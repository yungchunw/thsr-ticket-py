from typing import List

from thsr_ticket.view.web.abstract_show import AbstractShow
from thsr_ticket.view.console import console
from thsr_ticket.view_model.error_feedback import Error


class ShowErrorMsg(AbstractShow):
    def show(self, errors: List[Error], select: bool = False) -> int:
        for e in errors:
            console.print(f"[bold red]✗[/bold red]  {e.msg.strip()}")
        return 0
