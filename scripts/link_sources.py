"""串聯兩來源：MOTC 台灣抵港船 × aisstream 外國 hub sightings（用 MMSI join）。

對每艘在台灣被 MOTC 拍到的船，回查它在 aisstream 外國 hub 方框內、時間早於台灣
抵達、且在 track_lookback_days 內的最近一筆 sighting → 即真實「前一外國港」。

用法：.venv\\Scripts\\python scripts/link_sources.py
輸出：data/linked_arrivals.json + 主控台摘要
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MOTC = Path(settings.motc_sightings_file)
TRACKS = ROOT / "data" / "tracks_log.jsonl"
NAMES = ROOT / "data" / "tracks_names.json"
OUT = ROOT / "data" / "linked_arrivals.json"

# 外國 hub 方框（排除台灣）：(UNLOCODE, name, lat0, lat1, lon0, lon1)
FOREIGN_HUBS = [
    ("KRPUS", "釜山", 34.6, 35.6, 128.5, 129.7),
    ("HKHKG", "香港", 21.8, 22.8, 113.7, 114.7),
    ("SGSIN", "新加坡", 0.8, 1.7, 103.3, 104.4),
    ("JPTYO", "東京灣", 35.0, 35.9, 139.3, 140.2),
]


def hub_of(lat: float, lon: float) -> str | None:
    for code, _, y0, y1, x0, x1 in FOREIGN_HUBS:
        if y0 <= lat <= y1 and x0 <= lon <= x1:
            return code
    return None


def parse(t: str | None) -> datetime | None:
    if not t:
        return None
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def load_foreign_sightings() -> dict[str, list[tuple[datetime, str]]]:
    """從 tracks_log 推導 {mmsi: [(time, hub_code), …]}（只留外國 hub 點）。"""
    out: dict[str, list[tuple[datetime, str]]] = {}
    if not TRACKS.exists():
        return out
    with open(TRACKS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            hub = hub_of(r["y"], r["x"])
            dt = parse(r.get("t"))
            if hub and dt:
                out.setdefault(r["m"], []).append((dt, hub))
    for m in out:
        out[m].sort()
    return out


def main() -> None:
    if not MOTC.exists():
        sys.exit(f"找不到 {MOTC}；請先跑 collect_motc.py。")
    motc = json.load(open(MOTC, encoding="utf-8")).get("ships", {})
    foreign = load_foreign_sightings()
    names = {}
    if NAMES.exists():
        try:
            names = json.load(open(NAMES, encoding="utf-8"))
        except Exception:
            names = {}
    lookback = timedelta(days=settings.track_lookback_days)

    linked = []
    for mmsi, sh in motc.items():
        fs = foreign.get(mmsi)
        if not fs:
            continue
        # 台灣抵達時間：取該船各台灣港最早的 first_seen
        arrivals = [(port, parse(c["first_seen"]))
                    for port, c in sh.get("ports", {}).items()]
        arrivals = [(p, t) for p, t in arrivals if t]
        if not arrivals:
            continue
        tw_port, tw_arr = min(arrivals, key=lambda x: x[1])
        # 台灣抵達前、lookback 內、最近一筆外國 hub sighting
        cands = [(t, hub) for t, hub in fs if t < tw_arr and (tw_arr - t) <= lookback]
        if not cands:
            continue
        prev_t, prev_hub = max(cands, key=lambda x: x[0])
        linked.append({
            "mmsi": mmsi,
            "imo": sh.get("imo"),
            "name": sh.get("name") or names.get(mmsi),
            "prev_foreign_port": prev_hub,
            "prev_seen_utc": prev_t.isoformat(),
            "tw_port": tw_port,
            "tw_arrival_utc": tw_arr.isoformat(),
            "gap_hours": round((tw_arr - prev_t).total_seconds() / 3600, 1),
        })

    linked.sort(key=lambda x: x["tw_arrival_utc"], reverse=True)
    OUT.write_text(json.dumps(linked, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"MOTC 台灣船 {len(motc)}、aisstream 有外國 hub 點的船 {len(foreign)}")
    print(f"=== 串聯成功（含前一外國港）：{len(linked)} 艘 ===")
    from collections import Counter
    by_port = Counter(x["prev_foreign_port"] for x in linked)
    by_tw = Counter(x["tw_port"] for x in linked)
    print("  前一外國港分布:", dict(by_port))
    print("  台灣抵達港分布:", dict(by_tw))
    print("  範例（最多 15）:")
    for x in linked[:15]:
        print(f"    {str(x['name'])[:20]:20s} IMO={str(x['imo']):>8s} "
              f"{x['prev_foreign_port']} → {x['tw_port']}  (航程 {x['gap_hours']}h)")
    print(f"\n已寫入 {OUT}")


if __name__ == "__main__":
    main()
