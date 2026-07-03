"""SQLAlchemy engine / session / Base 宣告。"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, settings

# 確保 SQLite 檔案目錄存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """所有 ORM 模型的宣告基底。"""


def get_session():
    """FastAPI 依賴注入用的 session 產生器。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建立所有資料表（MVP 以 create_all 取代 migration 工具）。"""
    import app.models  # noqa: F401  觸發模型註冊

    Base.metadata.create_all(bind=engine)
