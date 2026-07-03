"""REST API 路由（應用服務層）。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Notification, OutbreakEvent, RiskAssessment, Ship
from app.pipeline import assess_ship, full_refresh
from app.schemas import AssessmentBundle, AssessmentOut, NotificationOut, OutbreakOut, PortCallOut
from app.service.presenter import clean_assessment, clean_bundle
from app.analysis.track_builder import reconstruct_sequence

router = APIRouter()

_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _latest_per_ship(session: Session) -> list[RiskAssessment]:
    """每艘船取最新一筆評估。"""
    rows = session.scalars(
        select(RiskAssessment).order_by(RiskAssessment.assessed_at.desc())
    ).all()
    seen: set[int] = set()
    latest: list[RiskAssessment] = []
    for r in rows:
        if r.ship_id not in seen:
            seen.add(r.ship_id)
            latest.append(r)
    return latest


@router.get("/assessments", response_model=AssessmentBundle, tags=["assessments"])
def list_assessments(
    min_level: str | None = Query(None, description="low|medium|high|critical"),
    session: Session = Depends(get_session),
):
    """即時風險資料庫：每艘船最新評估（workflow 標準輸出格式）。"""
    latest = _latest_per_ship(session)
    if min_level:
        threshold = _LEVEL_ORDER.get(min_level.lower(), 0)
        latest = [a for a in latest if _LEVEL_ORDER.get(a.risk_level, 0) >= threshold]
    return clean_bundle(session, latest)


@router.get("/assessments/{ship_code}", response_model=AssessmentOut, tags=["assessments"])
def get_assessment(ship_code: str, session: Session = Depends(get_session)):
    ship = session.scalar(select(Ship).where(Ship.ship_code == ship_code))
    if not ship:
        raise HTTPException(404, f"找不到船舶: {ship_code}")
    a = session.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.ship_id == ship.id)
        .order_by(RiskAssessment.assessed_at.desc())
    ).first()
    if not a:
        raise HTTPException(404, f"該船尚無評估紀錄: {ship_code}")
    return clean_assessment(session, a)


@router.get("/ships/{ship_code}/track", response_model=list[PortCallOut], tags=["ships"])
def get_track(ship_code: str, session: Session = Depends(get_session)):
    ship = session.scalar(select(Ship).where(Ship.ship_code == ship_code))
    if not ship:
        raise HTTPException(404, f"找不到船舶: {ship_code}")
    return reconstruct_sequence(session, ship)


@router.post("/assess/{ship_code}", response_model=AssessmentOut, tags=["assessments"])
def trigger_assess(ship_code: str, session: Session = Depends(get_session)):
    ship = session.scalar(select(Ship).where(Ship.ship_code == ship_code))
    if not ship:
        raise HTTPException(404, f"找不到船舶: {ship_code}")
    a = assess_ship(session, ship)
    return clean_assessment(session, a)


@router.get("/outbreaks", response_model=list[OutbreakOut], tags=["outbreaks"])
def list_outbreaks(
    country: str | None = Query(None, description="ISO3166-1 alpha-2"),
    since: date | None = Query(None),
    limit: int = Query(100, le=1000),
    session: Session = Depends(get_session),
):
    stmt = select(OutbreakEvent).order_by(OutbreakEvent.report_date.desc())
    if country:
        stmt = stmt.where(OutbreakEvent.country == country.upper())
    if since:
        stmt = stmt.where(OutbreakEvent.report_date >= since)
    events = session.scalars(stmt.limit(limit)).all()
    return [
        OutbreakOut(
            id=e.id, disease=e.disease, country=e.country, region=e.region,
            report_date=e.report_date.isoformat(), severity=e.severity,
            is_pheic=e.is_pheic, source=e.source, source_url=e.source_url,
        )
        for e in events
    ]


@router.get("/notifications", response_model=list[NotificationOut], tags=["notifications"])
def list_notifications(limit: int = Query(100, le=1000), session: Session = Depends(get_session)):
    notes = session.scalars(
        select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    ).all()
    return list(notes)


@router.post("/jobs/refresh", response_model=AssessmentBundle, tags=["jobs"])
def jobs_refresh(session: Session = Depends(get_session)):
    """一鍵：抓疫情 + 抓 AIS + 全量評估（高風險自動推播），回傳標準輸出格式。"""
    full_refresh(session, datetime.utcnow())
    return clean_bundle(session, _latest_per_ship(session))
