"""高階流程編排：抓取 → 比對評分 → 寫回即時風險資料庫（供 API / 排程共用）。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.analysis.matcher import match_ship
from app.analysis.risk_engine import assess as assess_matches
from app.analysis.track_builder import get_target_arrivals, ingest_port_calls, prev_foreign_call
from app.config import settings
from app.governance.outbreaks import store_outbreaks
from app.models import RiskAssessment, Ship
from app.sources.cdc_scraper import fetch_cdc_alerts
from app.sources.who_scraper import fetch_who_don


def refresh_outbreaks(session: Session, include_who: bool = True) -> dict:
    """抓取疾管署（+ WHO）疫情事件並入庫。"""
    stats = {"cdc": store_outbreaks(session, fetch_cdc_alerts())}
    if include_who:
        try:
            stats["who"] = store_outbreaks(session, fetch_who_don())
        except Exception as e:  # noqa: BLE001  WHO 失敗不應中斷主流程
            stats["who_error"] = repr(e)
    return stats


def refresh_ais(session: Session) -> int:
    """抓取 AIS 靠港紀錄並入庫。"""
    return ingest_port_calls(session)


def assess_ship(session: Session, ship: Ship, as_of: datetime | None = None) -> RiskAssessment:
    """對單船做時序比對 + 風險評分，寫入一筆 risk_assessments。"""
    as_of = as_of or datetime.utcnow()
    matches = match_ship(session, ship, as_of)
    result = assess_matches(matches, as_of.date() if isinstance(as_of, datetime) else as_of)
    prev = prev_foreign_call(session, ship, as_of)

    assessment = RiskAssessment(
        ship_id=ship.id,
        target_port=settings.target_port_unlocode,
        prev_port=prev.port_unlocode if prev else None,
        matched_events=result["matched_events"],
        risk_level=result["risk_level"],
        score=result["score"],
        recommendation=result["recommendation"],
        assessed_at=as_of,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def assess_all(session: Session, as_of: datetime | None = None) -> list[RiskAssessment]:
    """對所有抵達目標港的船做評估，回傳結果清單。"""
    as_of = as_of or datetime.utcnow()
    results = [assess_ship(session, ship, as_of) for ship in get_target_arrivals(session, as_of)]

    # P6 會在此接上高風險自動推播（notifier）。
    from app.service.notifier import notify_if_high  # 延遲匯入避免循環

    for a in results:
        notify_if_high(session, a)
    return results


def full_refresh(session: Session, as_of: datetime | None = None) -> dict:
    """一鍵：抓疫情 + 抓 AIS + 全量評估。"""
    outbreaks = refresh_outbreaks(session)
    new_calls = refresh_ais(session)
    assessments = assess_all(session, as_of)
    return {
        "outbreaks": outbreaks,
        "new_port_calls": new_calls,
        "assessed_ships": len(assessments),
    }
