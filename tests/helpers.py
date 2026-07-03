"""測試輔助：建立船舶、靠港、疫情事件。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import OutbreakEvent, PortCall, Ship


def add_ship(session: Session, ship_code: str, name: str = "Test") -> Ship:
    ship = Ship(ship_code=ship_code, name=name)
    session.add(ship)
    session.flush()
    return ship


def add_call(session: Session, ship: Ship, port: str, arrival: datetime,
             departure: datetime | None) -> PortCall:
    call = PortCall(ship_id=ship.id, port_unlocode=port, arrival_ts=arrival,
                    departure_ts=departure, source="test")
    session.add(call)
    session.flush()
    return call


def add_outbreak(session: Session, disease: str, country: str, report_date: date,
                 is_pheic: bool = False, source: str = "test") -> OutbreakEvent:
    ev = OutbreakEvent(
        disease=disease, country=country, region=None, report_date=report_date,
        severity=None, is_pheic=is_pheic, source=source, source_url=None,
        raw_text=None, dedup_key=f"{source}:{country}:{disease}:{report_date.isoformat()}",
    )
    session.add(ev)
    session.flush()
    return ev
