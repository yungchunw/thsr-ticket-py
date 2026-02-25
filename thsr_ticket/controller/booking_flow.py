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
try:
    from thsr_ticket.ml.captcha_solver import LowConfidenceError
except ImportError:
    class LowConfidenceError(Exception):  # type: ignore[no-redef]
        pass
from thsr_ticket.view_model.error_feedback import ErrorFeedback
from thsr_ticket.view_model.booking_result import BookingResult
from thsr_ticket.view.web.show_error_msg import ShowErrorMsg
from thsr_ticket.view.web.show_booking_result import ShowBookingResult
from thsr_ticket.view.common import history_info
from thsr_ticket.model.db import ParamDB, Record
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.view.console import console


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
    snatch_end: Optional[str] = None  # enables snatch mode; try all dates from date→snatch_end


class BookingFlow:
    def __init__(self, **kwargs) -> None:
        self.client = HTTPRequest()
        self.db = ParamDB()
        self.record = Record()
        self.opts = CliOptions(**kwargs)

        self.error_feedback = ErrorFeedback()
        self.show_error_msg = ShowErrorMsg()

    def run(self) -> Response:
        console.print(Rule("[bold cyan]🚄  台灣高鐵自動訂票[/bold cyan]", style="cyan"))

        self.show_history()

        snatch_dates = self._build_snatch_dates()
        if snatch_dates:
            console.print(
                f"\n[bold yellow]🎯 刷票模式[/bold yellow]  "
                f"[dim]{snatch_dates[0]} ~ {snatch_dates[-1]}，共 {len(snatch_dates)} 天[/dim]"
            )

        dates_to_try = snatch_dates if snatch_dates else [None]

        for attempt_date in dates_to_try:
            if attempt_date is not None:
                self.opts.date = attempt_date
                self.client = HTTPRequest()
                console.print(f"\n[dim]嘗試 {attempt_date}...[/dim]")

            status, result = self._book_one_date(snatch_mode=bool(snatch_dates))

            if status == 'success':
                return result
            elif status == 'no_trains':
                console.print(f"  [dim]{attempt_date}：查無可售班次[/dim]")
                continue
            else:
                return result  # None or error Response

        if snatch_dates:
            console.print(f"\n[bold red]✗[/bold red]  刷票失敗：所有日期均無可售班次")
        return None

    def _book_one_date(self, snatch_mode: bool = False) -> Tuple[str, Optional[Response]]:
        """Try to complete a booking for the current opts.date.

        Returns:
            ('success', ticket_resp)  - booking completed successfully
            ('no_trains', resp)       - no trains available (snatch mode: try next date)
            ('error', resp_or_none)   - unrecoverable error
        """
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
        train_resp, train_model = ConfirmTrainFlow(
            self.client, book_resp, auto_select=snatch_mode
        ).run()
        if self.show_error(train_resp.content):
            return 'error', train_resp

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
        h_idx = history_info(hist)
        if h_idx is not None:
            self.record = hist[h_idx]

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
