"""港口主檔（治理層）：載入 UN/LOCODE 港口與座標，供國別對齊使用。

MVP 採 data/ports_seed.csv 的精選港口清單；未來可換 improved-un-locodes
的 code-list-improved.csv（欄位對映見 load_from_improved_unlocode）。
"""
from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models import Port

SEED_CSV = DATA_DIR / "ports_seed.csv"


def load_ports_from_seed(session: Session, csv_path: Path = SEED_CSV) -> int:
    """從精選 CSV 匯入 / 更新港口主檔，回傳處理筆數。"""
    count = 0
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            _upsert_port(
                session,
                unlocode=row["unlocode"].strip().upper(),
                name=row["name"].strip(),
                country=row["country"].strip().upper(),
                lat=_to_float(row.get("lat")),
                lon=_to_float(row.get("lon")),
            )
            count += 1
    session.commit()
    return count


def _upsert_port(session: Session, *, unlocode, name, country, lat, lon) -> None:
    port = session.get(Port, unlocode)
    if port is None:
        session.add(Port(unlocode=unlocode, name=name, country=country, lat=lat, lon=lon))
    else:
        port.name, port.country, port.lat, port.lon = name, country, lat, lon


def get_port(session: Session, unlocode: str) -> Port | None:
    return session.get(Port, unlocode.strip().upper())


def country_of(session: Session, unlocode: str) -> str | None:
    """回傳港口所屬的 ISO3166-1 alpha-2 國別碼。"""
    port = get_port(session, unlocode)
    return port.country if port else None


def all_ports(session: Session) -> list[Port]:
    return list(session.scalars(select(Port)))


def _to_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
