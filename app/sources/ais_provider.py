"""AIS 來源層：抽象介面 + 模擬實作 + aisstream.io 即時實作。

上層（track_builder）只依賴 AISProvider 介面，切換 mock / aisstream / 付費 API
時不需改動分析邏輯（實作計畫 §8.3）。

aisstream.io 是「即時位置串流」，不提供航跡歷史。因此 AISStreamProvider 的策略：
連線一段時間、收集台灣周邊即時船位，用「港口座標鄰近 + 低船速」偵測靠港，
並把每次觀測累積到 data/ais_sightings.json，讓靠港序列隨排程多次執行逐步補齊
（到港=首次在港區被看到，離港=之後在他處/離開港區時補上）。
詳見 docs/資料來源與真假對照.md 與 README「即時進港船」段落。
"""
from __future__ import annotations

import asyncio
import csv
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

# 位置類訊息（帶經緯度與 SOG）
_POSITION_TYPES = {
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
}


@dataclass
class PortCallRecord:
    """單筆靠港紀錄（來源層原始輸出，未入庫）。"""

    ship_code: str
    mmsi: str | None
    imo: str | None
    name: str | None
    port_unlocode: str
    arrival: datetime
    departure: datetime | None
    source: str = "mock"


class AISProvider(ABC):
    """AIS 來源抽象介面。"""

    source_name: str = "ais"

    @abstractmethod
    def fetch_port_calls(self) -> list[PortCallRecord]:
        """回傳所有已知船舶的靠港紀錄。"""
        raise NotImplementedError


class MockAISProvider(AISProvider):
    """讀取 data/mock_ais.json 的模擬來源。"""

    source_name = "mock"

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or settings.ais_mock_file)

    def fetch_port_calls(self) -> list[PortCallRecord]:
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)

        records: list[PortCallRecord] = []
        for ship in data.get("ships", []):
            for call in ship.get("calls", []):
                records.append(
                    PortCallRecord(
                        ship_code=ship["ship_code"],
                        mmsi=ship.get("mmsi"),
                        imo=ship.get("imo"),
                        name=ship.get("name"),
                        port_unlocode=call["port"].strip().upper(),
                        arrival=_parse_dt(call["arrival"]),
                        departure=_parse_dt(call.get("departure")),
                        source=self.source_name,
                    )
                )
        return records


class AISStreamProvider(AISProvider):
    """aisstream.io 即時來源：連線收集台灣周邊船位，偵測靠港並累積成序列。

    每次 fetch_port_calls()：
      1. 連 wss://stream.aisstream.io/v0/stream，訂閱設定的 bounding box。
      2. 收集 ais_collect_seconds 秒的即時訊息。
      3. 用港口座標鄰近（ais_port_radius_km）+ 低船速（ais_port_max_sog）偵測「在港」。
      4. 併入 data/ais_sightings.json（到港/離港隨多次執行補齊）。
      5. 由累積後的 sightings 產生 PortCallRecord。
    """

    source_name = "aisstream"
    WS_URL = "wss://stream.aisstream.io/v0/stream"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.aisstream_api_key
        self.bboxes = settings.ais_bbox
        self.collect_seconds = settings.ais_collect_seconds
        self.radius_km = settings.ais_port_radius_km
        self.max_sog = settings.ais_port_max_sog
        self.sightings_path = Path(settings.ais_sightings_file)
        self._ports = _load_port_coords()

    # --- 對外介面 ------------------------------------------------------
    def fetch_port_calls(self) -> list[PortCallRecord]:
        if not self.api_key:
            raise RuntimeError(
                "AISSTREAM_API_KEY 未設定，無法使用 aisstream 來源。請在 .env 填入金鑰。"
            )
        observations = self._collect()
        store = self._merge_into_store(observations)
        return self._records_from_store(store)

    # --- 步驟 1-2：連線收集 --------------------------------------------
    def _collect(self) -> dict[str, dict]:
        """連線收集一段時間，回傳 {mmsi: 聚合觀測}。"""
        return asyncio.run(self._collect_async())

    async def _collect_async(self) -> dict[str, dict]:
        import websockets  # 延遲匯入：mock 模式不需安裝

        subscribe = {
            "APIKey": self.api_key,
            "BoundingBoxes": self.bboxes,
            "FilterMessageTypes": ["PositionReport", "ShipStaticData",
                                   "StandardClassBPositionReport",
                                   "ExtendedClassBPositionReport"],
        }
        agg: dict[str, dict] = {}
        async with websockets.connect(self.WS_URL, ping_interval=None) as ws:
            await ws.send(json.dumps(subscribe))
            loop = asyncio.get_event_loop()
            deadline = loop.time() + self.collect_seconds
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                self._ingest_message(json.loads(raw), agg)
        return agg

    def _ingest_message(self, msg: dict, agg: dict[str, dict]) -> None:
        mtype = msg.get("MessageType")
        meta = msg.get("MetaData", {})
        mmsi = meta.get("MMSI")
        if mmsi is None:
            return
        mmsi = str(mmsi)
        rec = agg.setdefault(mmsi, {"mmsi": mmsi, "imo": None, "name": None,
                                    "destination": None, "lat": None, "lon": None,
                                    "sog": None, "ts": None})

        ts = _parse_ais_time(meta.get("time_utc"))
        name = (meta.get("ShipName") or "").strip() or None

        if mtype in _POSITION_TYPES:
            body = msg.get("Message", {}).get(mtype, {})
            lat = body.get("Latitude", meta.get("latitude"))
            lon = body.get("Longitude", meta.get("longitude"))
            sog = body.get("Sog")
            # 取每船最新一筆位置
            if ts and (rec["ts"] is None or ts >= rec["ts"]):
                rec["lat"], rec["lon"], rec["sog"], rec["ts"] = lat, lon, sog, ts
            rec["name"] = rec["name"] or name

        elif mtype == "ShipStaticData":
            body = msg.get("Message", {}).get("ShipStaticData", {})
            imo = body.get("ImoNumber")
            rec["imo"] = rec["imo"] or (str(imo) if imo else None)
            rec["name"] = (body.get("Name") or "").strip() or rec["name"] or name
            dest = (body.get("Destination") or "").strip()
            rec["destination"] = dest or rec["destination"]

    # --- 步驟 3-4：偵測在港 + 併入 sightings ---------------------------
    def _merge_into_store(self, observations: dict[str, dict]) -> dict:
        store = self._load_store()
        ships = store.setdefault("ships", {})
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

        for mmsi, obs in observations.items():
            ship = ships.setdefault(mmsi, {"mmsi": mmsi, "imo": None, "name": None,
                                           "destination": None, "calls": {}})
            ship["imo"] = obs.get("imo") or ship.get("imo")
            ship["name"] = obs.get("name") or ship.get("name")
            ship["destination"] = obs.get("destination") or ship.get("destination")

            ts_iso = (obs["ts"].isoformat(timespec="seconds")
                      if obs.get("ts") else now_iso)
            current_port = self._nearest_port(obs)
            calls = ship["calls"]

            for port, call in calls.items():
                if call.get("open") and port != current_port:
                    # 這艘船已離開先前港區 → 補上離港時間
                    call["departure"] = call.get("last_seen_near") or ts_iso
                    call["open"] = False

            if current_port:
                call = calls.get(current_port)
                if call and call.get("open"):
                    call["last_seen_near"] = ts_iso
                else:
                    calls[current_port] = {
                        "arrival": ts_iso,
                        "departure": None,
                        "last_seen_near": ts_iso,
                        "open": True,
                    }

        store["updated_at"] = now_iso
        self._save_store(store)
        return store

    def _nearest_port(self, obs: dict) -> str | None:
        """回傳船目前所在港口 UN/LOCODE；不在任何港區則 None。"""
        lat, lon, sog = obs.get("lat"), obs.get("lon"), obs.get("sog")
        if lat is None or lon is None:
            return None
        # 明顯航行中（SOG 高）視為過境、非靠港
        if sog is not None and sog > self.max_sog:
            return None
        best, best_km = None, self.radius_km
        for unlocode, (plat, plon) in self._ports.items():
            d = _haversine_km(lat, lon, plat, plon)
            if d <= best_km:
                best, best_km = unlocode, d
        return best

    # --- 步驟 5：由 sightings 產生靠港紀錄 -----------------------------
    def _records_from_store(self, store: dict) -> list[PortCallRecord]:
        records: list[PortCallRecord] = []
        for mmsi, ship in store.get("ships", {}).items():
            for port, call in ship.get("calls", {}).items():
                records.append(
                    PortCallRecord(
                        ship_code=mmsi,
                        mmsi=mmsi,
                        imo=ship.get("imo"),
                        name=ship.get("name"),
                        port_unlocode=port,
                        arrival=_parse_dt(call["arrival"]),
                        departure=_parse_dt(call.get("departure")),
                        source=self.source_name,
                    )
                )
        return records

    # --- sightings 讀寫 ------------------------------------------------
    def _load_store(self) -> dict:
        if self.sightings_path.exists():
            with open(self.sightings_path, encoding="utf-8") as f:
                return json.load(f)
        return {"ships": {}}

    def _save_store(self, store: dict) -> None:
        self.sightings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sightings_path, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)


class MOTCLinkProvider(AISProvider):
    """由 MOTC×aisstream 串聯結果（linked_arrivals.json）產生靠港序列。

    每艘串聯成功的船 → 兩筆靠港：前一外國港（aisstream 在外國 hub 拍到的時間）
    + 台灣抵達港（MOTC 拍到的時間）。這讓風險引擎能對「真實抵達高雄、且有真實
    前一外國港」的船跑時序比對——即「高雄 × 真船 × 真前一港 × 真疫情」。
    串聯與涵蓋限制見 docs/資料來源與真假對照.md、AIS來源評估與升級路徑.md。
    """

    source_name = "motc_link"

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or settings.linked_arrivals_file)

    def fetch_port_calls(self) -> list[PortCallRecord]:
        if not self.path.exists():
            raise RuntimeError(
                f"找不到 {self.path}；請先跑 scripts/link_sources.py 產生串聯結果。"
            )
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)

        records: list[PortCallRecord] = []
        for r in data:
            mmsi = r["mmsi"]
            imo = r.get("imo")
            name = r.get("name")
            records.append(PortCallRecord(
                ship_code=mmsi, mmsi=mmsi, imo=imo, name=name,
                port_unlocode=r["prev_foreign_port"].strip().upper(),
                arrival=_parse_dt(r["prev_seen_utc"]), departure=None,
                source=self.source_name,
            ))
            records.append(PortCallRecord(
                ship_code=mmsi, mmsi=mmsi, imo=imo, name=name,
                port_unlocode=r["tw_port"].strip().upper(),
                arrival=_parse_dt(r["tw_arrival_utc"]), departure=None,
                source=self.source_name,
            ))
        return records


def get_provider() -> AISProvider:
    """依設定回傳 AIS 來源實作。"""
    provider = settings.ais_provider.lower()
    if provider == "mock":
        return MockAISProvider()
    if provider == "aisstream":
        return AISStreamProvider()
    if provider == "motc":
        return MOTCLinkProvider()
    raise NotImplementedError(f"AIS provider 尚未實作: {provider}")


# --- 工具函式 ----------------------------------------------------------
def _load_port_coords() -> dict[str, tuple[float, float]]:
    """從 data/ports_seed.csv 載入 {UN/LOCODE: (lat, lon)}。"""
    path = Path(settings.ports_seed_file)
    ports: dict[str, tuple[float, float]] = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lat, lon = row.get("lat"), row.get("lon")
            if lat and lon:
                ports[row["unlocode"].strip().upper()] = (float(lat), float(lon))
    return ports


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parse_ais_time(value: str | None) -> datetime | None:
    """aisstream time_utc 例：'2026-07-05 10:08:51.244... +0000 UTC' → naive UTC datetime。"""
    if not value:
        return None
    try:
        head = value.split(".")[0].split(" +")[0].strip()  # '2026-07-05 10:08:51'
        return datetime.fromisoformat(head)
    except (ValueError, IndexError):
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
