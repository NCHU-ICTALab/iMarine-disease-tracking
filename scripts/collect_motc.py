"""台灣端輪詢：定時抓 MOTC（航港局）臺灣海域即時船位，累積台灣港靠港紀錄。

只用公開、免授權的地圖端點（當下船位）；禮貌輪詢（預設每 3 分鐘）。
偵測到船在台灣港（高雄/基隆/台中…座標鄰近 + 低船速）即記錄，供之後用 MMSI
與 aisstream 外國 hub sightings 串聯，還原真實「前一外國港」。

用法：.venv\\Scripts\\python -u scripts/collect_motc.py [時數]
      例：.venv\\Scripts\\python -u scripts/collect_motc.py 96
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.sources.ais_provider import _haversine_km, _load_port_coords  # noqa: E402

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 96.0

ROOT = Path(__file__).resolve().parent.parent
SIGHT = Path(settings.motc_sightings_file)
LOG = Path(settings.motc_log_file)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
           "Referer": "https://mpbais.motcmpb.gov.tw/"}

# 只取台灣港座標（TWKHH / TWKEL / TWTXG …）
TW_PORTS = {c: (la, lo) for c, (la, lo) in _load_port_coords().items() if c.startswith("TW")}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def nearest_tw_port(lat: float, lon: float, sog: float | None) -> str | None:
    if sog is not None and sog > settings.ais_port_max_sog:
        return None
    best, best_km = None, settings.ais_port_radius_km
    for code, (plat, plon) in TW_PORTS.items():
        d = _haversine_km(lat, lon, plat, plon)
        if d <= best_km:
            best, best_km = code, d
    return best


def load_sightings() -> dict:
    if SIGHT.exists():
        try:
            return json.load(open(SIGHT, encoding="utf-8"))
        except Exception:
            return {"ships": {}}
    return {"ships": {}}


def poll_once(store: dict, logf) -> dict:
    """打一次 MOTC，更新 store，回傳本輪各港在港數。"""
    r = httpx.get(settings.motc_ais_url, headers=HEADERS, timeout=40, verify=False)
    r.raise_for_status()
    feats = r.json().get("features", [])
    ships = store.setdefault("ships", {})
    t = now_iso()
    counts: dict[str, int] = {}
    for f in feats:
        p = f.get("properties", {})
        mmsi = str(p.get("MMSI", "")).strip()
        if not mmsi:
            continue
        lon, lat = f["geometry"]["coordinates"]
        port = nearest_tw_port(lat, lon, p.get("SOG"))
        if not port:
            continue
        counts[port] = counts.get(port, 0) + 1
        imo = str(p.get("IMO_Number", "")).strip()
        name = (p.get("ShipName") or "").strip()
        sh = ships.setdefault(mmsi, {"imo": None, "name": None, "ports": {}})
        sh["imo"] = sh["imo"] or (imo if imo and imo != "0" else None)
        sh["name"] = sh["name"] or (name or None)
        call = sh["ports"].get(port)
        if call:
            call["last_seen"] = t
        else:
            sh["ports"][port] = {"first_seen": t, "last_seen": t}
        logf.write(json.dumps({"m": mmsi, "port": port, "t": t,
                               "sog": p.get("SOG")}, separators=(",", ":")) + "\n")
    store["updated_at"] = t
    return counts


def main() -> None:
    deadline = time.monotonic() + HOURS * 3600
    store = load_sightings()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = open(LOG, "a", encoding="utf-8")
    print(f"[motc] 開始，預計輪詢 {HOURS:.0f} 小時（每 {settings.motc_poll_seconds:.0f}s 一次），"
          f"台灣港 {sorted(TW_PORTS)}", flush=True)

    poll = 0
    while time.monotonic() < deadline:
        poll += 1
        try:
            counts = poll_once(store, logf)
            logf.flush()
            with open(SIGHT, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=1)
            khh = counts.get("TWKHH", 0)
            top = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
            el = (time.monotonic() - (deadline - HOURS * 3600)) / 3600
            print(f"[motc] poll {poll} +{el:4.1f}h {datetime.now():%H:%M:%S} | "
                  f"累積船 {len(store['ships'])} | 本輪高雄 {khh} | {top}", flush=True)
        except Exception as e:  # noqa: BLE001  單輪失敗不中斷
            print(f"[motc] poll {poll} 失敗：{type(e).__name__}: {str(e)[:70]}", flush=True)

        # 睡到下一輪（同時尊重 deadline）
        end = time.monotonic() + settings.motc_poll_seconds
        while time.monotonic() < min(end, deadline):
            time.sleep(min(5.0, max(0.0, min(end, deadline) - time.monotonic())))
        if time.monotonic() >= deadline:
            break

    logf.close()
    print(f"[motc] 結束，共 {poll} 輪，累積 {len(store['ships'])} 艘。sightings: {SIGHT}", flush=True)


if __name__ == "__main__":
    main()
