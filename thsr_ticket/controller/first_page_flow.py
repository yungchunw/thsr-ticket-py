import io
import json
import re
import questionary
from PIL import Image
from typing import Tuple, TYPE_CHECKING
from datetime import date, timedelta

from bs4 import BeautifulSoup
from requests.models import Response

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
from thsr_ticket.view.console import console, QUESTIONARY_STYLE

if TYPE_CHECKING:
    from thsr_ticket.controller.booking_flow import CliOptions


def _validate_date(v: str):
    v = v.strip().replace('/', '-')
    try:
        d = date.fromisoformat(v)
    except ValueError:
        return "日期格式錯誤（YYYY/MM/DD）"
    today = date.today()
    last = today + timedelta(days=DAYS_BEFORE_BOOKING_AVAILABLE)
    if d < today:
        return f"日期不可早於今天（{today}）"
    if d > last:
        return f"日期不可晚於 {last}（最多提前 {DAYS_BEFORE_BOOKING_AVAILABLE} 天）"
    return True


def _format_time(t_str: str) -> str:
    t_int = int(t_str[:-1])
    if t_str[-1] == "A" and (t_int // 100) == 12:
        t_int = t_int % 1200
    elif t_int != 1230 and t_str[-1] == "P":
        t_int += 1200
    return f'{t_int // 100:02d}:{t_int % 100:02d}'


class FirstPageFlow:
    def __init__(self, client: HTTPRequest, record: Record = None, opts: 'CliOptions' = None) -> None:
        self.client = client
        self.record = record
        self.opts = opts

    def run(self) -> Tuple[Response, BookingModel, bytes]:
        with console.status("[bold cyan]連線中...[/bold cyan]", spinner="dots"):
            book_page = self.client.request_booking_page().content
            img_resp = self.client.request_security_code_img(book_page).content
        page = BeautifulSoup(book_page, features='html.parser')

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
            class_type = questionary.select(
                "車廂類型",
                choices=[
                    questionary.Choice("標準車廂", value=0),
                    questionary.Choice("商務車廂", value=1),
                ],
                default=0,
                style=QUESTIONARY_STYLE,
            ).unsafe_ask()
            if self.opts:
                self.opts.class_type = class_type

        types_of_trip = _parse_types_of_trip_value(page)
        search_by = _parse_search_by(page)

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

        choices = [
            questionary.Choice(title=STATION_ZH.get(s.value, s.name), value=s.value)
            for s in StationMapping
        ]
        default_choice = next((c for c in choices if c.value == default_value), choices[0])
        return questionary.select(
            f"選擇{travel_type}站",
            choices=choices,
            default=default_choice,
            style=QUESTIONARY_STYLE,
        ).unsafe_ask()

    def select_date(self, date_type: str, cli_value: str = None) -> str:
        if cli_value is not None:
            return cli_value

        today = date.today()
        last_avail_date = today + timedelta(days=DAYS_BEFORE_BOOKING_AVAILABLE)
        console.print(f"\n[dim]可預訂範圍：{today} ~ {last_avail_date}[/dim]")
        raw = questionary.text(
            "輸入出發日期",
            default=str(today),
            style=QUESTIONARY_STYLE,
            validate=_validate_date,
        ).unsafe_ask() or str(today)
        return raw.strip().replace('-', '/')

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

        choices = [
            questionary.Choice(title=_format_time(t), value=t)
            for t in AVAILABLE_TIME_TABLE
        ]
        default_t = AVAILABLE_TIME_TABLE[default_value - 1]
        default_choice = next((c for c in choices if c.value == default_t), choices[0])
        return questionary.select("選擇出發時間", choices=choices, default=default_choice, style=QUESTIONARY_STYLE).unsafe_ask()

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

        choices = [questionary.Choice(str(i), value=i) for i in range(MAX_TICKET_NUM + 1)]
        result = questionary.select(f"{ticket_type_name}票數", choices=choices, default=default_ticket_num, style=QUESTIONARY_STYLE).unsafe_ask()
        return f'{result}{ticket_type.value}'

    def _format_ticket(self, ticket_type: TicketType, cli_count: int = None) -> str:
        if cli_count is not None:
            return f'{cli_count}{ticket_type.value}'
        return f'0{ticket_type.value}'

    def select_seat_prefer(self, page: BeautifulSoup, cli_value: int = None) -> str:
        options = page.find(**BOOKING_PAGE["seat_prefer_radio"])
        all_opts = options.find_all('option')

        if cli_value is None:
            cli_value = questionary.select(
                "座位偏好",
                choices=[
                    questionary.Choice("無偏好", value=0),
                    questionary.Choice("靠窗", value=1),
                    questionary.Choice("走道", value=2),
                ],
                default=0,
                style=QUESTIONARY_STYLE,
            ).unsafe_ask()
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
        from thsr_ticket.ml.captcha_solver import solve, LowConfidenceError  # noqa: F401
        code = solve(img_resp)
        console.print(f"[dim]自動辨識驗證碼：[/dim][bold yellow]{code}[/bold yellow]")
        return code

    console.print("\n[bold cyan]◆ 驗證碼[/bold cyan]  [dim]（圖片即將開啟）[/dim]")
    image = Image.open(io.BytesIO(img_resp))
    image.show()
    return questionary.text("輸入驗證碼", style=QUESTIONARY_STYLE).unsafe_ask() or ''
