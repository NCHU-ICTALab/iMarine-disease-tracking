"""初始化資料庫並載入基礎主檔（港口）。

執行：python scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db               # noqa: E402
from app.governance.ports import load_ports_from_seed   # noqa: E402
from app.analysis.track_builder import ingest_port_calls  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as session:
        n = load_ports_from_seed(session)
        print(f"[seed] port master loaded: {n}")
        c = ingest_port_calls(session)
        print(f"[seed] AIS port calls ingested (new): {c}")


if __name__ == "__main__":
    main()
