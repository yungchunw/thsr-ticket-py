import hashlib
import os
import time
from dataclasses import dataclass
from datetime import date as date_cls, timedelta
from typing import Optional, Tuple

from requests.models import Response
from rich.rule import Rule

from thsr_ticket.controller.confirm_train_flow import ConfirmTrainFlow
from thsr_ticket.controller.confirm_ticket_flow import ConfirmTicketFlow
from thsr_ticket.controller.first_page_flow import FirstPageFlow
from thsr_ticket.view_model.error_feedback import ErrorFeedback
from thsr_ticket.view_model.booking_result import BookingResult
from thsr_ticket.view.web.show_error_msg import ShowErrorMsg
from thsr_ticket.view.web.show_booking_result import ShowBookingResult
from thsr_ticket.view.common import history_info
from thsr_ticket.model.db import ParamDB, Record
from thsr_ticket.remote.http_request import HTTPRequest
import questionary
from thsr_ticket.view.console import console, QUESTIONARY_STYLE


MAX_CAPTCHA_RETRY = 30


@dataclass
class CliOptions:
    auto_captcha: bool = True
    use_membership: bool = False
    from_station: Optional[int] = None
    to_station: Optional[int] = None
    date: Optional[str] = None
    time_id: Optional[int] = None
    adult_count: Optional[int] = None
    student_count: Optional[int] = None
    personal_id: Optional[str] = None
    phone: Optional[str] = None
    seat_prefer: Optional[int] = None
    class_type: Optional[int] = None
    preferred_train: Optional[int] = None  # snatch specific train number (e.g. 1234)
    snatch_single: bool = False       # single-day snatch: retry same date until ticket found
    snatch_end: Optional[str] = None  # multi-day snatch: iterate from date → snatch_end
    snatch_interval: Optional[int] = None  # seconds between rounds (both modes)
    snatch_select_train: bool = False  # show train list on first attempt, then lock in
    dry_run: bool = False             # simulate mode: stop before final ticket submission


class BookingFlow:
    def __init__(self, **kwargs) -> None:
        self.client = HTTPRequest()
        self.db = ParamDB()
        self.record = Record()
        self.opts = CliOptions(**kwargs)

        self.error_feedback = ErrorFeedback()
        self.show_error_msg = ShowErrorMsg()

    def run(self) -> Response:
        console.print(Rule("[bold cyan]台灣高鐵自動訂票[/bold cyan]", style="cyan"))

        self.show_history()
        self._ask_snatch_mode()

        snatch_dates = self._build_snatch_dates()
        is_snatch = bool(snatch_dates) or self.opts.snatch_single
        interval = self.opts.snatch_interval

        if snatch_dates:
            interval_str = f"，每 {interval} 秒輪詢一次" if interval else ""
            console.print(
                f"\n[bold yellow]刷票模式（跨日）[/bold yellow]  "
                f"[dim]{snatch_dates[0]} ~ {snatch_dates[-1]}，共 {len(snatch_dates)} 天{interval_str}[/dim]"
            )
        elif self.opts.snatch_single:
            interval_str = f"，每 {interval} 秒輪詢一次" if interval else ""
            console.print(
                f"\n[bold yellow]刷票模式（當天）[/bold yellow]  "
                f"[dim]查無票時持續重試{interval_str}[/dim]"
            )

        dates_to_try = snatch_dates if snatch_dates else [None]
        round_num = 0

        while True:
            round_num += 1
            if is_snatch and round_num > 1:
                console.print(f"\n[dim]── 第 {round_num} 輪 ──[/dim]")
                self.client = HTTPRequest()

            for attempt_date in dates_to_try:
                if attempt_date is not None:
                    self.opts.date = attempt_date
                    self.client = HTTPRequest()
                    console.print(f"\n[dim]嘗試 {attempt_date}...[/dim]")

                status, result = self._book_one_date(snatch_mode=is_snatch)

                if status == 'success':
                    return result
                elif status == 'no_trains':
                    date_str = attempt_date or self.opts.date or '當天'
                    console.print(f"  [dim]{date_str}：查無可售班次[/dim]")
                    continue
                else:
                    return result  # None or error Response

            # All dates exhausted in this round
            if not is_snatch or not self.opts.snatch_interval:
                break

            seconds = self.opts.snatch_interval
            console.print(
                f"\n[dim]本輪所有日期均無票，{seconds} 秒後重試（Ctrl+C 中止）...[/dim]"
            )
            time.sleep(seconds)

        if is_snatch:
            console.print(f"\n[bold red]✗[/bold red]  刷票失敗：查無可售班次")
        return None

    def _book_one_date(self, snatch_mode: bool = False) -> Tuple[str, Optional[Response]]:
        """Try to complete a booking for the current opts.date.

        Returns:
            ('success', ticket_resp)  - booking completed successfully
            ('no_trains', resp)       - no trains available (snatch mode: try next date)
            ('error', resp_or_none)   - unrecoverable error
        """
        try:
            from thsr_ticket.ml.captcha_solver import LowConfidenceError
        except ImportError:
            class LowConfidenceError(Exception):  # type: ignore[assignment]
                pass

        max_attempts = MAX_CAPTCHA_RETRY if self.opts.auto_captcha else 1
        book_resp = None
        book_model = None

        for attempt in range(1, max_attempts + 1):
            try:
                resp, model, captcha_img = FirstPageFlow(
                    client=self.client, record=self.record, opts=self.opts
                ).run()
            except LowConfidenceError as e:
                console.print(f"[dim][{attempt}/{max_attempts}] 跳過：{e}[/dim]")
                if attempt < max_attempts:
                    self.client = HTTPRequest()
                    continue
                console.print("[bold red]✗[/bold red]  已達最大嘗試次數")
                return 'error', None
            except Exception as e:
                console.print(f"[dim][{attempt}/{max_attempts}] 連線失敗：{e}[/dim]")
                if attempt < max_attempts:
                    self.client = HTTPRequest()
                    time.sleep(2)
                    continue
                console.print("[bold red]✗[/bold red]  已達最大嘗試次數")
                return 'error', None

            # Cache user choices so retries and subsequent date attempts skip re-asking
            self._fill_opts_from_model(model)

            errors = self.error_feedback.parse(resp.content)
            if not errors:
                self._save_captcha(captcha_img, label=model.security_code)
                book_resp, book_model = resp, model
                break

            error_msgs = ', '.join(e.msg.strip() for e in errors)
            is_captcha_error = any('檢測碼' in e.msg for e in errors)

            if not is_captcha_error:
                is_no_trains = any('查無' in e.msg for e in errors)
                if snatch_mode and is_no_trains:
                    return 'no_trains', resp
                console.print(f"[bold red]✗[/bold red]  {error_msgs}")
                return 'error', resp

            if attempt < max_attempts:
                self._save_captcha(captcha_img)
                console.print(f"[dim][{attempt}/{max_attempts}] {error_msgs}，重試中...[/dim]")
                self.client = HTTPRequest()
                time.sleep(1)
            else:
                self._save_captcha(captcha_img)
                self.show_error_msg.show(errors)
                return 'error', resp

        # Trains available — proceed with selection and confirmation
        if self.opts.snatch_select_train and self.opts.preferred_train is None:
            from thsr_ticket.view_model.avail_trains import AvailTrains
            trains = AvailTrains().parse(book_resp.content)
            if trains:
                choices = [
                    questionary.Choice(
                        title=f"{t.id}  {t.depart} → {t.arrive}  {t.travel_time}" + (f"  {t.discount_str}" if t.discount_str else ""),
                        value=t.id,
                    )
                    for t in trains
                ]
                self.opts.preferred_train = questionary.select(
                    "選擇目標車次",
                    choices=choices,
                    style=QUESTIONARY_STYLE,
                ).unsafe_ask()

        from thsr_ticket.controller.confirm_train_flow import PreferredTrainNotAvailable
        try:
            train_resp, train_model = ConfirmTrainFlow(
                self.client, book_resp,
                auto_select=snatch_mode,
                preferred_train=self.opts.preferred_train,
            ).run()
        except PreferredTrainNotAvailable as e:
            if snatch_mode:
                return 'no_trains', book_resp
            console.print(f"[bold red]✗[/bold red]  車次 {e} 目前無票")
            return 'error', book_resp
        except Exception as e:
            console.print(f"[dim]確認班次失敗：{e}，重試中...[/dim]")
            self.client = HTTPRequest()
            return 'no_trains', None
        if self.show_error(train_resp.content):
            return 'error', train_resp

        if self.opts.dry_run:
            console.print("\n[bold yellow]── 模擬模式：班次確認完畢，模擬查無票繼續輪詢 ──[/bold yellow]")
            return 'no_trains', train_resp

        ticket_resp, ticket_model = ConfirmTicketFlow(
            self.client, train_resp, self.record,
            use_membership=self.opts.use_membership,
            personal_id=self.opts.personal_id,
            phone=self.opts.phone,
        ).run()
        if self.show_error(ticket_resp.content):
            return 'error', ticket_resp

        result_model = BookingResult().parse(ticket_resp.content)
        ShowBookingResult().show(result_model)
        console.print("[bold yellow]請使用官方管道完成付款及取票！[/bold yellow]\n")

        self.db.save(book_model, ticket_model)
        return 'success', ticket_resp

    def _build_snatch_dates(self) -> Optional[list]:
        """Build list of date strings from opts.date to opts.snatch_end (inclusive)."""
        if not self.opts.snatch_end:
            return None
        start_str = self.opts.date or str(date_cls.today())
        end_str = self.opts.snatch_end
        start = date_cls.fromisoformat(start_str.replace('/', '-'))
        end = date_cls.fromisoformat(end_str.replace('/', '-'))
        if end < start:
            console.print("[bold red]✗[/bold red]  --snatch-end 必須不早於起始日期")
            return None
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime('%Y/%m/%d'))
            current += timedelta(days=1)
        return dates

    def _fill_opts_from_model(self, model) -> None:
        """Cache user's booking choices into opts so retries skip interactive prompts."""
        if self.opts.from_station is None:
            self.opts.from_station = model.start_station
        if self.opts.to_station is None:
            self.opts.to_station = model.dest_station
        if self.opts.date is None:
            self.opts.date = model.outbound_date
        if self.opts.time_id is None:
            from thsr_ticket.configs.common import AVAILABLE_TIME_TABLE
            try:
                self.opts.time_id = AVAILABLE_TIME_TABLE.index(model.outbound_time) + 1
            except ValueError:
                pass
        if self.opts.adult_count is None:
            self.opts.adult_count = int(model.adult_ticket_num[:-1])
        if self.opts.student_count is None:
            self.opts.student_count = int(model.college_ticket_num[:-1])
        if self.opts.seat_prefer is None:
            self.opts.seat_prefer = 0
        if self.opts.class_type is None:
            self.opts.class_type = model.class_type

    def show_history(self) -> None:
        hist = self.db.get_history()
        if not hist:
            return
        record = history_info(hist, db=self.db)
        if record is not None:
            self.record = record

    def _ask_snatch_mode(self) -> None:
        """Interactively ask about snatch mode if not already set via CLI."""
        if self.opts.snatch_end is not None or self.opts.snatch_single:
            return

        mode = questionary.select(
            "搶票模式",
            choices=[
                questionary.Choice("不啟用", value="none"),
                questionary.Choice("當天搶票（指定日期持續重試直到有票）", value="single"),
                questionary.Choice("跨日搶票（從出發日逐日搜尋到指定日期）", value="multi"),
            ],
            style=QUESTIONARY_STYLE,
        ).unsafe_ask()

        if mode == "none":
            return

        if mode == "single":
            self.opts.snatch_single = True

        elif mode == "multi":
            today = date_cls.today()
            last = today + timedelta(days=28)
            console.print(f"[dim]可搶票範圍到：{last}[/dim]")

            def _validate_end_date(v: str):
                v = v.strip().replace('/', '-')
                try:
                    d = date_cls.fromisoformat(v)
                except ValueError:
                    return "日期格式錯誤（YYYY/MM/DD）"
                if d < today:
                    return "結束日期不可早於今天"
                if d > last:
                    return f"結束日期不可晚於 {last}"
                return True

            end_raw = questionary.text(
                "搶票結束日期",
                style=QUESTIONARY_STYLE,
                validate=_validate_end_date,
            ).unsafe_ask()
            self.opts.snatch_end = end_raw.strip().replace('-', '/')

        use_interval = questionary.confirm(
            "查無票時持續輪詢重試？",
            default=False,
            style=QUESTIONARY_STYLE,
        ).unsafe_ask()
        if use_interval:
            interval_raw = questionary.text(
                "輪詢間隔（秒）",
                default="30",
                style=QUESTIONARY_STYLE,
                validate=lambda v: True if v.strip().isdigit() and int(v.strip()) > 0 else "請輸入正整數",
            ).unsafe_ask()
            self.opts.snatch_interval = int(interval_raw.strip())

        if self.opts.preferred_train is None:
            use_specific = questionary.confirm(
                "指定特定車次？（不指定則自動選最早班次）",
                default=False,
                style=QUESTIONARY_STYLE,
            ).unsafe_ask()
            if use_specific:
                self.opts.snatch_select_train = True

    @staticmethod
    def _save_captcha(img_bytes: bytes, label: str = None) -> None:
        """Save captcha to training data directory.

        label=None  → unlabeled (NNN_captcha_hash.png), needs manual labeling
        label='XXXX' → auto-labeled (NNN_XXXX_hash.png), confirmed correct by THSR
        """
        raw_dir = os.path.join(
            os.path.dirname(__file__), '..', 'ml', 'train', 'data', 'raw',
        )
        os.makedirs(raw_dir, exist_ok=True)
        img_hash = hashlib.md5(img_bytes).hexdigest()[:12]
        existing = [f for f in os.listdir(raw_dir) if f.endswith('.png')]
        next_num = max((int(f.split('_')[0]) for f in existing if f[0].isdigit()), default=0) + 1
        middle = label if label else 'captcha'
        filepath = os.path.join(raw_dir, f'{next_num:05d}_{middle}_{img_hash}.png')
        if not os.path.exists(filepath):
            with open(filepath, 'wb') as f:
                f.write(img_bytes)

    def show_error(self, html: bytes) -> bool:
        errors = self.error_feedback.parse(html)
        if len(errors) == 0:
            return False
        self.show_error_msg.show(errors)
        return True
