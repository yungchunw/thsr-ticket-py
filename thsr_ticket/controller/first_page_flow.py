import io
import json
from PIL import Image
from typing import Tuple, TYPE_CHECKING
from datetime import date, timedelta

from bs4 import BeautifulSoup
from requests.models import Response
from rich.columns import Columns

from thsr_ticket.model.db import Record
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.configs.web.param_schema import BookingModel
from thsr_ticket.configs.web.parse_html_element import BOOKING_PAGE
from thsr_ticket.configs.web.enums import StationMapping, TicketType
from thsr_ticket.configs.common import (
    AVAILABLE_TIME_TABLE,
    DAYS_BEFORE_BOOKING_AVAILABLE,
    MAX_TICKET_NUM,
    STATION_ZH,
)
from thsr_ticket.view.console import console

if TYPE_CHECKING:
    from thsr_ticket.controller.booking_flow import CliOptions


class FirstPageFlow:
    def __init__(self, client: HTTPRequest, record: Record = None, opts: 'CliOptions' = None) -> None:
        self.client = client
        self.record = record
        self.opts = opts

    def run(self) -> Tuple[Response, BookingModel, bytes]:
        # First page. Booking options
        with console.status("[bold cyan]連線中...[/bold cyan]", spinner="dots"):
            book_page = self.client.request_booking_page().content
            img_resp = self.client.request_security_code_img(book_page).content
        page = BeautifulSoup(book_page, features='html.parser')

        # Step 1: collect user inputs (interactive prompts) — done before captcha
        # so user answers are preserved even if captcha solving fails
        start_station = self.select_station('啟程', self.opts.from_station if self.opts else None)
        dest_station = self.select_station('到達', self.opts.to_station if self.opts else None, default_value=StationMapping.Zuouing.value)
        outbound_date = self.select_date('出發', self.opts.date if self.opts else None)
        outbound_time = self.select_time('啟程', self.opts.time_id if self.opts else None)
        adult_ticket_num = self.select_ticket_num(TicketType.ADULT, cli_count=self.opts.adult_count if self.opts else None)
        college_ticket_num = self._format_ticket(TicketType.COLLEGE, self.opts.student_count if self.opts else None)
        seat_prefer = self.select_seat_prefer(page, self.opts.seat_prefer if self.opts else None)
        if self.opts and self.opts.class_type is not None:
            class_type = self.opts.class_type
        else:
            console.print("\n[bold cyan]◆ 車廂類型[/bold cyan]")
            console.print("  [dim] 0[/dim]  標準車廂   [dim] 1[/dim]  商務車廂")
            sel = input("  輸入選擇（預設：0）：").strip() or '0'
            class_type = int(sel)
            if self.opts:
                self.opts.class_type = class_type
        types_of_trip = _parse_types_of_trip_value(page)
        search_by = _parse_search_by(page)

        # Cache answers back into opts so retries skip re-asking
        if self.opts:
            if self.opts.from_station is None:
                self.opts.from_station = start_station
            if self.opts.to_station is None:
                self.opts.to_station = dest_station
            if self.opts.date is None:
                self.opts.date = outbound_date
            if self.opts.time_id is None:
                try:
                    self.opts.time_id = AVAILABLE_TIME_TABLE.index(outbound_time) + 1
                except ValueError:
                    pass
            if self.opts.adult_count is None:
                self.opts.adult_count = int(adult_ticket_num[:-1])
            if self.opts.student_count is None:
                self.opts.student_count = int(college_ticket_num[:-1])
            if self.opts.seat_prefer is None:
                self.opts.seat_prefer = 0
            if self.opts.class_type is None:
                self.opts.class_type = class_type

        # Step 2: solve captcha (may raise LowConfidenceError — user answers already saved)
        security_code = _solve_captcha(img_resp, self.opts.auto_captcha if self.opts else False)

        with console.status("[bold cyan]提交訂票資訊...[/bold cyan]", spinner="dots"):
            book_model = BookingModel(
                start_station=start_station,
                dest_station=dest_station,
                outbound_date=outbound_date,
                outbound_time=outbound_time,
                adult_ticket_num=adult_ticket_num,
                college_ticket_num=college_ticket_num,
                seat_prefer=seat_prefer,
                class_type=class_type,
                types_of_trip=types_of_trip,
                search_by=search_by,
                security_code=security_code,
            )
            json_params = book_model.json(by_alias=True)
            dict_params = json.loads(json_params)
            resp = self.client.submit_booking_form(dict_params)
        return resp, book_model, img_resp

    def select_station(self, travel_type: str, cli_value: int = None, default_value: int = StationMapping.Taipei.value) -> int:
        if cli_value is not None:
            return cli_value

        if (
            self.record
            and (
                station := {
                    '啟程': self.record.start_station,
                    '到達': self.record.dest_station,
                }.get(travel_type)
            )
        ):
            return station

        console.print(f"\n[bold cyan]◆ 選擇{travel_type}站[/bold cyan]")
        items = [
            f"[dim]{s.value:>2}[/dim]  {STATION_ZH.get(s.value, s.name)}"
            for s in StationMapping
        ]
        console.print(Columns(items, equal=True, padding=(0, 2)))
        return int(
            input(f"  輸入選擇（預設：{default_value}）：")
            or default_value
        )

    def select_date(self, date_type: str, cli_value: str = None) -> str:
        if cli_value is not None:
            return cli_value

        today = date.today()
        last_avail_date = today + timedelta(days=DAYS_BEFORE_BOOKING_AVAILABLE)
        console.print(f"\n[bold cyan]◆ 選擇{date_type}日期[/bold cyan]  [dim]{today} ~ {last_avail_date}[/dim]")
        return input("  輸入日期（預設：今日）：") or str(today)

    def select_time(self, time_type: str, cli_value: int = None, default_value: int = 10) -> str:
        if cli_value is not None:
            return AVAILABLE_TIME_TABLE[cli_value - 1]

        if self.record and (
            time_str := {
                '啟程': self.record.outbound_time,
                '回程': None,
            }.get(time_type)
        ):
            return time_str

        console.print("\n[bold cyan]◆ 選擇出發時間[/bold cyan]")
        items = []
        for idx, t_str in enumerate(AVAILABLE_TIME_TABLE, 1):
            t_int = int(t_str[:-1])
            if t_str[-1] == "A" and (t_int // 100) == 12:
                t_int = "{:04d}".format(t_int % 1200)  # type: ignore
            elif t_int != 1230 and t_str[-1] == "P":
                t_int += 1200
            t_str_fmt = str(t_int)
            items.append(f"[dim]{idx:>2}[/dim]  {t_str_fmt[:-2]}:{t_str_fmt[-2:]}")
        console.print(Columns(items, equal=True, padding=(0, 1), column_first=True))

        selected_opt = int(input(f"  輸入選擇（預設：{default_value}）：") or default_value)
        return AVAILABLE_TIME_TABLE[selected_opt-1]

    def select_ticket_num(self, ticket_type: TicketType, default_ticket_num: int = 1, cli_count: int = None) -> str:
        if cli_count is not None:
            return f'{cli_count}{ticket_type.value}'

        if self.record and (
            ticket_num_str := {
                TicketType.ADULT: self.record.adult_num,
                TicketType.CHILD: None,
                TicketType.DISABLED: None,
                TicketType.ELDER: None,
                TicketType.COLLEGE: None,
            }.get(ticket_type)
        ):
            return ticket_num_str

        ticket_type_name = {
            TicketType.ADULT: '成人',
            TicketType.CHILD: '孩童',
            TicketType.DISABLED: '愛心',
            TicketType.ELDER: '敬老',
            TicketType.COLLEGE: '大學生',
        }.get(ticket_type)

        console.print(f"\n[bold cyan]◆ {ticket_type_name}票數[/bold cyan]  [dim]0 ~ {MAX_TICKET_NUM}[/dim]")
        ticket_num = int(input(f"  輸入票數（預設：{default_ticket_num}）：") or default_ticket_num)
        return f'{ticket_num}{ticket_type.value}'

    def _format_ticket(self, ticket_type: TicketType, cli_count: int = None) -> str:
        if cli_count is not None:
            return f'{cli_count}{ticket_type.value}'
        return f'0{ticket_type.value}'

    def select_seat_prefer(self, page: BeautifulSoup, cli_value: int = None) -> str:
        options = page.find(**BOOKING_PAGE["seat_prefer_radio"])
        all_opts = options.find_all('option')

        if cli_value is None:
            console.print("\n[bold cyan]◆ 座位偏好[/bold cyan]")
            console.print("  [dim] 0[/dim]  無偏好   [dim] 1[/dim]  靠窗   [dim] 2[/dim]  走道")
            sel = input("  輸入選擇（預設：0）：").strip() or '0'
            cli_value = int(sel)
            if self.opts:
                self.opts.seat_prefer = cli_value

        if cli_value < len(all_opts):
            return all_opts[cli_value].attrs['value']
        return all_opts[0].attrs['value']


def _parse_seat_prefer_value(page: BeautifulSoup) -> str:
    options = page.find(**BOOKING_PAGE["seat_prefer_radio"])
    preferred_seat = options.find_next(selected='selected')
    return preferred_seat.attrs['value']


def _parse_types_of_trip_value(page: BeautifulSoup) -> int:
    options = page.find(**BOOKING_PAGE["types_of_trip"])
    tag = options.find_next(selected='selected')
    return int(tag.attrs['value'])


def _parse_search_by(page: BeautifulSoup) -> str:
    candidates = page.find_all('input', {'name': 'bookingMethod'})
    tag = next((cand for cand in candidates if 'checked' in cand.attrs))
    return tag.attrs['value']


def _solve_captcha(img_resp: bytes, auto_captcha: bool = False) -> str:
    if auto_captcha:
        from thsr_ticket.ml.captcha_solver import solve, LowConfidenceError
        code = solve(img_resp)
        console.print(f"[dim]自動辨識驗證碼：[/dim][bold yellow]{code}[/bold yellow]")
        return code

    console.print("\n[bold cyan]◆ 驗證碼[/bold cyan]  [dim]（圖片即將開啟）[/dim]")
    image = Image.open(io.BytesIO(img_resp))
    image.show()
    return input("  輸入驗證碼：")
