"""定時排程：週期性抓取疫情 / AIS 並重算評估。

可獨立執行（python -m app.jobs.scheduler），或由 main.py 在啟動時掛載。
"""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal, init_db
from app.pipeline import full_refresh

logger = logging.getLogger("epidemic_trace.scheduler")

# 抓取 / 重算間隔（分鐘）。疫情來源日更，AIS 可較頻繁。
REFRESH_INTERVAL_MINUTES = 60


def run_once() -> dict:
    """執行一次完整刷新，回傳統計。"""
    with SessionLocal() as session:
        result = full_refresh(session, datetime.utcnow())
    logger.info("[scheduler] full_refresh 完成: %s", result)
    return result


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(
        run_once,
        "interval",
        minutes=REFRESH_INTERVAL_MINUTES,
        id="full_refresh",
        next_run_time=datetime.now(),  # 啟動後立即跑一次
        max_instances=1,
        coalesce=True,
    )
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("[scheduler] 立即執行一次 full_refresh ...")
    print(run_once())
