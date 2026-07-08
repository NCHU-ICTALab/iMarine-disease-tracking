"""用軌跡紀錄（data/tracks_log.jsonl）生成「船隻移動軌跡」動畫 GIF。

每艘船（MMSI）依其逐點位置隨時間在地圖上移動，拖著淡出的尾跡；依船籍上色。
底圖用東亞「有涵蓋走廊」海岸線（Natural Earth 50m）。

執行：.venv\\Scripts\\python scripts/make_track_gif.py [--frame N]
輸出：docs/ais_21h_tracks.gif
"""
from __future__ import annotations

import json
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
OUT = ROOT / "docs" / "ais_21h_tracks.gif"

LON0, LON1, LAT0, LAT1 = 99.0, 142.0, -3.0, 40.0
BG, LANDC, LANDE, INK, INK2 = "#0A141E", "#1A2A38", "#274052", "#E7EEF4", "#9DB0C0"

# 船籍（MMSI 前三碼 MID）→ 顏色
def flag_color(mmsi: str) -> str:
    p = mmsi[:3]
    if p in ("440", "441"): return "#E7B23C"   # 南韓
    if p == "416": return "#33C2D6"            # 台灣
    if p in ("563", "564", "565", "566"): return "#46C892"  # 新加坡
    if p == "477": return "#E56F97"            # 香港
    if p in ("412", "413", "414"): return "#E56F97"         # 中國/華南
    if p in ("431", "432"): return "#74AEE8"   # 日本
    return "#8FA0B2"

LEGEND = [("#E7B23C", "南韓"), ("#33C2D6", "台灣"), ("#46C892", "新加坡"),
          ("#E56F97", "香港 · 華南"), ("#74AEE8", "日本"), ("#8FA0B2", "其他")]

N_FRAMES = 150
FPS = 15
TRAIL_MIN = 45.0     # 尾跡保留分鐘
GONE_MIN = 15.0      # 超過幾分鐘沒點視為離開涵蓋
MAXGAP_MIN = 25.0    # 兩點間隔小於此值才內插頭部位置


def ensure_land():
    if LAND.exists():
        return
    import httpx
    url = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
           "master/geojson/ne_50m_land.geojson")
    print("下載海岸線底圖…")
    LAND.write_bytes(httpx.get(url, timeout=60, follow_redirects=True).content)


def draw_land(ax):
    g = json.load(open(LAND, encoding="utf-8"))
    def add_ring(coords):
        arr = np.asarray(coords)
        if arr.ndim != 2: return
        if arr[:, 0].max() < LON0 or arr[:, 0].min() > LON1: return
        if arr[:, 1].max() < LAT0 or arr[:, 1].min() > LAT1: return
        ax.add_patch(MplPoly(arr, closed=True, facecolor=LANDC,
                             edgecolor=LANDE, linewidth=0.6, zorder=1))
    for feat in g.get("features", []):
        geom = feat.get("geometry", {}); t = geom.get("type")
        if t == "Polygon":
            for ring in geom["coordinates"]: add_ring(ring)
        elif t == "MultiPolygon":
            for poly in geom["coordinates"]:
                for ring in poly: add_ring(ring)


def load_tracks():
    """回傳 {mmsi: (t_hours ndarray, lat ndarray, lon ndarray)} 與 t0, span_h。"""
    raw = defaultdict(list)
    tmin = tmax = None
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
        la = np.array([p[1] for p in pts]); lo = np.array([p[2] for p in pts])
        # 只留在地圖範圍內、且有 2 點以上的（能畫出移動）
        tracks[m] = (th, la, lo)
    span = (tmax - tmin).total_seconds() / 3600.0
    return tracks, tmin, span


def main():
    ensure_land()
    tracks, t0, span = load_tracks()
    npts = sum(len(v[0]) for v in tracks.values())
    print(f"船數 {len(tracks)}、總點數 {npts}、時間跨度 {span:.1f}h，t0={t0:%Y-%m-%d %H:%M}")
    if span < 0.05:
        sys.exit("資料時間跨度太短，稍後再產生。")

    trail_h = TRAIL_MIN / 60.0; gone_h = GONE_MIN / 60.0; maxgap_h = MAXGAP_MIN / 60.0
    colors = {m: flag_color(m) for m in tracks}

    fig = plt.figure(figsize=(8.0, 8.4), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor(BG)
    ax.set_xlim(LON0, LON1); ax.set_ylim(LAT0, LAT1); ax.set_aspect(1.15); ax.axis("off")
    for x in range(100, 141, 10): ax.axvline(x, color="#152634", lw=0.5, zorder=0)
    for y in range(0, 41, 10): ax.axhline(y, color="#152634", lw=0.5, zorder=0)
    draw_land(ax)

    ax.text(0.035, 0.965, "21 小時真實 AIS 船隻軌跡", transform=ax.transAxes, color=INK,
            fontsize=20, fontweight="bold", va="top", fontfamily="Microsoft JhengHei")
    ax.text(0.035, 0.923, "aisstream.io · 每條軌跡=一艘船(MMSI)的真實移動 · 依船籍上色",
            transform=ax.transAxes, color=INK2, fontsize=10.5, va="top",
            fontfamily="Microsoft JhengHei")
    for i, (c, lab) in enumerate(LEGEND):
        yy = 0.34 - i * 0.036
        ax.scatter([0.775], [yy], s=70, c=c, transform=ax.transAxes, edgecolors="none", zorder=6)
        ax.text(0.80, yy, lab, transform=ax.transAxes, color=INK2, fontsize=10,
                va="center", fontfamily="Microsoft JhengHei")
    clock = ax.text(0.965, 0.965, "", transform=ax.transAxes, color=INK, fontsize=15,
                    va="top", ha="right", fontfamily="Consolas")
    counter = ax.text(0.035, 0.885, "", transform=ax.transAxes, color="#33C2D6", fontsize=13,
                      va="top", ha="left", fontfamily="Microsoft JhengHei")
    ax.text(0.965, 0.035, "資料：2026-07 · 有涵蓋走廊", transform=ax.transAxes,
            color="#5E7286", fontsize=9, ha="right", fontfamily="Microsoft JhengHei")

    dynamic = []

    def head_at(th, la, lo, T):
        """回傳在時間 T 的頭部位置 (lat,lon)，不在涵蓋則 None。"""
        idx = int(np.searchsorted(th, T))
        if idx == 0:
            return None
        if idx >= len(th):
            return (la[-1], lo[-1]) if T - th[-1] <= gone_h else None
        gap = th[idx] - th[idx - 1]
        if gap <= maxgap_h:
            f = (T - th[idx - 1]) / gap if gap > 0 else 0
            return (la[idx - 1] + f * (la[idx] - la[idx - 1]),
                    lo[idx - 1] + f * (lo[idx] - lo[idx - 1]))
        return (la[idx - 1], lo[idx - 1]) if T - th[idx - 1] <= gone_h else None

    def update(frame):
        for a in dynamic:
            a.remove()
        dynamic.clear()
        T = (frame / (N_FRAMES - 1)) * span
        segs, seg_cols, hx, hy, hc = [], [], [], [], []
        active = 0
        for m, (th, la, lo) in tracks.items():
            head = head_at(th, la, lo, T)
            if head is None:
                continue
            active += 1
            c = colors[m]
            mask = (th >= T - trail_h) & (th <= T)
            xs = list(lo[mask]); ys = list(la[mask])
            xs.append(head[1]); ys.append(head[0])
            if len(xs) >= 2:
                pts = np.column_stack([xs, ys])
                segs.append(pts); seg_cols.append(c)
            hx.append(head[1]); hy.append(head[0]); hc.append(c)
        if segs:
            lc = LineCollection(segs, colors=seg_cols, linewidths=0.9, alpha=0.5, zorder=4)
            ax.add_collection(lc); dynamic.append(lc)
        if hx:
            dynamic.append(ax.scatter(hx, hy, s=13, c=hc, alpha=0.95,
                                      edgecolors="white", linewidths=0.3, zorder=6))
        cur = t0 + timedelta(hours=T)
        clock.set_text(f"T+{T:04.1f}h  {cur:%m/%d %H:%M} UTC")
        counter.set_text(f"航行中 {active} 艘")
        return dynamic + [clock, counter]

    if "--frame" in sys.argv:
        i = int(sys.argv[sys.argv.index("--frame") + 1])
        update(i)
        fig.savefig(ROOT / "docs" / "_track_frame.png", facecolor=BG)
        print("frame saved"); return

    print("算圖中…")
    anim = FuncAnimation(fig, update, frames=N_FRAMES, blit=False)
    OUT.parent.mkdir(exist_ok=True)
    anim.save(OUT, writer=PillowWriter(fps=FPS))
    print(f"完成：{OUT} ({OUT.stat().st_size/1e6:.1f} MB, {N_FRAMES}f @ {FPS}fps)")


if __name__ == "__main__":
    main()
