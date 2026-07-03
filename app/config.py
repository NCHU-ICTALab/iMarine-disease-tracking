"""集中式設定：來源端點、追蹤範圍、門檻、金鑰。

以 pydantic-settings 讀取 .env，未設定時採合理預設值。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 專案根目錄（epidemic_trace/）
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 資料庫
    database_url: str = f"sqlite:///{(DATA_DIR / 'epidemic_trace.db').as_posix()}"

    # 追蹤範圍
    target_port_unlocode: str = "TWKHH"   # 高雄港
    track_lookback_days: int = 28

    # 疫情資料來源
    cdc_travel_alert_csv: str = (
        "https://www.cdc.gov.tw/CountryEpidLevel/ExportCSV"
        "?type=0&fileName=TCDCTravelAlertAll.csv"
    )
    who_don_api: str = "https://www.who.int/api/news/diseaseoutbreaknews"

    # AIS 來源
    ais_provider: str = "mock"            # mock | aisstream
    ais_mock_file: str = str(DATA_DIR / "mock_ais.json")
    aisstream_api_key: str = ""

    # 風險 / 推播
    notify_min_level: str = "high"        # low | medium | high | critical


settings = Settings()
