"""航跡重建測試：抵港偵測、序列排序、前一外國港、回溯窗口過濾。"""
from __future__ import annotations

from datetime import datetime

from app.analysis.track_builder import (
    get_target_arrivals,
    prev_foreign_call,
    reconstruct_sequence,
)
from tests.helpers import add_call, add_ship

AS_OF = datetime(2026, 7, 3)


def test_arrival_detected_and_sequence_ordered(session):
    ship = add_ship(session, "S1")
    add_call(session, ship, "HKHKG", datetime(2026, 6, 22, 8), datetime(2026, 6, 24, 20))
    add_call(session, ship, "CNSHA", datetime(2026, 6, 26, 6), datetime(2026, 6, 27, 18))
    add_call(session, ship, "TWKHH", datetime(2026, 6, 29, 9), None)
    session.commit()

    arrivals = get_target_arrivals(session, AS_OF)
    assert [s.ship_code for s in arrivals] == ["S1"]

    seq = reconstruct_sequence(session, ship, AS_OF)
    assert [c.port_unlocode for c in seq] == ["HKHKG", "CNSHA", "TWKHH"]

    prev = prev_foreign_call(session, ship, AS_OF)
    assert prev is not None and prev.port_unlocode == "CNSHA"


def test_old_foreign_call_outside_window_excluded(session):
    ship = add_ship(session, "S2")
    # 外國港在 28 天窗口外（4 月），只有高雄在窗口內
    add_call(session, ship, "IDJKT", datetime(2026, 4, 10, 6), datetime(2026, 4, 12, 20))
    add_call(session, ship, "TWKHH", datetime(2026, 6, 28, 10), None)
    session.commit()

    prev = prev_foreign_call(session, ship, AS_OF)
    assert prev is None  # 舊外國港被回溯窗口濾除


def test_ship_not_arriving_target_excluded(session):
    ship = add_ship(session, "S3")
    add_call(session, ship, "SGSIN", datetime(2026, 6, 25, 6), datetime(2026, 6, 26, 20))
    session.commit()
    assert get_target_arrivals(session, AS_OF) == []
