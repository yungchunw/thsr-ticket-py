import json
from typing import Optional, Tuple

from bs4 import BeautifulSoup
from requests.models import Response
from thsr_ticket.configs.web.param_schema import ConfirmTicketModel

from thsr_ticket.model.db import Record
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.view.console import console


class ConfirmTicketFlow:
    def __init__(
        self,
        client: HTTPRequest,
        train_resp: Response,
        record: Record = None,
        use_membership: bool = False,
        personal_id: Optional[str] = None,
        phone: Optional[str] = None,
    ):
        self.client = client
        self.train_resp = train_resp
        self.record = record
        self.use_membership = use_membership
        self.cli_personal_id = personal_id
        self.cli_phone = phone

    def run(self) -> Tuple[Response]:
        page = BeautifulSoup(self.train_resp.content, features='html.parser')
        personal_id = self.set_personal_id()
        use_membership = self.use_membership or self._ask_membership()
        phone_num = self.set_phone_num()
        early_bird_params = _process_early_bird(page, personal_id)

        while True:
            member_radio, extra_params = _select_membership(page, personal_id, use_membership)
            ticket_model = ConfirmTicketModel(
                personal_id=personal_id,
                phone_num=phone_num,
                member_radio=member_radio,
            )
            dict_params = json.loads(ticket_model.json(by_alias=True))
            if extra_params:
                dict_params.update(extra_params)
            if early_bird_params:
                dict_params.update(early_bird_params)

            with console.status("[bold cyan]確認乘客資訊...[/bold cyan]", spinner="dots"):
                resp = self.client.submit_ticket(dict_params)

            if use_membership:
                from thsr_ticket.view_model.error_feedback import ErrorFeedback
                errors = ErrorFeedback().parse(resp.content)
                if any('TGo' in e.msg for e in errors):
                    console.print("[bold yellow]⚠[/bold yellow]  TGo 帳號失效，自動切換為非會員模式繼續訂票")
                    use_membership = False
                    continue
            break

        return resp, ticket_model

    def _ask_membership(self) -> bool:
        console.print("\n[bold cyan]◆ 會員身分[/bold cyan]")
        ans = input("  使用高鐵會員身分？(y/n，預設：n)：").strip().lower()
        return ans == 'y'

    def set_personal_id(self) -> str:
        if self.cli_personal_id:
            return self.cli_personal_id

        if self.record and (personal_id := self.record.personal_id):
            return personal_id

        console.print("\n[bold cyan]◆ 乘客資訊[/bold cyan]")
        return input("  輸入身分證字號：")

    def set_phone_num(self) -> str:
        if self.cli_phone:
            return self.cli_phone

        if self.record and (phone_num := self.record.phone):
            return phone_num

        if phone_num := input("  輸入手機號碼（選填）："):
            return phone_num
        return ''


def _select_membership(page: BeautifulSoup, personal_id: str, use_membership: bool = False) -> tuple:
    """Returns (member_radio_value, extra_params_dict_or_None)."""
    if not use_membership:
        tag = page.find('input', id='memberSystemRadio3')
        return tag.attrs['value'], None

    tag = page.find('input', id='memberSystemRadio1')
    extra_params = {
        'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup:memberShipNumber': personal_id,
        'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup:memberSystemShipCheckBox': 'on',
    }
    return tag.attrs['value'], extra_params


def _process_early_bird(page: BeautifulSoup, personal_id: str) -> Optional[dict]:
    """Handle early bird / super early bird multi-passenger forms."""
    early_bird_tags = page.find_all(class_='superEarlyBird')
    if not early_bird_tags:
        return None

    passenger_count = len(early_bird_tags)

    type_input = page.find(
        'input',
        attrs={'name': 'TicketPassengerInfoInputPanel:passengerDataView:0:passengerDataView2:passengerDataTypeName'}
    )
    if not type_input:
        return None
    early_type = type_input.attrs['value']

    params = {}

    console.print("\n[bold cyan]◆ 早鳥旅客資訊[/bold cyan]")
    first_id = input(f"  旅客 1 身分證字號（預設：{personal_id}）：") or personal_id
    prefix = 'TicketPassengerInfoInputPanel:passengerDataView:0:passengerDataView2'
    params[f'{prefix}:passengerDataLastName'] = ''
    params[f'{prefix}:passengerDataFirstName'] = ''
    params[f'{prefix}:passengerDataTypeName'] = early_type
    params[f'{prefix}:passengerDataIdNumber'] = first_id
    params[f'{prefix}:passengerDataInputChoice'] = '0'

    for i in range(1, passenger_count):
        while True:
            inp_id = input(f"  旅客 {i + 1} 身分證字號（確認後不可修改）：")
            if inp_id.strip():
                break
            console.print("  [bold red]✗[/bold red]  身分證字號不可為空！")

        prefix = f'TicketPassengerInfoInputPanel:passengerDataView:{i}:passengerDataView2'
        params[f'{prefix}:passengerDataLastName'] = ''
        params[f'{prefix}:passengerDataFirstName'] = ''
        params[f'{prefix}:passengerDataTypeName'] = early_type
        params[f'{prefix}:passengerDataIdNumber'] = inp_id.strip()
        params[f'{prefix}:passengerDataInputChoice'] = '0'

    return params
