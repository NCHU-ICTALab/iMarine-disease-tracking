"""各涵蓋港區「放大」的船隻軌跡動畫（小倍數 small-multiples）。

大陸尺度看不出移動（船只在各港 ~50km 泡泡內動），故每個有涵蓋的港各放一個放大面板，
同步在 21h 時間軸上播放真實軌跡。也直觀呈現「涵蓋孤島」：每格是一座獨立的沿岸泡泡。

執行：.venv\\Scripts\\python scripts/make_track_panels_gif.py [--frame N]
輸出：docs/ais_21h_tracks_panels.gif
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon as MplPoly

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "tracks_log.jsonl"
LAND = ROOT / "data" / "ne_land.geojson"
OUT = ROOT / "docs" / "ais_21h_tracks_panels.gif"

BG, LANDC, LANDE, INK, INK2 = "#0A141E", "#1B2C3A", "#2C4658", "#E7EEF4", "#9DB0C0"

# 各放大面板：標題, (lat0,lat1,lon0,lon1)
PANELS = [
    ("釜山 · 南韓 KRPUS", (34.55, 35.55, 128.45, 129.85)),
    ("基隆／北台灣 TWKEL", (24.35, 25.85, 120.6, 122.65)),
    ("香港 · 華南 HKHKG", (21.85, 22.95, 113.45, 114.75)),
    ("新加坡 SGSIN", (0.85, 1.75, 103.35, 104.45)),
    ("東京灣 JPTYO/JPYOK", (34.85, 35.85, 139.35, 140.25)),
]

LEGEND = [("#E7B23C", "南韓"), ("#33C2D6", "台灣"), ("#46C892", "新加坡"),
          ("#E56F97", "香港·華南"), ("#74AEE8", "日本"), ("#8FA0B2", "其他")]

N_FRAMES = 150
FPS = 15
TRAIL_MIN = 60.0
GONE_MIN = 18.0
MAXGAP_MIN = 30.0


def flag_color(mmsi: str) -> str:
    p = mmsi[:3]
    if p in ("440", "441"): return "#E7B23C"
    if p == "416": return "#33C2D6"
    if p in ("563", "564", "565", "566"): return "#46C892"
    if p == "477" or p in ("412", "413", "414"): return "#E56F97"
    if p in ("431", "432"): return "#74AEE8"
    return "#8FA0B2"


def ensure_land():
    if LAND.exists(): return
    import httpx
    url = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
           "master/geojson/ne_50m_land.geojson")
    LAND.write_bytes(httpx.get(url, timeout=60, follow_redirects=True).content)


def draw_land(ax, box):
    y0, y1, x0, x1 = box
    g = json.load(open(LAND, encoding="utf-8"))
    def add_ring(coords):
        arr = np.asarray(coords)
        if arr.ndim != 2: return
        if arr[:, 0].max() < x0 or arr[:, 0].min() > x1: return
        if arr[:, 1].max() < y0 or arr[:, 1].min() > y1: return
        ax.add_patch(MplPoly(arr, closed=True, facecolor=LANDC,
                             edgecolor=LANDE, linewidth=0.7, zorder=1))
    for feat in g.get("features", []):
        geom = feat.get("geometry", {}); t = geom.get("type")
        if t == "Polygon":
            for ring in geom["coordinates"]: add_ring(ring)
        elif t == "MultiPolygon":
            for poly in geom["coordinates"]:
                for ring in poly: add_ring(ring)


def load_tracks():
    raw = defaultdict(list); tmin = tmax = None
    with open(LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                r = json.loads(line)
                if not r.get("t"): continue
                dt = datetime.fromisoformat(r["t"])
            except (ValueError, json.JSONDecodeError):
                continue
            raw[r["m"]].append((dt, r["y"], r["x"]))
            tmin = dt if tmin is None or dt < tmin else tmin
            tmax = dt if tmax is None or dt > tmax else tmax
    tracks = {}
    for m, pts in raw.items():
        pts.sort(key=lambda p: p[0])
        th = np.array([(p[0] - tmin).total_seconds() / 3600.0 for p in pts])
        tracks[m] = (th, np.array([p[1] for p in pts]), np.array([p[2] for p in pts]),
                     flag_color(m))
    span = (tmax - tmin).total_seconds() / 3600.0
    return tracks, tmin, span


def head_at(th, la, lo, T, gone_h, maxgap_h):
    idx = int(np.searchsorted(th, T))
    if idx == 0: return None
    if idx >= len(th):
        return (la[-1], lo[-1]) if T - th[-1] <= gone_h else None
    gap = th[idx] - th[idx - 1]
    if gap <= maxgap_h:
        f = (T - th[idx - 1]) / gap if gap > 0 else 0
        return (la[idx - 1] + f * (la[idx] - la[idx - 1]),
                lo[idx - 1] + f * (lo[idx] - lo[idx - 1]))
    return (la[idx - 1], lo[idx - 1]) if T - th[idx - 1] <= gone_h else None


def main():
    ensure_land()
    tracks, t0, span = load_tracks()
    print(f"船數 {len(tracks)}、時間跨度 {span:.1f}h")

    trail_h, gone_h, maxgap_h = TRAIL_MIN / 60, GONE_MIN / 60, MAXGAP_MIN / 60

    # 每個面板：預先算出「曾進入此框」的船清單
    def in_box(la, lo, box):
        y0, y1, x0, x1 = box
        return np.any((la >= y0) & (la <= y1) & (lo >= x0) & (lo <= x1))
    panel_ships = []
    for _, box in PANELS:
        subset = [m for m, (th, la, lo, c) in tracks.items() if in_box(la, lo, box)]
        panel_ships.append(subset)

    fig = plt.figure(figsize=(12.4, 8.6), dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.012, 0.955, "21 小時真實 AIS 船隻軌跡 · 各涵蓋港區放大",
             color=INK, fontsize=21, fontweight="bold", fontfamily="Microsoft JhengHei")
    fig.text(0.012, 0.915, "每條軌跡=一艘船(MMSI)的真實移動｜依船籍上色｜每格是一座獨立的沿岸涵蓋泡泡，"
                           "泡泡之間的公海沒有資料", color=INK2, fontsize=11.5,
             fontfamily="Microsoft JhengHei")
    # 圖例（彩色圓點 ● + 標籤）
    for i, (c, lab) in enumerate(LEGEND):
        fx = 0.012 + i * 0.078
        fig.text(fx, 0.055, "●", color=c, fontsize=13, va="center")
        fig.text(fx + 0.014, 0.055, lab, color=INK2, fontsize=10.5, va="center",
                 fontfamily="Microsoft JhengHei")
    clock = fig.text(0.988, 0.955, "", color=INK, fontsize=16, ha="right",
                     fontfamily="Consolas")
    counter = fig.text(0.988, 0.915, "", color="#33C2D6", fontsize=12.5, ha="right",
                       fontfamily="Microsoft JhengHei")

    # 面板位置（2 列 3 欄，第 6 格留給說明）
    axes = []
    L, Rp, gap = 0.012, 0.012, 0.018
    top, bot = 0.87, 0.11
    pw = (1 - L - Rp - 2 * gap) / 3
    ph = (top - bot - gap) / 2
    slots = [(0, 1), (1, 1), (2, 1), (0, 0), (1, 0)]  # (col, row) row1=上
    for (name, box), (col, row) in zip(PANELS, slots):
        x = L + col * (pw + gap)
        y = bot + row * (ph + gap)
        ax = fig.add_axes([x, y, pw, ph])
        y0, y1, x0, x1 = box
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        ax.set_aspect(1 / math.cos(math.radians((y0 + y1) / 2)))
        ax.set_facecolor("#0C1924")
        for s in ax.spines.values():
            s.set_color("#22333F")
        ax.set_xticks([]); ax.set_yticks([])
        draw_land(ax, box)
        ax.text(0.035, 0.94, name, transform=ax.transAxes, color=INK, fontsize=12,
                va="top", fontweight="bold", fontfamily="Microsoft JhengHei")
        axes.append(ax)

    # 第 6 格：說明文字
    x = L + 2 * (pw + gap); y = bot
    info = fig.add_axes([x, y, pw, ph]); info.axis("off")
    info.text(0.02, 0.9, "為什麼分成一格一格？", color=INK, fontsize=12.5, va="top",
              fontweight="bold", fontfamily="Microsoft JhengHei", transform=info.transAxes)
    info.text(0.02, 0.72,
              "免費 aisstream 靠岸上志工接收站（VHF ~40–75km）。\n"
              "每個港是一座獨立涵蓋泡泡：看得到船進出港、\n"
              "操船、等錨的真實軌跡，但船一離開泡泡就消失。\n\n"
              "泡泡之間的公海完全沒有資料 → 21 小時內沒有\n"
              "任何一條跨港的遠洋航線被記錄到。\n\n"
              "要看完整跨國航線，需付費／衛星 AIS。",
              color=INK2, fontsize=10.3, va="top", linespacing=1.5,
              fontfamily="Microsoft JhengHei", transform=info.transAxes)

    dynamic = []

    def update(frame):
        for a in dynamic: a.remove()
        dynamic.clear()
        T = (frame / (N_FRAMES - 1)) * span
        total_active = 0
        for ax, subset in zip(axes, panel_ships):
            segs, cols, hx, hy, hc = [], [], [], [], []
            for m in subset:
                th, la, lo, c = tracks[m]
                head = head_at(th, la, lo, T, gone_h, maxgap_h)
                if head is None: continue
                total_active += 1
                mask = (th >= T - trail_h) & (th <= T)
                xs = list(lo[mask]) + [head[1]]; ys = list(la[mask]) + [head[0]]
                if len(xs) >= 2:
                    segs.append(np.column_stack([xs, ys])); cols.append(c)
                hx.append(head[1]); hy.append(head[0]); hc.append(c)
            if segs:
                lc = LineCollection(segs, colors=cols, linewidths=1.0, alpha=0.55, zorder=4)
                ax.add_collection(lc); dynamic.append(lc)
            if hx:
                dynamic.append(ax.scatter(hx, hy, s=17, c=hc, alpha=0.95,
                                          edgecolors="white", linewidths=0.35, zorder=6))
        cur = t0 + timedelta(hours=T)
        clock.set_text(f"T+{T:04.1f}h  {cur:%m/%d %H:%M} UTC")
        counter.set_text(f"航行中 {total_active} 艘")
        return dynamic + [clock, counter]

    if "--frame" in sys.argv:
        update(int(sys.argv[sys.argv.index("--frame") + 1]))
        fig.savefig(ROOT / "docs" / "_panels_frame.png", facecolor=BG)
        print("frame saved"); return

    print("算圖中…")
    anim = FuncAnimation(fig, update, frames=N_FRAMES, blit=False)
    OUT.parent.mkdir(exist_ok=True)
    anim.save(OUT, writer=PillowWriter(fps=FPS))
    print(f"完成：{OUT} ({OUT.stat().st_size/1e6:.1f} MB, {N_FRAMES}f @ {FPS}fps)")


if __name__ == "__main__":
    main()
