"""病原規則表載入與查詢（供 matcher 取潛伏期、risk_engine 取嚴重度/傳播度）。"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from app.config import DATA_DIR

PATHOGENS_YAML = DATA_DIR / "pathogens.yaml"


@dataclass(frozen=True)
class Pathogen:
    name: str
    incubation_min: int
    incubation_max: int
    transmissibility: float
    severity: float
    pheic: bool
    route: str
    match: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def _load() -> tuple[list[Pathogen], Pathogen]:
    with open(PATHOGENS_YAML, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    def _mk(d: dict, name: str | None = None) -> Pathogen:
        return Pathogen(
            name=d.get("name", name or "Unknown"),
            incubation_min=int(d["incubation_min"]),
            incubation_max=int(d["incubation_max"]),
            transmissibility=float(d["transmissibility"]),
            severity=float(d["severity"]),
            pheic=bool(d.get("pheic", False)),
            route=d.get("route", "unknown"),
            match=tuple(s.lower() for s in d.get("match", [])),
        )

    pathogens = [_mk(p) for p in raw.get("pathogens", [])]
    default = _mk(raw["default"], name="Unknown/Emerging")
    return pathogens, default


def lookup(disease: str) -> Pathogen:
    """依疾病名（中/英）以關鍵字子字串比對；未命中回傳保守預設。"""
    pathogens, default = _load()
    text = (disease or "").lower()
    for p in pathogens:
        if any(kw in text for kw in p.match):
            return p
    return default
