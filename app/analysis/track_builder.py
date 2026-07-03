"""航跡重建（分析層 ①）。

將 AIS 來源的靠港紀錄入庫，並為抵達目標港（高雄）的船舶重建近期靠港序列、
標記前一個外國港（prev_foreign_port）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PortCall, Ship
from app.sources.ais_provider import AISProvider, PortCallRecord, get_provider


def ingest_port_calls(session: Session, provider: AISProvider | None = None) -> int:
    """把來源層的靠港紀錄寫入 ships / port_calls（去重）。回傳新增筆數。"""
    provider = provider or get_provider()
    records = provider.fetch_port_calls()

    new_calls = 0
    for rec in records:
        ship = _upsert_ship(session, rec)
        if not _call_exists(session, ship.id, rec.port_unlocode, rec.arrival):
            session.add(
                PortCall(
                    ship_id=ship.id,
                    port_unlocode=rec.port_unlocode,
                    arrival_ts=rec.arrival,
                    departure_ts=rec.departure,
                    source=rec.source,
                )
            )
            new_calls += 1
    session.commit()
    return new_calls


def _upsert_ship(session: Session, rec: PortCallRecord) -> Ship:
    ship = session.scalar(select(Ship).where(Ship.ship_code == rec.ship_code))
    if ship is None:
        ship = Ship(ship_code=rec.ship_code, mmsi=rec.mmsi, imo=rec.imo, name=rec.name)
        session.add(ship)
        session.flush()  # 取得 ship.id
    else:
        ship.mmsi = ship.mmsi or rec.mmsi
        ship.imo = ship.imo or rec.imo
        ship.name = ship.name or rec.name
    return ship


def _call_exists(session: Session, ship_id: int, port: str, arrival: datetime) -> bool:
    return session.scalar(
        select(PortCall.id).where(
            PortCall.ship_id == ship_id,
            PortCall.port_unlocode == port,
            PortCall.arrival_ts == arrival,
        )
    ) is not None


def get_target_arrivals(session: Session, as_of: datetime | None = None) -> list[Ship]:
    """回傳在回溯窗口內曾抵達目標港（高雄）的船舶。"""
    as_of = as_of or datetime.utcnow()
    since = as_of - timedelta(days=settings.track_lookback_days)
    ship_ids = session.scalars(
        select(PortCall.ship_id)
        .where(
            PortCall.port_unlocode == settings.target_port_unlocode,
            PortCall.arrival_ts >= since,
            PortCall.arrival_ts <= as_of,
        )
        .distinct()
    ).all()
    if not ship_ids:
        return []
    return list(session.scalars(select(Ship).where(Ship.id.in_(ship_ids))))


def reconstruct_sequence(
    session: Session, ship: Ship, as_of: datetime | None = None
) -> list[PortCall]:
    """重建單船在回溯窗口內、依抵達時間排序的靠港序列。"""
    as_of = as_of or datetime.utcnow()
    since = as_of - timedelta(days=settings.track_lookback_days)
    return list(
        session.scalars(
            select(PortCall)
            .where(
                PortCall.ship_id == ship.id,
                PortCall.arrival_ts >= since,
                PortCall.arrival_ts <= as_of,
            )
            .order_by(PortCall.arrival_ts)
        )
    )


def prev_foreign_call(
    session: Session, ship: Ship, as_of: datetime | None = None
) -> PortCall | None:
    """回傳抵達高雄前、最後一個『非本國(台灣)』港口的靠港紀錄。

    以目標港所屬國家（台灣 TW）為本國；序列中排在目標港抵達之前、
    最靠近的外國港即為 prev_foreign_port。
    """
    from app.governance.ports import country_of

    seq = reconstruct_sequence(session, ship, as_of)
    home_country = country_of(session, settings.target_port_unlocode)

    # 找出目標港的抵達時間（取窗口內最後一次抵達高雄）
    target_arrivals = [c for c in seq if c.port_unlocode == settings.target_port_unlocode]
    if not target_arrivals:
        return None
    target_arrival_ts = target_arrivals[-1].arrival_ts

    prev = None
    for call in seq:
        if call.arrival_ts >= target_arrival_ts:
            break
        if country_of(session, call.port_unlocode) != home_country:
            prev = call
    return prev
