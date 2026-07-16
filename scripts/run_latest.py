"""抓一次最新資料 + 全量重算 + 輸出結果（等同 POST /jobs/refresh）。

執行：python scripts/run_latest.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings                  # noqa: E402
from app.db import SessionLocal, init_db          # noqa: E402
from app.governance.ports import load_ports_from_seed  # noqa: E402
from app.pipeline import refresh_outbreaks, refresh_ais, assess_all  # noqa: E402
from app.service.presenter import clean_bundle    # noqa: E402
from app.models import Notification               # noqa: E402

# 真實來源（aisstream / motc 串聯）的靠港時間是「現在」，用當下時間評估；
# 模擬資料的時間停在 2026-07 上旬，沿用固定 AS_OF 讓 demo 可重現。
AS_OF = datetime(2026, 7, 3) if settings.ais_provider.lower() == "mock" else datetime.utcnow()


def main() -> None:
    init_db()
    with SessionLocal() as s:
        load_ports_from_seed(s)

        print("[1/3] 抓取最新疫情資料（疾管署 + WHO）...")
        ob = refresh_outbreaks(s)
        print("      疾管署:", ob.get("cdc"))
        print("      WHO   :", ob.get("who"))

        src = {"aisstream": "aisstream 即時串流", "motc": "MOTC×aisstream 串聯（真實）"}.get(
            settings.ais_provider.lower(), "模擬船")
        print(f"[2/3] 匯入 AIS 靠港紀錄（{src}）...")
        n = refresh_ais(s)
        print(f"      新增靠港紀錄: {n}")

        print("[3/3] 全量風險評估 + 高風險自動推播...")
        results = assess_all(s, AS_OF)
        bundle = clean_bundle(s, results, as_of=AS_OF)

        # 主控台只印 ASCII（避免亂碼）；完整中文看 demo_output.json
        print("\n=== 評估結果（依風險排序）===")
        for a in bundle["assessments"]:
            print(f"  {a['ship_code']:14s} prev={str(a['prev_port']):6s} "
                  f"{a['risk_level']:8s} score={a['score']:.3f} "
                  f"matches={len(a['matched_outbreaks'])}")

        notes = s.query(Notification).count()
        print(f"\n推播紀錄（mock）累計: {notes}")

        dest = ROOT / "demo_output.json"
        dest.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"完整結果已寫入: {dest.name}")


if __name__ == "__main__":
    main()
