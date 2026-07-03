"""pytest 共用設定：以臨時 SQLite DB 隔離測試，載入港口主檔。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 在匯入 app 之前指定臨時資料庫
_TMP_DB = Path(tempfile.gettempdir()) / "epidemic_trace_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["TARGET_PORT_UNLOCODE"] = "TWKHH"
os.environ["TRACK_LOOKBACK_DAYS"] = "28"


@pytest.fixture()
def session():
    # 以 drop_all + create_all 做每測試隔離（避免 Windows 上刪除鎖定的 SQLite 檔）
    from app.db import Base, SessionLocal, engine, init_db
    from app.governance.ports import load_ports_from_seed

    Base.metadata.drop_all(bind=engine)
    init_db()
    db = SessionLocal()
    load_ports_from_seed(db)
    try:
        yield db
    finally:
        db.close()
