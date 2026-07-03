"""時序交叉比對（分析層 ②）。

對船舶靠港序列中的每個外國港，比對該港所屬國家的疫情事件，
判定時序關係並落在病原潛伏期窗口內者才視為命中。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.pathogens import lookup as lookup_pathogen
from app.config import settings
from app.governance.ports import country_of
from app.models import OutbreakEvent, PortCall, Ship

# 疫情通報早於停靠多久仍視為「該時期仍在流行」（避免比對到已結束的舊疫情）
STALE_BEFORE_DAYS = 365


@dataclass
class Match:
    port_unlocode: str
    country: str
    disease: str
    event_id: int
    report_date: str
    is_pheic: bool
    severity_raw: str | None
    source: str
    source_url: str | None
    relation: str          # during_or_before | post_departure
    days_gap: int          # 通報相對於離港的天數（負=停靠期間/之前）
    temporal_fit: float    # 0-1 時序吻合度
    stay_days: float
    seq_position_from_last: int  # 0=前一個外國港，往前遞增
    incubation_max: int


def match_ship(session: Session, ship: Ship, as_of: datetime | None = None) -> list[Match]:
    from app.analysis.track_builder import reconstruct_sequence

    as_of = as_of or datetime.utcnow()
    seq = reconstruct_sequence(session, ship, as_of)
    home_country = country_of(session, settings.target_port_unlocode)

    # 目標港（高雄）抵達時間 → 只看抵達前的外國港
    target_arrivals = [c for c in seq if c.port_unlocode == settings.target_port_unlocode]
    if not target_arrivals:
        return []
    khh_arrival = target_arrivals[-1].arrival_ts

    foreign_calls = [
        c for c in seq
        if c.arrival_ts < khh_arrival
        and country_of(session, c.port_unlocode) not in (None, home_country)
    ]
    # 由近而遠標序位（最後一個外國港 = 前一港 = position 0）
    foreign_calls_sorted = sorted(foreign_calls, key=lambda c: c.arrival_ts, reverse=True)

    matches: list[Match] = []
    for pos, call in enumerate(foreign_calls_sorted):
        matches.extend(_match_call(session, call, pos))
    return matches


def _match_call(session: Session, call: PortCall, seq_position: int) -> list[Match]:
    country = country_of(session, call.port_unlocode)
    if not country:
        return []
    arrival = call.arrival_ts
    departure = call.departure_ts or call.arrival_ts
    stay_days = max(0.0, (departure - arrival).total_seconds() / 86400.0)

    events = session.scalars(
        select(OutbreakEvent).where(OutbreakEvent.country == country)
    ).all()

    out: list[Match] = []
    for ev in events:
        pathogen = lookup_pathogen(ev.disease)
        inc_max = pathogen.incubation_max
        report_dt = datetime(ev.report_date.year, ev.report_date.month, ev.report_date.day)

        # 時序窗口：通報不得晚於離港 + 潛伏期上限；也不得早於抵達 - 一年（排除已結束舊疫情）
        if report_dt > departure + timedelta(days=inc_max):
            continue
        if report_dt < arrival - timedelta(days=STALE_BEFORE_DAYS):
            continue

        if report_dt <= departure:
            relation = "during_or_before"
            temporal_fit = 1.0
            days_gap = -max(0, (departure - report_dt).days)
        else:
            relation = "post_departure"     # 報告書 P.8 明列缺口：離港後才通報
            gap = (report_dt - departure).days
            days_gap = gap
            temporal_fit = max(0.5, 1.0 - (gap / inc_max) * 0.5)

        out.append(
            Match(
                port_unlocode=call.port_unlocode,
                country=country,
                disease=ev.disease,
                event_id=ev.id,
                report_date=ev.report_date.isoformat(),
                is_pheic=ev.is_pheic,
                severity_raw=ev.severity,
                source=ev.source,
                source_url=ev.source_url,
                relation=relation,
                days_gap=days_gap,
                temporal_fit=round(temporal_fit, 3),
                stay_days=round(stay_days, 2),
                seq_position_from_last=seq_position,
                incubation_max=inc_max,
            )
        )
    return out
