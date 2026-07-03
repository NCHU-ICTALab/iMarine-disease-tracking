"""規則式風險評分引擎（分析層 ③，依 WHO IHR 精神，可解釋、不用 ML）。

對 matcher 的每筆命中，以五個維度加權計分，再乘上「近因衰減」；
以船舶所有命中的最高分作為整體風險，並映射風險等級與防護建議。
每筆計分依據都保留在輸出中（Grounding / 可解釋性）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from app.analysis.matcher import Match
from app.analysis.pathogens import lookup as lookup_pathogen

# 維度權重（總和 = 1）。以港邊人員的人傳人風險為最重。
WEIGHTS = {
    "transmissibility": 0.30,
    "severity": 0.25,
    "temporal_fit": 0.25,
    "stay": 0.10,
    "recency": 0.10,
}

# 近因衰減：前一個外國港權重最高，往前每一站遞減。
PROXIMITY_DECAY = 0.7

# 分數 → 等級門檻
LEVEL_THRESHOLDS = [
    (0.75, "critical"),
    (0.55, "high"),
    (0.35, "medium"),
    (0.0, "low"),
]

RECENCY_HALFLIFE_DAYS = 120  # 通報距今超過此天數，時效性權重約略折半


@dataclass
class ScoredMatch:
    match: dict
    dimensions: dict
    proximity_decay: float
    event_score: float


def score_match(m: Match, as_of: date | None = None) -> ScoredMatch:
    as_of = as_of or date.today()
    pathogen = lookup_pathogen(m.disease)

    # 1) 傳播度（對港邊人員的人傳人風險）
    transmissibility = pathogen.transmissibility
    # 2) 嚴重度（含 PHEIC 加成）
    severity = min(1.0, pathogen.severity + (0.15 if (pathogen.pheic or m.is_pheic) else 0.0))
    # 3) 時序吻合度（matcher 已算）
    temporal_fit = m.temporal_fit
    # 4) 停留時間（>=3 天視為充分暴露）
    stay = min(1.0, m.stay_days / 3.0)
    # 5) 時效性（通報距評估日越近越高，指數衰減）
    days_since = max(0, (as_of - date.fromisoformat(m.report_date)).days)
    recency = 0.5 ** (days_since / RECENCY_HALFLIFE_DAYS)

    dims = {
        "transmissibility": round(transmissibility, 3),
        "severity": round(severity, 3),
        "temporal_fit": round(temporal_fit, 3),
        "stay": round(stay, 3),
        "recency": round(recency, 3),
    }
    weighted = sum(WEIGHTS[k] * v for k, v in dims.items())
    decay = PROXIMITY_DECAY ** m.seq_position_from_last
    event_score = round(weighted * decay, 4)

    return ScoredMatch(match=asdict(m), dimensions=dims, proximity_decay=round(decay, 3),
                       event_score=event_score)


def level_of(score: float) -> str:
    for threshold, level in LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return "low"


def recommend(level: str, top: ScoredMatch | None) -> str:
    if top is None:
        return "無比對到疫情事件，維持一般港埠檢疫 SOP。"
    disease = top.match["disease"]
    route = lookup_pathogen(disease).route
    route_advice = {
        "respiratory": "全程配戴 N95、保持通風、避免密閉艙間長時間停留",
        "bodily_fluids": "穿戴手套/防護衣，避免接觸體液，落實手部衛生",
        "contact": "避免直接皮膚接觸，接觸後立即消毒手部與器具",
        "waterborne": "注意飲用水與食物衛生，勤洗手",
        "faecal_oral": "加強手部衛生與廁所清潔，注意飲食衛生",
        "vector": "港區噴藥防蚊、著長袖，降低病媒叮咬",
        "unknown": "採最高等級個人防護並回報疾管署評估",
    }.get(route, "採個人防護並回報疾管署評估")

    base = {
        "critical": f"【極高風險】對「{disease}」啟動最高防護：登輪人員完整 PPE、船員採檢與隔離、"
                    f"通報疾管署與港務檢疫。",
        "high": f"【高風險】對「{disease}」加強防護：登輪人員配戴防護裝備、優先安排船員健康監測、"
                f"通報港埠檢疫窗口。",
        "medium": f"【中風險】對「{disease}」提高警覺：登輪人員基本防護、留意船員症狀通報。",
        "low": f"【低風險】對「{disease}」維持一般檢疫 SOP，留意後續疫情更新。",
    }.get(level, "維持一般檢疫 SOP。")
    return f"{base} 建議措施：{route_advice}。"


def assess(matches: list[Match], as_of: date | None = None) -> dict:
    """彙整單船所有命中 → 風險分數、等級、防護建議與可解釋明細。"""
    if not matches:
        return {
            "score": 0.0,
            "risk_level": "low",
            "recommendation": recommend("low", None),
            "matched_events": [],
        }

    scored = sorted((score_match(m, as_of) for m in matches),
                    key=lambda s: s.event_score, reverse=True)
    top = scored[0]
    score = top.event_score
    level = level_of(score)

    return {
        "score": score,
        "risk_level": level,
        "recommendation": recommend(level, top),
        "matched_events": [
            {
                "port": s.match["port_unlocode"],
                "country": s.match["country"],
                "disease": s.match["disease"],
                "event_id": s.match["event_id"],
                "report_date": s.match["report_date"],
                "relation": s.match["relation"],
                "days_gap": s.match["days_gap"],
                "source": s.match["source"],
                "source_url": s.match["source_url"],
                "seq_position_from_last": s.match["seq_position_from_last"],
                "dimensions": s.dimensions,
                "proximity_decay": s.proximity_decay,
                "event_score": s.event_score,
            }
            for s in scored
        ],
    }
