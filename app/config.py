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
        # 台灣（目的地端，交叉檢核；台灣主要資料來自 MOTC）
        [[24.5, 121.2], [25.6, 122.3]],   # 基隆 / 北台灣 TWKEL
        [[22.0, 119.8], [23.3, 120.9]],   # 高雄 TWKHH（aisstream 0 涵蓋，保留備用）
        # 外國 hub（普查實測有涵蓋、且在往台灣航線上）
        [[34.6, 128.5], [35.6, 129.7]],   # 釜山 KRPUS
        [[37.0, 126.1], [37.9, 127.1]],   # 仁川 KRINC
        [[35.0, 139.3], [35.9, 140.2]],   # 東京灣（東京 JPTYO / 橫濱 JPYOK）
        [[34.4, 135.0], [34.9, 135.7]],   # 大阪灣（大阪 JPOSA / 神戶 JPUKB）
        [[21.8, 113.6], [22.9, 114.8]],   # 香港 / 深圳 HKHKG
        [[0.8, 103.3], [1.7, 104.4]],     # 新加坡 SGSIN
        [[-6.6, 106.3], [-5.6, 107.4]],   # 雅加達 IDJKT
        [[14.1, 120.5], [15.1, 121.5]],   # 馬尼拉 PHMNL
        [[12.8, 100.3], [13.9, 101.2]],   # 曼谷 / 林查班 THLCH
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
    # MOTC×aisstream 串聯結果（link_sources.py 輸出），供 MOTCAISProvider 讀取
    linked_arrivals_file: str = str(DATA_DIR / "linked_arrivals.json")

    # 風險 / 推播
    notify_min_level: str = "high"        # low | medium | high | critical


settings = Settings()
