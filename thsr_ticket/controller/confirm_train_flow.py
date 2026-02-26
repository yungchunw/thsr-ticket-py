import json
import questionary
from typing import List, Optional, Tuple

from requests.models import Response

from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.view_model.avail_trains import AvailTrains
from thsr_ticket.configs.web.param_schema import Train, ConfirmTrainModel
from thsr_ticket.view.console import console, QUESTIONARY_STYLE


class PreferredTrainNotAvailable(Exception):
    """Raised when the preferred train number is not in the available trains list."""
    pass


class ConfirmTrainFlow:
    def __init__(
        self,
        client: HTTPRequest,
        book_resp: Response,
        auto_select: bool = False,
        preferred_train: Optional[int] = None,
    ):
        self.client = client
        self.book_resp = book_resp
        self.auto_select = auto_select
        self.preferred_train = preferred_train

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

    def select_available_trains(self, trains: List[Train]) -> Train:
        if self.auto_select:
            if self.preferred_train:
                target = next((t for t in trains if t.id == self.preferred_train), None)
                if target is None:
                    console.print(f"  [dim]車次 {self.preferred_train} 目前無票[/dim]")
                    raise PreferredTrainNotAvailable(self.preferred_train)
                console.print(
                    f"  [dim]搶到車次：[/dim]"
                    f"[bold cyan]{target.id}[/bold cyan] "
                    f"[dim]{target.depart} → {target.arrive}[/dim]"
                )
                return target.form_value
            else:
                first = trains[0]
                console.print(
                    f"  [dim]自動選擇第一班：[/dim]"
                    f"[bold cyan]{first.id}[/bold cyan] "
                    f"[dim]{first.depart} → {first.arrive}[/dim]"
                )
                return first.form_value

        choices = [
            questionary.Choice(
                title=f"{train.id}  {train.depart} → {train.arrive}  {train.travel_time}" + (f"  {train.discount_str}" if train.discount_str else ""),
                value=train.form_value,
            )
            for train in trains
        ]
        return questionary.select("選擇班次", choices=choices, style=QUESTIONARY_STYLE).unsafe_ask()
