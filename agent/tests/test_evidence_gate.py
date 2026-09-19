"""
Unit tests for Evidence Sufficiency Gate.
Verifies FR-004: Insufficient or incompatible evidence halts generation with safe refusal.
"""
import pytest
from agent.src.evidence_gate import run_evidence_gate, GateDecision
from agent.src.normalizer import normalize_query
from agent.src.retrieval import RetrievalResponse


def test_gate_passes_with_sufficient_compatible_evidence(
    sample_auth_context, agent_config, make_retrieval_result
):
    """High-relevance evidence matching the requested model passes the gate."""
    q = normalize_query("The compressor CP-204 is showing error E17.")
    good_chunk = make_retrieval_result(
        score=0.92,
        model="CP-200",
        text="Error E17 on CP-200: High discharge temperature above 185F.",
    )
    response = RetrievalResponse(
        results=[good_chunk],
        query=q.search_query,
        latency_ms=5.0,
        index_version="1.0.0",
        retrieval_id="ret-001",
    )

    result = run_evidence_gate(response, q, sample_auth_context, agent_config)

    assert result.passed is True
    assert result.decision == GateDecision.PASS
    assert len(result.evidence_used) == 1
    assert result.fallback_message == ""


def test_gate_fails_when_no_evidence_found(sample_auth_context, agent_config):
    """Zero retrieved chunks fails the gate with safe fallback."""
    q = normalize_query("Unknown compressor showing error E99.")
    empty_response = RetrievalResponse(
        results=[],
        query=q.search_query,
        latency_ms=3.0,
        index_version="1.0.0",
        retrieval_id="ret-002",
    )

    result = run_evidence_gate(empty_response, q, sample_auth_context, agent_config)

    assert result.passed is False
    assert result.decision == GateDecision.FAIL_NO_EVIDENCE
    assert "E99" in result.fallback_message or "documentation" in result.fallback_message


def test_gate_fails_on_model_mismatch(
    sample_auth_context, agent_config, make_retrieval_result
):
    """CRITICAL SAFETY TEST: CP-200 query must not use CP-300 evidence (VFD vs Thermal)."""
    q = normalize_query("CP-204 showing error E17.")
    # Top chunk is for CP-300 rotary screw VFD fault
    wrong_model_chunk = make_retrieval_result(
        score=0.89,
        model="CP-300",
        document_id="CP300-SVC-001",
        text="E17 on CP-300 signifies Motor Frequency Fault on the VFD inverter.",
    )
    response = RetrievalResponse(
        results=[wrong_model_chunk],
        query=q.search_query,
        latency_ms=4.1,
        index_version="1.0.0",
        retrieval_id="ret-003",
    )

    result = run_evidence_gate(response, q, sample_auth_context, agent_config)

    assert result.passed is False
    assert result.decision == GateDecision.FAIL_MODEL_MISMATCH
    assert "CP-300" in result.reason
    assert "does not match your equipment" in result.fallback_message


def test_gate_fails_on_low_relevance(
    sample_auth_context, agent_config, make_retrieval_result
):
    """Low-scoring generic documentation fails the gate."""
    q = normalize_query("Compressor CP-204 unusual vibration.")
    low_score_chunk = make_retrieval_result(
        score=0.35,  # below 0.65 threshold
        model="CP-200",
        text="General plant noise and ventilation overview.",
    )
    response = RetrievalResponse(
        results=[low_score_chunk],
        query=q.search_query,
        latency_ms=4.0,
        index_version="1.0.0",
        retrieval_id="ret-004",
    )

    result = run_evidence_gate(response, q, sample_auth_context, agent_config)

    assert result.passed is False
    assert result.decision == GateDecision.FAIL_LOW_RELEVANCE
    assert "does not match your specific symptoms" in result.fallback_message
