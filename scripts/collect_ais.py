"""跑一次 aisstream 即時收集，偵測靠港並累積到 data/ais_sightings.json。

執行：.venv\\Scripts\\python scripts/collect_ais.py
可多次執行（或掛排程）讓靠港序列逐步補齊。連外網。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings                       # noqa: E402
from app.sources.ais_provider import AISStreamProvider  # noqa: E402


def main() -> None:
    print(f"連線 aisstream.io，收集 {settings.ais_collect_seconds:.0f} 秒 "
          f"（bbox={settings.ais_bbox}）...")
    provider = AISStreamProvider()
    records = provider.fetch_port_calls()

    # 依港口彙整目前累積的靠港紀錄
    by_port: dict[str, int] = {}
    for r in records:
        by_port[r.port_unlocode] = by_port.get(r.port_unlocode, 0) + 1

    print(f"\n累積靠港紀錄：{len(records)} 筆，分佈：")
    for port, n in sorted(by_port.items(), key=lambda x: -x[1]):
        print(f"  {port}: {n}")

    target = settings.target_port_unlocode
    arrivals = [r for r in records if r.port_unlocode == target]
    print(f"\n抵達目標港 {target} 的船：{len(arrivals)} 艘")
    for r in arrivals[:20]:
        print(f"  MMSI={r.ship_code:12s} IMO={str(r.imo):9s} "
              f"name={str(r.name):24s} arrival={r.arrival} departure={r.departure}")

    print(f"\nsightings 已寫入：{settings.ais_sightings_file}")


if __name__ == "__main__":
    main()
