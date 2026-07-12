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
    # aisstream 即時收集參數
    # 多區域監看（單一連線可帶多個 bounding box）：涵蓋「有 aisstream 涵蓋」的區域港，
    # 讓同一 MMSI 先後出現在外國港與台灣港時，能重建真實「外國港→台灣」航跡（真 prev_foreign_port）。
    # 各港涵蓋率為實測結果（見 docs/資料來源與真假對照.md）；高雄目前 0 涵蓋仍保留方框以備未來。
    ais_bbox: list = [
        [[24.5, 121.2], [25.6, 122.3]],   # 基隆 / 北台灣（TWKEL，實測有涵蓋）
        [[22.0, 119.8], [23.3, 120.9]],   # 高雄（TWKHH，目前 0 涵蓋，保留備用）
        [[34.6, 128.5], [35.6, 129.7]],   # 釜山 KRPUS（實測涵蓋最佳）
        [[21.8, 113.7], [22.8, 114.7]],   # 香港 HKHKG
        [[0.8, 103.3], [1.7, 104.4]],     # 新加坡 SGSIN
        [[35.0, 139.3], [35.9, 140.2]],   # 東京灣 JPTYO
    ]
    ais_collect_seconds: float = 45.0     # 每次連線收集秒數
    ais_port_radius_km: float = 25.0      # 距港口座標多近視為「在港」
    ais_port_max_sog: float = 3.0         # SOG 高於此值視為過境、非靠港（節）
    ais_sightings_file: str = str(DATA_DIR / "ais_sightings.json")
    ports_seed_file: str = str(DATA_DIR / "ports_seed.csv")

    # MOTC（航港局）臺灣海域即時船位：公開、免授權的地圖前端端點。
    # 只用當下船位（不碰需授權端點）。台灣端靠港偵測沿用 ais_port_radius_km / ais_port_max_sog。
    motc_ais_url: str = "https://mpbais.motcmpb.gov.tw/aismpb/tools/geojsonais.ashx"
    motc_poll_seconds: float = 180.0      # 每 3 分鐘輪詢一次（禮貌）
    motc_sightings_file: str = str(DATA_DIR / "motc_sightings.json")
    motc_log_file: str = str(DATA_DIR / "motc_log.jsonl")

    # 風險 / 推播
    notify_min_level: str = "high"        # low | medium | high | critical


settings = Settings()
