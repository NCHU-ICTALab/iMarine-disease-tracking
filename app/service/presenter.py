"""統一的輸出格式（workflow 的標準 output）。

API 與 scripts/export_demo.py 皆呼叫此處，確保各處輸出格式一致。
格式即 demo_output.json：頂層 metadata + assessments[]，每筆只保留重點欄位。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import RiskAssessment, Ship

_DATA_NOTES = {
    "motc": (
        "疫情為真實資料（疾管署 / WHO）；抵港船為真實資料（航港局 MOTC 臺灣海域船位），"
        "前一外國港由 MOTC×aisstream 以 MMSI 串聯還原（僅涵蓋有 aisstream 涵蓋的亞太 hub，"
        "南亞/中東/非洲疫情港無涵蓋）。詳見 docs/資料來源與真假對照.md"
    ),
    "aisstream": (
        "疫情為真實資料（疾管署 / WHO）；船舶為 aisstream 即時真實船位。"
        "免費 AIS 高雄 0 涵蓋、無跨國航跡歷史。詳見 docs/資料來源與真假對照.md"
    ),
    "mock": (
        "疫情為真實資料（疾管署 / WHO），船舶航跡為模擬資料。"
        "詳見 docs/資料來源與真假對照.md"
    ),
}


def data_note() -> str:
    return _DATA_NOTES.get(settings.ais_provider.lower(), _DATA_NOTES["mock"])

# 目標港顯示名（MVP 聚焦高雄）
_PORT_DISPLAY = {"TWKHH": "高雄港"}

# 每船預設保留分數最高的前 N 筆比對疫情
DEFAULT_MAX_MATCHES = 3


def target_port_display() -> str:
    code = settings.target_port_unlocode
    name = _PORT_DISPLAY.get(code)
    return f"{code} ({name})" if name else code


def clean_match(m: dict) -> dict:
    return {
        "port": m.get("port"),
        "country": m.get("country"),
        "disease": m.get("disease"),
        "report_date": m.get("report_date"),
        "relation": m.get("relation"),        # during_or_before | post_departure
        "source": m.get("source"),            # cdc | who
        "source_url": m.get("source_url"),
    }


def clean_assessment(
    session: Session, a: RiskAssessment, max_matches: int = DEFAULT_MAX_MATCHES
) -> dict:
    ship = session.get(Ship, a.ship_id)
    matches = a.matched_events or []
    # 註：recommendation（防護建議）仍會計算並存入 DB，只是暫不放進標準輸出格式。
    return {
        "ship_code": ship.ship_code if ship else None,
        "ship_name": ship.name if ship else None,
        "prev_port": a.prev_port,
        "risk_level": a.risk_level,
        "score": round(a.score, 3),
        "matched_outbreaks": [clean_match(m) for m in matches[:max_matches]],
    }


def clean_bundle(
    session: Session,
    assessments: list[RiskAssessment],
    as_of: datetime | None = None,
    max_matches: int = DEFAULT_MAX_MATCHES,
) -> dict:
    ordered = sorted(assessments, key=lambda a: a.score, reverse=True)
    return {
        "generated_at": (as_of or datetime.utcnow()).isoformat(),
        "target_port": target_port_display(),
        "data_note": data_note(),
        "assessments": [clean_assessment(session, a, max_matches) for a in ordered],
    }
