"""用 24 小時真實觀測資料做動畫 GIF。

底圖：東亞「有涵蓋走廊」海岸線（Natural Earth 50m）。
光點：每筆真實靠港（data/ais_sightings.json 的 arrival），依其真實觀測時刻在
24 小時時間軸上一顆顆亮起，依船籍/港區上色。剛觀測到的會閃亮，之後轉為穩定微光。

執行：.venv\\Scripts\\python scripts/make_observation_gif.py
輸出：docs/ais_24h_observation.gif
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Polygon as MplPoly

ROOT = Path(__file__).resolve().parent.parent
SIGHT = ROOT / "data" / "ais_sightings.json"
LAND = ROOT / "data" / "ne_land.geojson"
OUT = ROOT / "docs" / "ais_24h_observation.gif"

# 地圖範圍（涵蓋走廊：新加坡~1N 到 釜山/東京~36N）
LON0, LON1, LAT0, LAT1 = 99.0, 142.0, -3.0, 40.0

# 港區 → (顏色, 標籤)
REGION = {
    "KRPUS": ("#E7B23C", "南韓 · 釜山"),
    "TWKEL": ("#33C2D6", "台灣 · 基隆"),
    "TWKHH": ("#33C2D6", "台灣"),
    "TWTXG": ("#33C2D6", "台灣"),
    "SGSIN": ("#46C892", "新加坡"),
    "HKHKG": ("#E56F97", "香港 · 華南"),
    "CNSZX": ("#E56F97", "香港 · 華南"),
    "JPTYO": ("#74AEE8", "日本 · 東京灣"),
    "JPYOK": ("#74AEE8", "日本 · 東京灣"),
}
DEFAULT_COLOR = "#8FA0B2"

BG = "#0A141E"
LANDC = "#1A2A38"
LANDE = "#274052"
INK = "#E7EEF4"
INK2 = "#9DB0C0"

N_FRAMES = 112       # ~ 每格 ~13 分鐘
FPS = 14
FLASH_HOURS = 1.5    # 觀測後多久內算「剛亮起」


def load_ports() -> dict[str, tuple[float, float]]:
    ports = {}
    with open(ROOT / "data" / "ports_seed.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("lat") and row.get("lon"):
                ports[row["unlocode"].strip().upper()] = (float(row["lat"]), float(row["lon"]))
    return ports


def load_events(ports):
    """回傳 (lon, lat, color, t_hours) 四個 array；t_hours 為相對 24h 起點的小時。"""
    d = json.load(open(SIGHT, encoding="utf-8"))
    rows = []
    for s in d.get("ships", {}).values():
        for port, call in s.get("calls", {}).items():
            a = call.get("arrival")
            if not a or port not in ports:
                continue
            try:
                dt = datetime.fromisoformat(a)
            except ValueError:
                continue
            rows.append((port, dt))
    if not rows:
        sys.exit("no events found in sightings")
    tmax = max(dt for _, dt in rows)
    t0 = tmax - timedelta(hours=24)
    rng = np.random.default_rng(42)
    lon, lat, col, th = [], [], [], []
    for port, dt in rows:
        plat, plon = ports[port]
        # 在港口周邊抖動，形成光暈群（視覺化慣例）
        jx, jy = rng.normal(0, 0.28), rng.normal(0, 0.28)
        lon.append(plon + jx)
        lat.append(plat + jy)
        col.append(REGION.get(port, (DEFAULT_COLOR, "其他"))[0])
        # 早於 24h 窗口者夾到 0（開場即在）
        hrs = max(0.0, (dt - t0).total_seconds() / 3600.0)
        th.append(min(hrs, 24.0))
    return (np.array(lon), np.array(lat), np.array(col, dtype=object),
            np.array(th), t0)


def ensure_land():
    """底圖不存在時，自動抓 Natural Earth 50m 陸地 GeoJSON。"""
    if LAND.exists():
        return
    import httpx
    url = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
           "master/geojson/ne_50m_land.geojson")
    print("下載海岸線底圖…")
    r = httpx.get(url, timeout=60, follow_redirects=True)
    r.raise_for_status()
    LAND.write_bytes(r.content)


def draw_land(ax):
    g = json.load(open(LAND, encoding="utf-8"))
    def add_ring(coords):
        arr = np.asarray(coords)
        if arr.ndim != 2:
            return
        # 粗略 bbox 篩選
        if arr[:, 0].max() < LON0 or arr[:, 0].min() > LON1: return
        if arr[:, 1].max() < LAT0 or arr[:, 1].min() > LAT1: return
        ax.add_patch(MplPoly(arr, closed=True, facecolor=LANDC,
                             edgecolor=LANDE, linewidth=0.6, zorder=1))
    for feat in g.get("features", []):
        geom = feat.get("geometry", {})
        t = geom.get("type")
        if t == "Polygon":
            for ring in geom["coordinates"]:
                add_ring(ring)
        elif t == "MultiPolygon":
            for poly in geom["coordinates"]:
                for ring in poly:
                    add_ring(ring)


def main():
    ensure_land()
    ports = load_ports()
    lon, lat, col, th, t0 = load_events(ports)
    total = len(lon)
    print(f"事件數：{total}，時間起點 t0(UTC)={t0:%Y-%m-%d %H:%M}")

    fig = plt.figure(figsize=(8.0, 8.4), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(LON0, LON1); ax.set_ylim(LAT0, LAT1)
    ax.set_aspect(1.15)
    ax.axis("off")

    # 經緯格線
    for x in range(100, 141, 10):
        ax.axvline(x, color="#16283680" if False else "#152634", lw=0.5, zorder=0)
    for y in range(0, 41, 10):
        ax.axhline(y, color="#152634", lw=0.5, zorder=0)

    draw_land(ax)

    # 標題與圖例（靜態）
    ax.text(0.035, 0.965, "24 小時真實 AIS 觀測", transform=ax.transAxes,
            color=INK, fontsize=20, fontweight="bold", va="top",
            fontfamily="Microsoft JhengHei")
    ax.text(0.035, 0.923, "aisstream.io 即時串流 · 有涵蓋走廊 · 每點=一筆真實靠港",
            transform=ax.transAxes, color=INK2, fontsize=10.5, va="top",
            fontfamily="Microsoft JhengHei")
    # 圖例放在右側開闊海域（菲律賓海），避開任何港區光點
    legend_items = [("#E7B23C", "南韓 釜山"), ("#33C2D6", "台灣 基隆"),
                    ("#46C892", "新加坡"), ("#E56F97", "香港 華南"),
                    ("#74AEE8", "日本 東京灣"), ("#8FA0B2", "其他")]
    for i, (c, lab) in enumerate(legend_items):
        yy = 0.34 - i * 0.036
        ax.scatter([0.775], [yy], s=70, c=c, transform=ax.transAxes,
                   edgecolors="none", zorder=6)
        ax.text(0.80, yy, lab, transform=ax.transAxes, color=INK2,
                fontsize=10, va="center", fontfamily="Microsoft JhengHei")

    clock = ax.text(0.965, 0.965, "", transform=ax.transAxes, color=INK,
                    fontsize=15, va="top", ha="right", fontfamily="Consolas")
    counter = ax.text(0.035, 0.885, "", transform=ax.transAxes, color="#33C2D6",
                      fontsize=13, va="top", ha="left", fontfamily="Microsoft JhengHei")
    ax.text(0.965, 0.035, "資料：2026-07 · 高雄本身 0 涵蓋", transform=ax.transAxes,
            color="#5E7286", fontsize=9, ha="right", fontfamily="Microsoft JhengHei")

    dynamic = []

    def update(frame):
        for art in dynamic:
            art.remove()
        dynamic.clear()
        t = (frame / (N_FRAMES - 1)) * 24.0
        vis = th <= t
        nvis = int(vis.sum())
        age = t - th
        fresh = vis & (age <= FLASH_HOURS)
        old = vis & (age > FLASH_HOURS)

        # 穩定微光：暈 + 核
        if old.any():
            dynamic.append(ax.scatter(lon[old], lat[old], s=95, c=list(col[old]),
                                      alpha=0.16, edgecolors="none", zorder=3))
            dynamic.append(ax.scatter(lon[old], lat[old], s=9, c=list(col[old]),
                                      alpha=0.85, edgecolors="none", zorder=5))
        # 剛亮起：大光暈 + 白核閃爍
        if fresh.any():
            a = 1.0 - (age[fresh] / FLASH_HOURS)  # 0..1 新→舊
            dynamic.append(ax.scatter(lon[fresh], lat[fresh], s=340 * a + 60,
                                      c=list(col[fresh]), alpha=0.22,
                                      edgecolors="none", zorder=4))
            dynamic.append(ax.scatter(lon[fresh], lat[fresh], s=26,
                                      c=list(col[fresh]), alpha=0.95,
                                      edgecolors="white", linewidths=0.5, zorder=6))

        cur = t0 + timedelta(hours=t)
        clock.set_text(f"T+{t:04.1f}h  {cur:%m/%d %H:%M} UTC")
        counter.set_text(f"觀測到 {nvis} / {total} 艘")
        return dynamic + [clock, counter]

    # 輸出一張中段影格供檢視
    if "--frame" in sys.argv:
        update(72)
        fig.savefig(ROOT / "docs" / "_frame_check.png", facecolor=BG)
        print("frame saved")
        return

    print("算圖中…")
    anim = FuncAnimation(fig, update, frames=N_FRAMES, blit=False)
    OUT.parent.mkdir(exist_ok=True)
    anim.save(OUT, writer=PillowWriter(fps=FPS))
    size = OUT.stat().st_size / 1e6
    print(f"完成：{OUT}  ({size:.1f} MB, {N_FRAMES} frames @ {FPS}fps)")


if __name__ == "__main__":
    main()
