"""
Unit tests for Deterministic Query Normalizer.
Verifies error code, model family, asset ID, and intent extraction.
"""
import pytest
from agent.src.normalizer import normalize_query


def test_primary_demo_query_normalization():
    """Verify standard hackathon demo prompt normalization."""
    raw = "The compressor CP-204 is showing error E17. What should I check first?"
    q = normalize_query(raw)

    assert q.error_code == "E17"
    assert q.asset_id == "CP-204"
    assert q.model == "CP-200"
    assert q.equipment_type == "compressor"
    assert q.intent == "troubleshooting"
    assert "CP-200" in q.search_query
    assert "E17" in q.search_query


def test_cp300_query_normalization():
    raw = "Compressor CP-301 tripped on E17 with motor frequency fault."
    q = normalize_query(raw)

    assert q.error_code == "E17"
    assert q.asset_id == "CP-301"
    assert q.model == "CP-300"
    assert q.equipment_type == "compressor"
    assert q.intent == "troubleshooting"


def test_procedure_intent_detection():
    raw = "How do I replace the air intake filter on the CP-200?"
    q = normalize_query(raw)

    assert q.model == "CP-200"
    assert q.intent == "procedure"
    assert q.error_code is None


def test_symptom_extraction():
    raw = "Compressor CP-204 won't restart after overheating."
    q = normalize_query(raw)

    assert q.asset_id == "CP-204"
    assert q.model == "CP-200"
    assert q.symptom in ["won't restart", "overheating"]


def test_clean_input_without_identifiers():
    raw = "Hello, can you hear me on the headset?"
    q = normalize_query(raw)

    assert q.error_code is None
    assert q.model is None
    assert q.asset_id is None
    assert q.intent == "general"
