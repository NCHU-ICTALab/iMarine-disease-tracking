"""aisstream 全球涵蓋普查：訂閱全世界，收一段時間，看船實際出現在哪些港口。

用法：.venv\\Scripts\\python scripts/survey_coverage.py [秒數]
輸出：主控台涵蓋表 + data/coverage_survey.json
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets

from app.config import settings

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0

# 全球主要港口 (unlocode, name, country, lat, lon)
PORTS = [
    ("CNSHA", "Shanghai", "CN", 31.23, 121.47), ("CNNGB", "Ningbo", "CN", 29.87, 121.54),
    ("CNSZX", "Shenzhen", "CN", 22.53, 114.06), ("CNCAN", "Guangzhou", "CN", 23.10, 113.25),
    ("CNTAO", "Qingdao", "CN", 36.07, 120.32), ("CNTXG", "Tianjin", "CN", 38.98, 117.70),
    ("CNXMN", "Xiamen", "CN", 24.48, 118.08), ("CNDLC", "Dalian", "CN", 38.92, 121.63),
    ("HKHKG", "Hong Kong", "HK", 22.30, 114.17),
    ("TWKHH", "Kaohsiung", "TW", 22.61, 120.28), ("TWKEL", "Keelung", "TW", 25.13, 121.74),
    ("TWTXG", "Taichung", "TW", 24.29, 120.52),
    ("KRPUS", "Busan", "KR", 35.10, 129.04), ("KRINC", "Incheon", "KR", 37.45, 126.60),
    ("KRKAN", "Gwangyang", "KR", 34.90, 127.70),
    ("JPTYO", "Tokyo", "JP", 35.62, 139.78), ("JPYOK", "Yokohama", "JP", 35.45, 139.66),
    ("JPNGO", "Nagoya", "JP", 35.05, 136.85), ("JPUKB", "Kobe", "JP", 34.68, 135.20),
    ("JPOSA", "Osaka", "JP", 34.63, 135.43),
    ("SGSIN", "Singapore", "SG", 1.26, 103.83), ("MYPKG", "Port Klang", "MY", 3.00, 101.39),
    ("MYTPP", "Tanjung Pelepas", "MY", 1.36, 103.55), ("THLCH", "Laem Chabang", "TH", 13.08, 100.88),
    ("THBKK", "Bangkok", "TH", 13.70, 100.58), ("VNSGN", "Ho Chi Minh", "VN", 10.77, 106.70),
    ("VNHPH", "Haiphong", "VN", 20.86, 106.68), ("PHMNL", "Manila", "PH", 14.58, 120.97),
    ("IDJKT", "Jakarta", "ID", -6.10, 106.88), ("IDSUB", "Surabaya", "ID", -7.20, 112.73),
    ("LKCMB", "Colombo", "LK", 6.95, 79.85), ("INMAA", "Chennai", "IN", 13.10, 80.30),
    ("INNSA", "Nhava Sheva/Mumbai", "IN", 18.95, 72.95), ("INMUN", "Mundra", "IN", 22.75, 69.70),
    ("INCCU", "Kolkata", "IN", 22.55, 88.30), ("BDCGP", "Chittagong", "BD", 22.31, 91.80),
    ("PKKHI", "Karachi", "PK", 24.84, 66.98),
    ("AEJEA", "Jebel Ali", "AE", 25.01, 55.06), ("SADMN", "Dammam", "SA", 26.50, 50.20),
    ("SAJED", "Jeddah", "SA", 21.50, 39.17), ("OMSLL", "Salalah", "OM", 16.93, 54.00),
    ("QAHMD", "Hamad", "QA", 25.00, 51.60), ("IRBND", "Bandar Abbas", "IR", 27.15, 56.20),
    ("NLRTM", "Rotterdam", "NL", 51.95, 4.14), ("BEANR", "Antwerp", "BE", 51.28, 4.32),
    ("DEHAM", "Hamburg", "DE", 53.53, 9.93), ("DEBRV", "Bremerhaven", "DE", 53.55, 8.58),
    ("GBFXT", "Felixstowe", "GB", 51.95, 1.32), ("FRLEH", "Le Havre", "FR", 49.48, 0.10),
    ("ESVLC", "Valencia", "ES", 39.45, -0.32), ("ESALG", "Algeciras", "ES", 36.13, -5.44),
    ("ESBCN", "Barcelona", "ES", 41.35, 2.16), ("GRPIR", "Piraeus", "GR", 37.94, 23.64),
    ("ITGOA", "Genoa", "IT", 44.40, 8.90), ("ITGIT", "Gioia Tauro", "IT", 38.43, 15.90),
    ("FRMRS", "Marseille", "FR", 43.30, 5.36), ("PLGDN", "Gdansk", "PL", 54.40, 18.70),
    ("TRIST", "Istanbul", "TR", 41.00, 28.97),
    ("ZADUR", "Durban", "ZA", -29.87, 31.03), ("MAPTM", "Tangier Med", "MA", 35.88, -5.50),
    ("EGPSD", "Port Said", "EG", 31.25, 32.30), ("EGALY", "Alexandria", "EG", 31.20, 29.90),
    ("KEMBA", "Mombasa", "KE", -4.05, 39.67), ("NGLOS", "Lagos", "NG", 6.44, 3.40),
    ("TZDAR", "Dar es Salaam", "TZ", -6.83, 39.30), ("CIABJ", "Abidjan", "CI", 5.25, -4.00),
    ("ZACPT", "Cape Town", "ZA", -33.90, 18.43),
    ("USLAX", "Los Angeles", "US", 33.74, -118.26), ("USLGB", "Long Beach", "US", 33.75, -118.20),
    ("USNYC", "New York", "US", 40.67, -74.04), ("USSAV", "Savannah", "US", 32.08, -81.10),
    ("USHOU", "Houston", "US", 29.60, -94.98), ("USSEA", "Seattle", "US", 47.60, -122.34),
    ("CAVAN", "Vancouver", "CA", 49.29, -123.10), ("BRSSZ", "Santos", "BR", -23.98, -46.30),
    ("MXZLO", "Manzanillo", "MX", 19.05, -104.31), ("PABLB", "Balboa/Panama", "PA", 8.95, -79.56),
    ("COCTG", "Cartagena", "CO", 10.40, -75.50), ("PECLL", "Callao", "PE", -12.05, -77.15),
    ("AUSYD", "Sydney", "AU", -33.85, 151.20), ("AUMEL", "Melbourne", "AU", -37.83, 144.92),
    ("AUBNE", "Brisbane", "AU", -27.38, 153.17), ("NZAKL", "Auckland", "NZ", -36.84, 174.77),
]

# 只訂閱各港周邊小方框（一次連線可帶多個 bbox），大幅降低資料量、直接命中目標港
_BOX_D = 0.5
SURVEY_BOXES = [[[la - _BOX_D, lo - _BOX_D], [la + _BOX_D, lo + _BOX_D]]
                for _, _, _, la, lo in PORTS]


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*6371*math.asin(math.sqrt(a))


async def collect():
    sub = {"APIKey": settings.aisstream_api_key, "BoundingBoxes": SURVEY_BOXES,
           "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport",
                                  "ExtendedClassBPositionReport"]}
    ships = {}  # mmsi -> (lat, lon)
    total = 0
    deadline = time.monotonic() + SECONDS
    print(f"訂閱 {len(SURVEY_BOXES)} 個港區方框，收 {SECONDS:.0f}s …", flush=True)
    while time.monotonic() < deadline:
        try:
            async with websockets.connect("wss://stream.aisstream.io/v0/stream",
                                          open_timeout=30, ping_interval=None) as ws:
                await ws.send(json.dumps(sub))
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 60))
                    except asyncio.TimeoutError:
                        break
                    m = json.loads(raw)
                    md = m.get("MetaData", {})
                    mmsi = md.get("MMSI")
                    lat = md.get("latitude"); lon = md.get("longitude")
                    if mmsi is None or lat is None or lon is None:
                        continue
                    ships[str(mmsi)] = (lat, lon)
                    total += 1
        except Exception as e:  # noqa: BLE001
            print(f"  重連（{type(e).__name__}）", flush=True)
            await asyncio.sleep(4)
    return ships, total


def main():
    ships, total = asyncio.run(collect())
    print(f"收到 {total} 則位置、{len(ships)} 艘不重複船\n")

    # 每艘船對應最近港口（<=60km）
    port_ct = defaultdict(int)
    for lat, lon in ships.values():
        best = None; bestd = 60.0
        for code, name, ctry, plat, plon in PORTS:
            d = haversine(lat, lon, plat, plon)
            if d <= bestd:
                best, bestd = code, d
        if best:
            port_ct[best] += 1

    meta = {p[0]: p for p in PORTS}
    covered = sorted(port_ct.items(), key=lambda x: -x[1])
    print(f"=== aisstream 有涵蓋的港口（{len(covered)} 個）===")
    print(f"{'港口':22s}{'國':4s}{'船數':>6s}")
    for code, n in covered:
        _, name, ctry, _, _ = meta[code]
        print(f"{name[:20]:22s}{ctry:4s}{n:6d}  {code}")

    uncovered = [p for p in PORTS if p[0] not in port_ct]
    print(f"\n=== 無涵蓋（{len(uncovered)} 個）===")
    print(", ".join(f"{p[1]}({p[2]})" for p in uncovered))

    out = {"survey_seconds": SECONDS, "total_msgs": total, "unique_ships": len(ships),
           "covered": {c: n for c, n in covered},
           "uncovered": [p[0] for p in uncovered]}
    with open("data/coverage_survey.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n已寫入 data/coverage_survey.json")


if __name__ == "__main__":
    main()
