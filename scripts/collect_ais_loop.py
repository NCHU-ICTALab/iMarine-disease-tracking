"""持續收集 aisstream 即時船位數小時，累積靠港序列到 data/ais_sightings.json。

每一輪 = 連線收集 AIS_COLLECT_SECONDS 秒 → 偵測靠港 → 併入 sightings；輪與輪之間 pause。
多輪累積可補齊靠港序列、增加抵達目標港的真實船數。

用法：
    .venv\\Scripts\\python -u scripts/collect_ais_loop.py [時數] [每輪間隔秒]
    例：.venv\\Scripts\\python -u scripts/collect_ais_loop.py 6 60
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings                       # noqa: E402
from app.sources.ais_provider import AISStreamProvider  # noqa: E402

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
PAUSE = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0


def main() -> None:
    end = datetime.now() + timedelta(hours=HOURS)
    provider = AISStreamProvider()
    target = settings.target_port_unlocode
    cycle = 0
    print(f"[loop] 開始持續收集，預計跑到 {end:%Y-%m-%d %H:%M:%S}"
          f"（每輪收集 {settings.ais_collect_seconds:.0f}s、間隔 {PAUSE:.0f}s）", flush=True)

    while datetime.now() < end:
        cycle += 1
        try:
            records = provider.fetch_port_calls()
        except Exception as e:  # noqa: BLE001  單輪失敗不中斷整體
            print(f"[loop] cycle {cycle} 失敗：{e!r}；{PAUSE:.0f}s 後重試", flush=True)
            time.sleep(PAUSE)
            continue

        ships = len({r.ship_code for r in records})
        ports: dict[str, int] = {}
        for r in records:
            ports[r.port_unlocode] = ports.get(r.port_unlocode, 0) + 1
        tgt = ports.get(target, 0)
        top = ", ".join(f"{p}:{n}" for p, n in sorted(ports.items(), key=lambda x: -x[1])[:6])
        print(f"[loop] cycle {cycle} {datetime.now():%H:%M:%S} | "
              f"累積船 {ships} 艘、靠港 {len(records)} 筆 | 目標港 {target}={tgt} | {top}",
              flush=True)
        time.sleep(PAUSE)

    print(f"[loop] 結束，共 {cycle} 輪。sightings：{settings.ais_sightings_file}", flush=True)


if __name__ == "__main__":
    main()
