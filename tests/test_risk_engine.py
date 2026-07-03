"""風險評分測試：傳播途徑差異、等級門檻、可解釋維度、近因衰減。"""
from __future__ import annotations

from datetime import date

from app.analysis.matcher import Match
from app.analysis.risk_engine import assess, level_of, score_match


def _match(disease: str, **kw) -> Match:
    base = dict(
        port_unlocode="CNSHA", country="CN", disease=disease, event_id=1,
        report_date=date(2026, 6, 25).isoformat(), is_pheic=False, severity_raw=None,
        source="test", source_url=None, relation="during_or_before", days_gap=-2,
        temporal_fit=1.0, stay_days=3.0, seq_position_from_last=0, incubation_max=14,
    )
    base.update(kw)
    return Match(**base)


def test_respiratory_scores_higher_than_vector():
    covid = score_match(_match("COVID-19"), as_of=date(2026, 7, 3)).event_score
    malaria = score_match(_match("瘧疾"), as_of=date(2026, 7, 3)).event_score
    assert covid > malaria  # 呼吸道人傳人 > 病媒


def test_level_thresholds():
    assert level_of(0.80) == "critical"
    assert level_of(0.60) == "high"
    assert level_of(0.40) == "medium"
    assert level_of(0.10) == "low"


def test_proximity_decay_reduces_score():
    near = score_match(_match("COVID-19", seq_position_from_last=0)).event_score
    far = score_match(_match("COVID-19", seq_position_from_last=2)).event_score
    assert far < near


def test_assess_reports_explainable_dimensions():
    result = assess([_match("COVID-19")], as_of=date(2026, 7, 3))
    assert result["risk_level"] in {"medium", "high", "critical"}
    ev = result["matched_events"][0]
    for dim in ("transmissibility", "severity", "temporal_fit", "stay", "recency"):
        assert dim in ev["dimensions"]
    assert result["recommendation"]


def test_empty_matches_low():
    result = assess([], as_of=date(2026, 7, 3))
    assert result["risk_level"] == "low"
    assert result["score"] == 0.0
    assert result["matched_events"] == []
