from typing import Iterable

from rich.panel import Panel
from rich.table import Table

from thsr_ticket.model.db import Record
from thsr_ticket.model.web.booking_form.station_mapping import StationMapping
from thsr_ticket.configs.common import STATION_ZH
from thsr_ticket.view.console import console


def history_info(hists: Iterable[Record], select: bool = True) -> int:
    for idx, r in enumerate(hists, 1):
        t_str = r.outbound_time
        t_int = int(t_str[:-1])
        suffix = t_str[-1]
        if suffix == 'A' and t_int // 100 == 12:
            t_int = t_int % 1200
        elif suffix == 'P' and t_int != 1230:
            t_int += 1200
        time_disp = f"{t_int // 100:02d}:{t_int % 100:02d}"

        start_val = r.start_station
        dest_val = r.dest_station
        start_name = STATION_ZH.get(start_val, StationMapping(start_val).name)
        dest_name = STATION_ZH.get(dest_val, StationMapping(dest_val).name)

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold dim", min_width=10)
        grid.add_column()
        grid.add_row("身分證字號", r.personal_id)
        grid.add_row("手機號碼", r.phone)
        grid.add_row("起程 → 到達", f"{start_name} → {dest_name}")
        grid.add_row("出發時間", time_disp)
        grid.add_row("成人票數", r.adult_num[:-1])
        console.print(Panel(grid, title=f"[bold cyan]歷史紀錄 {idx}[/bold cyan]", border_style="cyan"))

    if select:
        sel = input("請選擇紀錄（Enter 跳過）：")
        return int(sel) - 1 if sel.strip() else None
    return None
