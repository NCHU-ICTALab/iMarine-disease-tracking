"""疫情事件的來源層中間表示（尚未入庫）。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class OutbreakRecord:
    disease: str
    country: str          # ISO3166-1 alpha-2；若無法解析則為 ""
    region: str | None
    report_date: date
    severity: str | None
    is_pheic: bool
    source: str           # cdc | who | news
    source_url: str | None
    raw_text: str | None
