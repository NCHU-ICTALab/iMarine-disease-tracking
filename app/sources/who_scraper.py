"""WHO Disease Outbreak News (DON) 抓取（來源層，權威補強 + PHEIC 標記）。

OData v4 API：Title 格式為「{疾病} - {國家/區域}」，地理需自 Title/內文解析。
"""
from __future__ import annotations

import re
from datetime import date

import httpx
from dateutil import parser as dtparser

from app.config import settings
from app.governance.countries import resolve_iso2
from app.sources.outbreak_record import OutbreakRecord

# 粗略 PHEIC 關鍵字（DON 未提供結構化欄位，以疾病名輔助標記）
_PHEIC_HINTS = ("ebola", "marburg", "mpox", "monkeypox", "polio", "covid", "sars", "mers", "zika")


def fetch_who_don(top: int = 50, timeout: int = 30) -> list[OutbreakRecord]:
    resp = httpx.get(
        settings.who_don_api,
        params={"$orderby": "PublicationDate desc", "$top": top},
        timeout=timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    items = resp.json().get("value", [])
    return [rec for it in items if (rec := _parse_item(it)) is not None]


def _parse_item(item: dict) -> OutbreakRecord | None:
    title = (item.get("Title") or "").strip()
    if not title:
        return None
    disease, location = _split_title(title)
    # 部分 Title 用逗號而非「 - 」分隔地名；若解析不到國別，退而以整段 Title 做子字串比對
    iso2 = resolve_iso2(location) or resolve_iso2(title)
    return OutbreakRecord(
        disease=disease,
        country=iso2 or "",
        region=location,
        report_date=_parse_date(item.get("PublicationDate")),
        severity=None,
        is_pheic=any(h in disease.lower() for h in _PHEIC_HINTS),
        source="who",
        source_url=_build_url(item),
        raw_text=title,
    )


def _split_title(title: str) -> tuple[str, str | None]:
    """「Nipah virus disease - India」→ ('Nipah virus disease', 'India')。"""
    m = re.split(r"\s[-–]\s", title, maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()
    return title, None


def _build_url(item: dict) -> str | None:
    slug = item.get("ItemDefaultUrl") or item.get("UrlName")
    if slug:
        slug = slug.lstrip("/")
        return f"https://www.who.int/emergencies/disease-outbreak-news/item/{slug}"
    return None


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return dtparser.parse(value).date()
    except (ValueError, OverflowError):
        return date.today()
