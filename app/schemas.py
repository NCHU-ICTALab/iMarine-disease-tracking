"""API 輸出 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PortCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    port_unlocode: str
    arrival_ts: datetime
    departure_ts: datetime | None
    source: str


class MatchedOutbreakOut(BaseModel):
    """比對到的疫情（重點欄位，含來源可溯）。"""
    port: str | None
    country: str | None
    disease: str | None
    report_date: str | None
    relation: str | None          # during_or_before | post_departure
    source: str | None            # cdc | who
    source_url: str | None


class AssessmentOut(BaseModel):
    """單船評估（workflow 標準輸出格式）。

    註：recommendation（防護建議）仍會計算並存入 DB，暫不放進此輸出格式。
    """
    ship_code: str | None
    ship_name: str | None
    prev_port: str | None
    risk_level: str
    score: float
    matched_outbreaks: list[MatchedOutbreakOut]


class AssessmentBundle(BaseModel):
    """即時風險資料庫的整體輸出（頂層 metadata + 每船評估）。"""
    generated_at: str
    target_port: str
    data_note: str
    assessments: list[AssessmentOut]


class OutbreakOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    disease: str
    country: str
    region: str | None
    report_date: str
    severity: str | None
    is_pheic: bool
    source: str
    source_url: str | None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assessment_id: int
    channel: str
    payload: dict | None
    status: str
    created_at: datetime
