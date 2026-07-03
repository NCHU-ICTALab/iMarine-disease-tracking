"""ORM 資料表定義（對應實作計畫 §4 DB Schema）。"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    DateTime,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Ship(Base):
    """船舶主檔（船隻代碼）。"""

    __tablename__ = "ships"

    id: Mapped[int] = mapped_column(primary_key=True)
    mmsi: Mapped[str | None] = mapped_column(String(16), index=True)
    imo: Mapped[str | None] = mapped_column(String(16), index=True)
    ship_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128))

    port_calls: Mapped[list["PortCall"]] = relationship(back_populates="ship")


class Port(Base):
    """港口主檔（UN/LOCODE、國別、座標）。"""

    __tablename__ = "ports"

    unlocode: Mapped[str] = mapped_column(String(8), primary_key=True)  # 如 TWKHH
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(2), index=True)         # ISO3166-1 alpha-2
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class PortCall(Base):
    """靠港序列（航跡重建結果）。"""

    __tablename__ = "port_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    ship_id: Mapped[int] = mapped_column(ForeignKey("ships.id"), index=True)
    port_unlocode: Mapped[str] = mapped_column(ForeignKey("ports.unlocode"), index=True)
    arrival_ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    departure_ts: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(32), default="mock")

    ship: Mapped["Ship"] = relationship(back_populates="port_calls")
    port: Mapped["Port"] = relationship()


class OutbreakEvent(Base):
    """疫情事件時間軸（疾管署 / WHO / 新聞）。"""

    __tablename__ = "outbreak_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    disease: Mapped[str] = mapped_column(String(128), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)        # ISO3166-1 alpha-2
    region: Mapped[str | None] = mapped_column(String(128))
    report_date: Mapped[date] = mapped_column(Date, index=True)
    severity: Mapped[str | None] = mapped_column(String(32))           # 來源原始等級
    is_pheic: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32))                    # cdc | who | news
    source_url: Mapped[str | None] = mapped_column(String(512))
    raw_text: Mapped[str | None] = mapped_column(Text)
    dedup_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)


class RiskAssessment(Base):
    """輸出：即時風險資料庫（船隻代碼、前一港、有無染疫風險）。"""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ship_id: Mapped[int] = mapped_column(ForeignKey("ships.id"), index=True)
    target_port: Mapped[str] = mapped_column(String(8))               # 高雄 TWKHH
    prev_port: Mapped[str | None] = mapped_column(String(8))          # 前一港 UN/LOCODE
    matched_events: Mapped[list | None] = mapped_column(JSON)         # 比對到的疫情事件明細
    risk_level: Mapped[str] = mapped_column(String(16), index=True)   # low|medium|high|critical
    score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str | None] = mapped_column(Text)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    ship: Mapped["Ship"] = relationship()


class Notification(Base):
    """推播紀錄（細胞簡訊 mock）。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("risk_assessments.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="cell_broadcast_mock")
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DecisionLog(Base):
    """決策層日誌（採納 / 退回 / 觸發紀錄）。"""

    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("risk_assessments.id"))
    action: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
