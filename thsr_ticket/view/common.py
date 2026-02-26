from typing import Iterable, List, Optional, TYPE_CHECKING

import questionary
from rich.panel import Panel
from rich.table import Table

from thsr_ticket.model.db import Record
from thsr_ticket.model.web.booking_form.station_mapping import StationMapping
from thsr_ticket.configs.common import STATION_ZH
from thsr_ticket.view.console import console, QUESTIONARY_STYLE

if TYPE_CHECKING:
    from thsr_ticket.model.db import ParamDB


def history_info(hists: Iterable[Record], select: bool = True, db: 'ParamDB' = None) -> Optional[Record]:
    hists_list = list(hists)

    while True:
        for idx, r in enumerate(hists_list, 1):
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

        if not select:
            return None

        choices: List[questionary.Choice] = [questionary.Choice("略過", value=-1)]
        if db:
            choices.append(questionary.Choice("刪除紀錄...", value=-2))
        for idx, r in enumerate(hists_list, 1):
            start_name = STATION_ZH.get(r.start_station, str(r.start_station))
            dest_name = STATION_ZH.get(r.dest_station, str(r.dest_station))
            choices.append(questionary.Choice(
                title=f"紀錄 {idx}：{start_name} → {dest_name}",
                value=idx - 1,
            ))

        result = questionary.select("請選擇歷史紀錄", choices=choices, style=QUESTIONARY_STYLE).unsafe_ask()

        if result == -1:
            return None

        if result == -2:
            del_choices = []
            for idx, r in enumerate(hists_list, 1):
                start_name = STATION_ZH.get(r.start_station, str(r.start_station))
                dest_name = STATION_ZH.get(r.dest_station, str(r.dest_station))
                del_choices.append(questionary.Choice(
                    title=f"紀錄 {idx}：{start_name} → {dest_name}  ({r.personal_id})",
                    value=idx - 1,
                ))
            to_delete = questionary.checkbox(
                "選擇要刪除的紀錄（空白確認取消）",
                choices=del_choices,
                style=QUESTIONARY_STYLE,
            ).unsafe_ask() or []

            for del_idx in sorted(to_delete, reverse=True):
                db.delete(del_idx)
                hists_list.pop(del_idx)

            if not hists_list:
                return None
            continue  # re-display updated list

        return hists_list[result]
