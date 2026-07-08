"""長時間記錄每艘船（以 MMSI 編號）的移動軌跡。

與 collect_ais_loop.py 不同：這支**持續連線**、記錄每艘船隨時間的**逐點位置**
（不是只存靠港點），供之後生成軌跡動畫。

- 訂閱 config 的多區域 bounding box。
- 每艘船每 MIN_INTERVAL 秒最多記一點（下採樣，控制檔案大小）。
- 逐點以 JSONL 追加到 data/tracks_log.jsonl：{"m":MMSI,"t":ISO,"y":lat,"x":lon}
- 船名另存 data/tracks_names.json。
- 斷線自動重連，定期 flush；跑到指定時數為止。

用法：.venv\\Scripts\\python -u scripts/collect_tracks.py [時數] [每船最短間隔秒]
      例：.venv\\Scripts\\python -u scripts/collect_tracks.py 21 45
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tracks_log.jsonl"
NAMES = ROOT / "data" / "tracks_names.json"
WS_URL = "wss://stream.aisstream.io/v0/stream"

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 21.0
MIN_INTERVAL = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0

_POS_TYPES = ["PositionReport", "StandardClassBPositionReport",
              "ExtendedClassBPositionReport"]


def _parse_time(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.split(".")[0].split(" +")[0].strip())
    except (ValueError, IndexError):
        return None


async def run():
    deadline = time.monotonic() + HOURS * 3600
    end_wall = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sub = {
        "APIKey": settings.aisstream_api_key,
        "BoundingBoxes": settings.ais_bbox,
        "FilterMessageTypes": _POS_TYPES,
    }
    import websockets

    last_seen: dict[str, float] = {}
    names: dict[str, str] = {}
    if NAMES.exists():
        try:
            names = json.load(open(NAMES, encoding="utf-8"))
        except Exception:
            names = {}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    f = open(OUT, "a", encoding="utf-8")
    count = 0
    started = time.monotonic()
    last_report = started
    print(f"[tracks] 開始，預計跑 {HOURS:.0f} 小時（每船最短間隔 {MIN_INTERVAL:.0f}s），"
          f"輸出 {OUT.name}", flush=True)

    while time.monotonic() < deadline:
        try:
            async with websockets.connect(WS_URL, open_timeout=30,
                                          ping_interval=None, close_timeout=5) as ws:
                await ws.send(json.dumps(sub))
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 120))
                    except asyncio.TimeoutError:
                        # 120s 無資料視為連線異常 → 跳出重連
                        print("[tracks] 120s 無資料，重連", flush=True)
                        break
                    msg = json.loads(raw)
                    meta = msg.get("MetaData", {})
                    mmsi = meta.get("MMSI")
                    lat = meta.get("latitude")
                    lon = meta.get("longitude")
                    if mmsi is None or lat is None or lon is None:
                        continue
                    mmsi = str(mmsi)
                    now = time.monotonic()
                    if now - last_seen.get(mmsi, -1e9) < MIN_INTERVAL:
                        continue
                    last_seen[mmsi] = now
                    t = _parse_time(meta.get("time_utc"))
                    rec = {"m": mmsi, "t": (t.isoformat() if t else None),
                           "y": round(float(lat), 5), "x": round(float(lon), 5)}
                    f.write(json.dumps(rec, separators=(",", ":")) + "\n")
                    count += 1
                    nm = (meta.get("ShipName") or "").strip()
                    if nm and mmsi not in names:
                        names[mmsi] = nm

                    if now - last_report >= 120:
                        f.flush()
                        json.dump(names, open(NAMES, "w", encoding="utf-8"),
                                  ensure_ascii=False)
                        mb = OUT.stat().st_size / 1e6
                        el = (now - started) / 3600
                        print(f"[tracks] +{el:4.1f}h | 點數 {count} | 船數 {len(last_seen)} "
                              f"| {mb:.1f}MB | {datetime.now():%H:%M:%S}", flush=True)
                        last_report = now
        except Exception as e:  # noqa: BLE001  斷線／握手逾時 → 重連
            print(f"[tracks] 連線中斷：{type(e).__name__}: {str(e)[:60]}；5s 後重連", flush=True)
            await asyncio.sleep(5)

    f.flush(); f.close()
    json.dump(names, open(NAMES, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[tracks] 結束。總點數 {count}、船數 {len(last_seen)}、"
          f"檔案 {OUT.stat().st_size/1e6:.1f}MB", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
