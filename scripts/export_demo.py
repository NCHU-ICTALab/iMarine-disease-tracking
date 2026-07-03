"""輸出乾淨的 demo JSON（workflow 標準輸出格式，與 API 一致）。

執行：python scripts/export_demo.py
輸出：demo_output.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import SessionLocal            # noqa: E402
from app.pipeline import assess_all        # noqa: E402
from app.service.presenter import clean_bundle  # noqa: E402

AS_OF = datetime(2026, 7, 3)


def main() -> None:
    with SessionLocal() as s:
        results = assess_all(s, AS_OF)
        bundle = clean_bundle(s, results, as_of=AS_OF)

    dest = ROOT / "demo_output.json"
    dest.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {dest}  ({len(bundle['assessments'])} ships)")


if __name__ == "__main__":
    main()
