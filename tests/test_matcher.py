"""時序交叉比對測試：三種時序關係與潛伏期窗口。"""
from __future__ import annotations

from datetime import date, datetime

from app.analysis.matcher import match_ship
from tests.helpers import add_call, add_outbreak, add_ship

AS_OF = datetime(2026, 7, 3)


def _ship_via_shanghai(session):
    """一艘經上海(CN)後抵高雄的船；在上海停靠 6/26–6/27。"""
    ship = add_ship(session, "M1")
    add_call(session, ship, "CNSHA", datetime(2026, 6, 26, 6), datetime(2026, 6, 27, 18))
    add_call(session, ship, "TWKHH", datetime(2026, 6, 29, 9), None)
    session.commit()
    return ship


def test_during_or_before_relation(session):
    ship = _ship_via_shanghai(session)
    add_outbreak(session, "COVID-19", "CN", date(2026, 6, 20))  # 停靠前已通報
    session.commit()

    matches = match_ship(session, ship, AS_OF)
    assert any(m.relation == "during_or_before" and m.port_unlocode == "CNSHA"
               for m in matches)


def test_post_departure_within_incubation(session):
    """報告書 P.8 缺口：離港後才通報，但落在潛伏期窗口內 → 命中。"""
    ship = _ship_via_shanghai(session)
    # COVID 潛伏期上限 14 天；離港 6/27 後第 5 天通報
    add_outbreak(session, "COVID-19", "CN", date(2026, 7, 2))
    session.commit()

    matches = [m for m in match_ship(session, ship, AS_OF) if m.port_unlocode == "CNSHA"]
    assert matches and matches[0].relation == "post_departure"
    assert 0 < matches[0].temporal_fit < 1.0


def test_post_departure_beyond_incubation_excluded(session):
    ship = _ship_via_shanghai(session)
    # 流感潛伏期上限僅 4 天；離港後第 20 天才通報 → 應被排除
    add_outbreak(session, "Influenza", "CN", date(2026, 7, 17))
    session.commit()

    matches = [m for m in match_ship(session, ship, AS_OF)
               if m.port_unlocode == "CNSHA" and m.disease == "Influenza"]
    assert matches == []


def test_stale_outbreak_excluded(session):
    ship = _ship_via_shanghai(session)
    add_outbreak(session, "COVID-19", "CN", date(2024, 1, 1))  # 兩年前 → 視為已結束
    session.commit()

    matches = [m for m in match_ship(session, ship, AS_OF) if m.port_unlocode == "CNSHA"]
    assert matches == []


def test_other_country_not_matched(session):
    ship = _ship_via_shanghai(session)
    add_outbreak(session, "COVID-19", "JP", date(2026, 6, 25))  # 日本疫情，船沒去日本
    session.commit()

    assert match_ship(session, ship, AS_OF) == []
