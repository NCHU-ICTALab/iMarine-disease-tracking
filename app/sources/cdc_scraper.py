"""疾管署『國際旅遊疫情建議等級表』CSV 抓取（來源層，結構化主軸）。

已實測欄位：source, effective, senderName, instruction, web, alert_title,
severity_level, alert_disease, areaDesc, areaDesc_EN, circle, ISO3166,
areaDetail, ISO3166_2。
"""
from __future__ import annotations

import csv
import io
from datetime import date

import httpx
from dateutil import parser as dtparser

from app.config import settings
from app.sources.outbreak_record import OutbreakRecord


def fetch_cdc_alerts(url: str | None = None, timeout: int = 30) -> list[OutbreakRecord]:
    url = url or settings.cdc_travel_alert_csv
    # 疾管署站台憑證鏈在部分環境無法驗證，MVP 階段關閉驗證（正式環境應補憑證）
    resp = httpx.get(url, timeout=timeout, verify=False, follow_redirects=True)
    resp.raise_for_status()
    return parse_cdc_csv(resp.content)


def parse_cdc_csv(content: bytes) -> list[OutbreakRecord]:
    text = content.decode("utf-8-sig", errors="replace")
    records: list[OutbreakRecord] = []
    for row in csv.DictReader(io.StringIO(text)):
        iso2 = (row.get("ISO3166") or "").strip().upper()
        disease = (row.get("alert_disease") or "").strip()
        if not disease:
            continue
        records.append(
            OutbreakRecord(
                disease=disease,
                country=iso2,
                region=(row.get("areaDesc_EN") or row.get("areaDesc") or "").strip() or None,
                report_date=_parse_date(row.get("effective")),
                severity=(row.get("severity_level") or "").strip() or None,
                is_pheic=False,
                source="cdc",
                source_url=(row.get("web") or "").strip() or None,
                raw_text=(row.get("alert_title") or "").strip() or None,
            )
        )
    return records


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return dtparser.parse(value).date()
    except (ValueError, OverflowError):
        return date.today()
