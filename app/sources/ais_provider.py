"""AIS 來源層：抽象介面 + 模擬實作。

上層（track_builder）只依賴 AISProvider 介面，切換 mock / aisstream / 付費 API
時不需改動分析邏輯（實作計畫 §8.3）。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import settings


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


def get_provider() -> AISProvider:
    """依設定回傳 AIS 來源實作。"""
    provider = settings.ais_provider.lower()
    if provider == "mock":
        return MockAISProvider()
    # aisstream 等未來實作預留
    raise NotImplementedError(f"AIS provider 尚未實作: {provider}")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
