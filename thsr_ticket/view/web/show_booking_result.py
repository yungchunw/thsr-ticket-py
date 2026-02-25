from typing import List

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from thsr_ticket.view.web.abstract_show import AbstractShow
from thsr_ticket.view.console import console
from thsr_ticket.view_model.booking_result import Ticket


class ShowBookingResult(AbstractShow):
    def show(self, tickets: List[Ticket], select: bool = False) -> int:
        ticket = tickets[0]

        info = Text()
        info.append("訂位代號  ", style="bold")
        info.append(f"{ticket.id}\n", style="bold yellow")
        info.append("繳費期限  ", style="bold")
        info.append(f"{ticket.payment_deadline}\n")
        info.append("票數      ", style="bold")
        info.append(f"{ticket.ticket_num_info}\n")
        info.append("總價      ", style="bold")
        info.append(ticket.price, style="bold green")

        table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 2))
        table.add_column("日期")
        table.add_column("起程")
        table.add_column("")
        table.add_column("到達")
        table.add_column("出發")
        table.add_column("抵達")
        table.add_column("車次", style="cyan")
        table.add_column("座位")
        table.add_row(
            ticket.date,
            ticket.start_station,
            "→",
            ticket.dest_station,
            ticket.depart_time,
            ticket.arrival_time,
            str(ticket.train_id),
            f"{ticket.seat_class} {ticket.seat}",
        )

        console.print()
        console.print(Panel(
            Group(info, Text(""), table),
            title="[bold green]✓ 訂位成功[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))
        return 0
