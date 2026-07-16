"""一次性：連 aisstream.io 抓幾筆真實 AIS 訊息存成 sample，觀察資料結構。

用法：
    .venv\\Scripts\\python scripts/sample_aisstream.py [API_KEY] [秒數]
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

import websockets

API_KEY = sys.argv[1] if len(sys.argv) > 1 else ""
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
MAX_MSGS = 60

# 台灣周邊（含高雄港、台灣海峽、巴士海峽），[[lat,lon(SW)],[lat,lon(NE)]]
BOUNDING_BOXES = [[[20.0, 118.0], [26.5, 123.0]]]


async def main() -> None:
    url = "wss://stream.aisstream.io/v0/stream"
    sub = {
        "APIKey": API_KEY,
        "BoundingBoxes": BOUNDING_BOXES,
        # 不設 FilterMessageTypes → 收全部（PositionReport / ShipStaticData 等）
    }
    collected: list[dict] = []
    types: dict[str, int] = {}

    async with websockets.connect(url, ping_interval=None) as ws:
        await ws.send(json.dumps(sub))
        print(f"connected; collecting up to {MAX_MSGS} msgs / {DURATION}s ...")
        loop = asyncio.get_event_loop()
        start = loop.time()
        while loop.time() - start < DURATION and len(collected) < MAX_MSGS:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=DURATION)
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            mtype = msg.get("MessageType", "?")
            types[mtype] = types.get(mtype, 0) + 1
            collected.append(msg)

    out = {
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "bounding_boxes": BOUNDING_BOXES,
        "message_type_counts": types,
        "count": len(collected),
        "messages": collected,
    }
    path = "data/aisstream_sample.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"types: {types}")
    print(f"saved {len(collected)} messages -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
