"""端到端 + API + 推播門檻測試（不打外部網路，使用注入的疫情事件）。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi.testclient import TestClient

from app.analysis.track_builder import ingest_port_calls
from app.governance.outbreaks import store_outbreaks
from app.models import Notification
from app.pipeline import assess_all
from app.service.notifier import notify_if_high
from app.sources.ais_provider import MockAISProvider
from app.sources.outbreak_record import OutbreakRecord
from tests.helpers import add_call, add_outbreak, add_ship

AS_OF = datetime(2026, 7, 3)


def test_dedup_store_outbreaks(session):
    rec = OutbreakRecord(
        disease="COVID-19", country="CN", region=None, report_date=date(2026, 6, 25),
        severity=None, is_pheic=True, source="cdc", source_url=None, raw_text=None,
    )
    r1 = store_outbreaks(session, [rec, rec])   # 同批重複
    r2 = store_outbreaks(session, [rec])        # 再存一次
    assert r1["added"] == 1
    assert r2["added"] == 0 and r2["skipped"] == 1


def test_drop_when_no_country(session):
    rec = OutbreakRecord(
        disease="Yellow fever", country="", region="Global", report_date=date(2026, 6, 24),
        severity=None, is_pheic=False, source="who", source_url=None, raw_text=None,
    )
    assert store_outbreaks(session, [rec])["dropped_no_country"] == 1


def test_high_risk_triggers_notification(session):
    ship = add_ship(session, "HR1")
    add_call(session, ship, "CNSHA", datetime(2026, 6, 26, 6), datetime(2026, 6, 29, 18))
    add_call(session, ship, "TWKHH", datetime(2026, 7, 1, 9), None)
    add_outbreak(session, "COVID-19", "CN", date(2026, 6, 27), is_pheic=True)
    session.commit()

    results = assess_all(session, AS_OF)
    a = next(r for r in results if r.ship_id == ship.id)
    assert a.risk_level in {"high", "critical"}
    assert session.query(Notification).filter_by(assessment_id=a.id).count() == 1


def test_low_risk_no_notification(session):
    ship = add_ship(session, "LR1")
    add_call(session, ship, "TWKHH", datetime(2026, 7, 1, 9), None)  # 無外國港
    session.commit()

    a = assess_all(session, AS_OF)[0]
    assert a.risk_level == "low"
    assert notify_if_high(session, a) is None


def test_mock_ais_provider_loads_and_ingests(session):
    n = ingest_port_calls(session, MockAISProvider())
    assert n > 0  # 從 data/mock_ais.json 匯入靠港紀錄


def test_api_endpoints(session):
    # 準備一筆高風險資料
    ship = add_ship(session, "API1")
    add_call(session, ship, "CNSHA", datetime(2026, 6, 26, 6), datetime(2026, 6, 29, 18))
    add_call(session, ship, "TWKHH", datetime(2026, 7, 1, 9), None)
    add_outbreak(session, "COVID-19", "CN", date(2026, 6, 27), is_pheic=True)
    session.commit()
    assess_all(session, AS_OF)

    from app.main import app
    client = TestClient(app)

    assert client.get("/health").status_code == 200

    r = client.get("/assessments", params={"min_level": "high"})
    assert r.status_code == 200
    body = r.json()
    assert "generated_at" in body and "data_note" in body
    assert any(a["ship_code"] == "API1" for a in body["assessments"])
    # 確認每筆為標準輸出格式（重點欄位）
    api1 = next(a for a in body["assessments"] if a["ship_code"] == "API1")
    assert set(api1) == {
        "ship_code", "ship_name", "prev_port", "risk_level",
        "score", "matched_outbreaks",
    }

    r = client.get("/ships/API1/track")
    assert r.status_code == 200
    assert [c["port_unlocode"] for c in r.json()] == ["CNSHA", "TWKHH"]

    r = client.get("/outbreaks", params={"country": "CN"})
    assert r.status_code == 200 and len(r.json()) >= 1
