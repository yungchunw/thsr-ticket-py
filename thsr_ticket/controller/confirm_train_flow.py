import json
from typing import List, Tuple

from requests.models import Response
from rich.table import Table

from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.view_model.avail_trains import AvailTrains
from thsr_ticket.configs.web.param_schema import Train, ConfirmTrainModel
from thsr_ticket.view.console import console


class ConfirmTrainFlow:
    def __init__(self, client: HTTPRequest, book_resp: Response, auto_select: bool = False):
        self.client = client
        self.book_resp = book_resp
        self.auto_select = auto_select

    def run(self) -> Tuple[Response, ConfirmTrainModel]:
        trains = AvailTrains().parse(self.book_resp.content)
        if not trains:
            raise ValueError('No available trains!')

        confirm_model = ConfirmTrainModel(
            selected_train=self.select_available_trains(trains),
        )
        json_params = confirm_model.json(by_alias=True)
        dict_params = json.loads(json_params)
        with console.status("[bold cyan]確認班次中...[/bold cyan]", spinner="dots"):
            resp = self.client.submit_train(dict_params)
        return resp, confirm_model

    def select_available_trains(self, trains: List[Train], default_value: int = 1) -> Train:
        table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
        table.add_column("#", style="dim", width=3)
        table.add_column("車次", style="cyan")
        table.add_column("出發")
        table.add_column("→", style="dim")
        table.add_column("抵達")
        table.add_column("行程")
        table.add_column("優惠", style="green")

        for idx, train in enumerate(trains, 1):
            table.add_row(
                str(idx),
                str(train.id),
                train.depart,
                "",
                train.arrive,
                train.travel_time,
                train.discount_str,
            )

        console.print()
        console.print(table)

        if self.auto_select:
            first = trains[0]
            console.print(
                f"  [dim]自動選擇第一班：[/dim]"
                f"[bold cyan]{first.id}[/bold cyan] "
                f"[dim]{first.depart} → {first.arrive}[/dim]"
            )
            return first.form_value

        selection = int(input(f"  輸入選擇（預設：{default_value}）：") or default_value)
        return trains[selection-1].form_value
