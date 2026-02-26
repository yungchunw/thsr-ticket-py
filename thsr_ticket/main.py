import os
import sys
import argparse

sys.path.append("./")

from rich.columns import Columns
from rich.rule import Rule
from rich.table import Table

from thsr_ticket.controller.booking_flow import BookingFlow
from thsr_ticket.configs.web.enums import StationMapping
from thsr_ticket.configs.common import AVAILABLE_TIME_TABLE, STATION_ZH
from thsr_ticket.view.console import console


def _format_time(t_str: str) -> str:
    t_int = int(t_str[:-1])
    if t_str[-1] == "A" and (t_int // 100) == 12:
        t_int = t_int % 1200
    elif t_int != 1230 and t_str[-1] == "P":
        t_int += 1200
    return f'{t_int // 100:02d}:{t_int % 100:02d}'


def list_stations():
    console.print(Rule("[bold cyan]車站列表[/bold cyan]", style="cyan"))
    table = Table(show_header=False, box=None, padding=(0, 3))
    table.add_column("ID", style="dim", width=4)
    table.add_column("站名")
    for s in StationMapping:
        table.add_row(str(s.value), STATION_ZH.get(s.value, s.name))
    console.print(table)


def list_time_table():
    console.print(Rule("[bold cyan]時刻表[/bold cyan]", style="cyan"))
    items = [
        f"[dim]{idx:>2}[/dim]  {_format_time(t_str)}"
        for idx, t_str in enumerate(AVAILABLE_TIME_TABLE, 1)
    ]
    console.print(Columns(items, equal=True, padding=(0, 1), column_first=True))


def _load_config() -> dict:
    """Load defaults from ~/.thsr.toml if it exists."""
    config_path = os.path.expanduser('~/.thsr.toml')
    if not os.path.exists(config_path):
        return {}
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        console.print("[dim]提示：安裝 tomli 套件以支援設定檔功能[/dim]")
        return {}
    try:
        with open(config_path, 'rb') as f:
            return tomllib.load(f)
    except Exception as e:
        console.print(f"[bold yellow]⚠[/bold yellow]  讀取設定檔失敗：{e}")
        return {}


# CLI arg names that map directly to config file keys
_CONFIG_KEYS = {
    'from_station', 'to_station', 'date', 'time', 'adult_count',
    'student_count', 'personal_id', 'phone', 'seat_prefer', 'class_type',
    'snatch_end', 'snatch_interval', 'snatch_single',
}


def main():
    config = _load_config()

    parser = argparse.ArgumentParser(
        description='台灣高鐵自動訂票程式',
        epilog='設定檔：~/.thsr.toml（可存常用預設值，CLI 參數優先）',
    )

    # Booking options
    parser.add_argument('-f', '--from-station', type=int, metavar='ID', help='啟程站 ID (1-12)')
    parser.add_argument('-t', '--to-station', type=int, metavar='ID', help='到達站 ID (1-12)')
    parser.add_argument('-d', '--date', metavar='DATE', help='出發日期 (YYYY/MM/DD)')
    parser.add_argument('-T', '--time', type=int, metavar='ID', help='出發時間 ID (1-37)')
    parser.add_argument('-a', '--adult-count', type=int, metavar='N', help='成人票數 (0-10)')
    parser.add_argument('-s', '--student-count', type=int, metavar='N', help='大學生票數 (0-10)')
    parser.add_argument('-i', '--personal-id', metavar='ID', help='身分證字號')
    parser.add_argument('-P', '--phone', metavar='PHONE', help='手機號碼')
    parser.add_argument('-p', '--seat-prefer', type=int, choices=[0, 1, 2], metavar='N', help='座位偏好 0:無 1:靠窗 2:走道')
    parser.add_argument('-c', '--class-type', type=int, choices=[0, 1], metavar='N', help='車廂類型 0:標準 1:商務')

    # Snatch mode
    parser.add_argument('--snatch', action='store_true', help='當天搶票：同一天持續重試直到有票')
    parser.add_argument('--snatch-end', metavar='DATE', help='跨日搶票：從 --date 開始逐日嘗試直到此日期（格式：YYYY/MM/DD）')
    parser.add_argument('--snatch-interval', type=int, metavar='SECONDS', help='搶票輪詢間隔（秒）；設定後查無票時持續輪詢')
    parser.add_argument('--train-id', type=int, metavar='N', help='指定搶特定車次（搭配搶票模式使用）')

    # Feature flags
    parser.add_argument('-C', '--no-auto-captcha', action='store_true', help='停用自動辨識驗證碼（改為手動輸入）')
    parser.add_argument('-m', '--use-membership', action='store_true', help='使用高鐵會員身分')
    parser.add_argument('--dry-run', action='store_true', help='模擬模式：完整執行流程但不實際送出訂位')

    # Info commands
    parser.add_argument('--list-station', action='store_true', help='列出所有車站')
    parser.add_argument('--list-time-table', action='store_true', help='列出所有時間選項')

    # Apply config file values as defaults (CLI args override)
    config_defaults = {k: v for k, v in config.items() if k in _CONFIG_KEYS}
    if config_defaults:
        parser.set_defaults(**config_defaults)

    args = parser.parse_args()

    if args.list_station:
        list_stations()
        return

    if args.list_time_table:
        list_time_table()
        return

    flow = BookingFlow(
        auto_captcha=not args.no_auto_captcha,
        use_membership=args.use_membership,
        from_station=args.from_station,
        to_station=args.to_station,
        date=args.date,
        time_id=args.time,
        adult_count=args.adult_count,
        student_count=args.student_count,
        personal_id=args.personal_id,
        phone=args.phone,
        seat_prefer=args.seat_prefer,
        class_type=args.class_type,
        preferred_train=args.train_id,
        snatch_single=args.snatch,
        snatch_end=args.snatch_end,
        snatch_interval=args.snatch_interval,
        dry_run=args.dry_run,
    )
    try:
        flow.run()
    except KeyboardInterrupt:
        console.print("\n[dim]已中止。[/dim]")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
