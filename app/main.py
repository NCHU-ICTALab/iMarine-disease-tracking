"""FastAPI 進入點。啟動時建表，提供健康檢查。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os

from app.config import settings
from app.db import init_db
from app.service.api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = None
    # 設 ENABLE_SCHEDULER=1 才在啟動時掛載定時抓取/重算（預設關閉，避免開發時打外部網路）
    if os.getenv("ENABLE_SCHEDULER") == "1":
        from app.jobs.scheduler import build_scheduler

        scheduler = build_scheduler()
        scheduler.start()
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(
    title="疫情自動追溯與擴散圈風險預警 API",
    description="重建進港船靠港序列，交叉比對疫情時序，輸出風險等級與防護建議。",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS：供前端整合層（iMarine-FrontEnd，Vite dev :5173）瀏覽器直接 fetch /assessments。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",  # vite preview
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "target_port": settings.target_port_unlocode,
        "ais_provider": settings.ais_provider,
    }
