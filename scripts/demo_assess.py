"""示範：對 mock 進港船跑完整評估，印出風險與可解釋明細。

執行：python scripts/demo_assess.py
"""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.db import SessionLocal          # noqa: E402
from app.models import Ship, Notification  # noqa: E402
from app.pipeline import assess_all       # noqa: E402


def main() -> None:
    as_of = datetime(2026, 7, 3)
    with SessionLocal() as s:
        results = assess_all(s, as_of)
        for a in sorted(results, key=lambda x: -x.score):
            sh = s.get(Ship, a.ship_id)
            print(
                f"{sh.ship_code:14s} prev={str(a.prev_port):6s} "
                f"level={a.risk_level:8s} score={a.score:.3f} "
                f"matches={len(a.matched_events or [])}"
            )
            for m in (a.matched_events or [])[:3]:
                disease = m["disease"][:26]
                print(
                    f"    - {m['port']}/{m['country']} {disease:26s} "
                    f"rel={m['relation']:16s} gap={m['days_gap']:>4} "
                    f"score={m['event_score']:.3f}"
                )
                print(f"        dims={m['dimensions']}  decay={m['proximity_decay']}")
            if a.recommendation:
                print(f"    建議: {a.recommendation}")

        n_notes = s.query(Notification).count()
        print(f"\n[notifier] 推播紀錄（mock）總數: {n_notes}")


if __name__ == "__main__":
    main()
