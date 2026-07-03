"""疫情事件治理層：正規化、去重、入庫（附 Grounding 來源標註）。"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OutbreakEvent
from app.sources.outbreak_record import OutbreakRecord


def make_dedup_key(rec: OutbreakRecord) -> str:
    """以 來源+國別+疾病+日期 建立去重鍵（同事件多次抓取只留一筆）。"""
    basis = f"{rec.source}|{rec.country}|{rec.disease}|{rec.report_date.isoformat()}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:32]


def store_outbreaks(session: Session, records: list[OutbreakRecord]) -> dict[str, int]:
    """把來源層事件正規化後 upsert 進 outbreak_events。回傳統計。"""
    added, skipped, dropped = 0, 0, 0
    seen: set[str] = set()

    for rec in records:
        # 治理：至少要有可比對的國別碼，否則保留為情報但不參與比對（此處先略過入庫）
        if not rec.country:
            dropped += 1
            continue

        key = make_dedup_key(rec)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)

        if session.scalar(select(OutbreakEvent.id).where(OutbreakEvent.dedup_key == key)):
            skipped += 1
            continue

        session.add(
            OutbreakEvent(
                disease=rec.disease,
                country=rec.country,
                region=rec.region,
                report_date=rec.report_date,
                severity=rec.severity,
                is_pheic=rec.is_pheic,
                source=rec.source,
                source_url=rec.source_url,
                raw_text=rec.raw_text,
                dedup_key=key,
            )
        )
        added += 1

    session.commit()
    return {"added": added, "skipped": skipped, "dropped_no_country": dropped}
