"""細胞簡訊推播（mock）。

真實細胞廣播（CBS）屬電信層，MVP 以抽象介面 + DB/log 模擬；
達門檻等級的評估會自動產生一筆 notifications 紀錄。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, RiskAssessment, Ship

logger = logging.getLogger("epidemic_trace.notifier")

_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Notifier(ABC):
    channel: str = "abstract"

    @abstractmethod
    def send(self, session: Session, assessment: RiskAssessment, payload: dict) -> Notification:
        raise NotImplementedError


class MockCellBroadcastNotifier(Notifier):
    """模擬細胞簡訊：寫入 notifications 表並輸出 log。"""

    channel = "cell_broadcast_mock"

    def send(self, session: Session, assessment: RiskAssessment, payload: dict) -> Notification:
        note = Notification(
            assessment_id=assessment.id,
            channel=self.channel,
            payload=payload,
            status="sent",
        )
        session.add(note)
        session.commit()
        session.refresh(note)
        logger.warning("[CELL-BROADCAST(mock)] %s", payload)
        return note


_default_notifier: Notifier = MockCellBroadcastNotifier()


def _meets_threshold(level: str) -> bool:
    return _LEVEL_ORDER.get(level, 0) >= _LEVEL_ORDER.get(settings.notify_min_level, 2)


def notify_if_high(
    session: Session, assessment: RiskAssessment, notifier: Notifier | None = None
) -> Notification | None:
    """達設定門檻（預設 high）才推播。回傳 Notification 或 None。"""
    if not _meets_threshold(assessment.risk_level):
        return None

    notifier = notifier or _default_notifier
    ship = session.get(Ship, assessment.ship_id)
    payload = {
        "ship_code": ship.ship_code if ship else None,
        "ship_name": ship.name if ship else None,
        "prev_port": assessment.prev_port,
        "target_port": assessment.target_port,
        "risk_level": assessment.risk_level,
        "score": assessment.score,
        "recommendation": assessment.recommendation,
        "top_disease": (assessment.matched_events or [{}])[0].get("disease"),
    }
    return notifier.send(session, assessment, payload)
