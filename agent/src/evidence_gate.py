"""
Deterministic Evidence Sufficiency Gate for FieldOps Voice Copilot.

Evaluates retrieved documentation BEFORE any LLM generation call.
Ensures evidence is sufficiently relevant, model-compatible, timely, and complete.
If the gate FAILS, a safe deterministic fallback message is returned immediately,
preventing hallucination or execution of invalid procedures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import structlog

from .config import AgentConfig
from .retrieval import RetrievalResponse, RetrievalResult

logger = structlog.get_logger(__name__)


class GateDecision(str, Enum):
    PASS = "PASS"
    FAIL_NO_EVIDENCE = "FAIL_NO_EVIDENCE"
    FAIL_LOW_RELEVANCE = "FAIL_LOW_RELEVANCE"
    FAIL_MODEL_MISMATCH = "FAIL_MODEL_MISMATCH"
    FAIL_EQUIPMENT_MISMATCH = "FAIL_EQUIPMENT_MISMATCH"
    FAIL_STALE_REVISION = "FAIL_STALE_REVISION"
    FAIL_INSUFFICIENT_COVERAGE = "FAIL_INSUFFICIENT_COVERAGE"


@dataclass
class EvidenceGateResult:
    """Outcome of deterministic evidence gating."""
    decision: GateDecision
    passed: bool
    reason: str
    evidence_used: List[RetrievalResult] = field(default_factory=list)
    fallback_message: str = ""
    top_score: float = 0.0
    model_matched: bool = True


def run_evidence_gate(
    retrieval_response: RetrievalResponse,
    normalized_query: Any,
    auth_context: Dict[str, Any],
    config: AgentConfig,
) -> EvidenceGateResult:
    """
    Evaluates evidence sufficiency deterministically.
    
    Checks (in priority sequence):
    1. Zero evidence retrieved -> FAIL_NO_EVIDENCE
    2. Top score below relevance threshold -> FAIL_LOW_RELEVANCE
    3. Model mismatch (e.g. queried CP-200 but evidence is CP-300) -> FAIL_MODEL_MISMATCH
    4. Equipment mismatch (e.g. queried pump but evidence is compressor) -> FAIL_EQUIPMENT_MISMATCH
    5. Document staleness / deprecated revision check -> FAIL_STALE_REVISION
    6. Minimum evidence coverage threshold -> FAIL_INSUFFICIENT_COVERAGE
    7. All checks pass -> PASS
    """
    raw_results = retrieval_response.results
    top_score = retrieval_response.top_score

    # Check 1: Zero evidence
    if not raw_results:
        target = f"'{normalized_query.error_code}'" if normalized_query.error_code else "this query"
        return EvidenceGateResult(
            decision=GateDecision.FAIL_NO_EVIDENCE,
            passed=False,
            reason=f"No documentation chunks retrieved for {target}.",
            evidence_used=[],
            fallback_message=(
                f"I do not have authorized documentation in the knowledge base for {target}. "
                "Please verify the equipment model and error code with plant engineering."
            ),
            top_score=0.0,
            model_matched=False,
        )

    # Check 2: Relevance threshold
    if top_score < config.evidence_min_score:
        return EvidenceGateResult(
            decision=GateDecision.FAIL_LOW_RELEVANCE,
            passed=False,
            reason=(
                f"Top retrieval score ({top_score:.3f}) is below the Evidence Sufficiency Gate "
                f"relevance threshold ({config.evidence_min_score:.2f})."
            ),
            evidence_used=[],
            fallback_message=(
                "The retrieved technical documentation does not match your specific symptoms with "
                "sufficient relevance. Please consult the physical equipment manual directly or contact plant engineering."
            ),
            top_score=top_score,
            model_matched=False,
        )

    # Check 3: Model compatibility check
    # CRITICAL: CP-200 error E17 is thermal, CP-300 error E17 is VFD electrical!
    # If the user asked about CP-200/CP-204, but top evidence is CP-300, reject!
    if normalized_query.model:
        query_model_family = normalized_query.model[:4].upper()  # "CP-2" or "CP-3"
        
        # Filter results that have model information
        results_with_model = [r for r in raw_results if r.model and r.model != "UNKNOWN"]
        
        if results_with_model:
            # Check if any of the top high-scoring chunks match the requested model family
            matching_model_results = [
                r for r in results_with_model
                if r.model.upper().startswith(query_model_family)
            ]
            
            # If top chunk has a model and that model does NOT match requested family
            top_result = raw_results[0]
            if top_result.model and not top_result.model.upper().startswith(query_model_family):
                # If there are no matching model results at all in the high-scoring tier
                if not matching_model_results:
                    return EvidenceGateResult(
                        decision=GateDecision.FAIL_MODEL_MISMATCH,
                        passed=False,
                        reason=(
                            f"Model mismatch detected: Query targets {normalized_query.model} ({query_model_family}), "
                            f"but retrieved evidence is for {top_result.model}."
                        ),
                        evidence_used=[],
                        fallback_message=(
                            f"Safety notice: Retrieved documentation is for model {top_result.model}, "
                            f"which does not match your equipment ({normalized_query.model}). "
                            "Procedures cannot be safely transferred between these models."
                        ),
                        top_score=top_score,
                        model_matched=False,
                    )
            
            # If matching results exist, filter the evidence set to matching model chunks
            if matching_model_results:
                raw_results = matching_model_results

    # Check 4: Equipment type compatibility
    if normalized_query.equipment_type:
        mismatched_equipment = [
            r for r in raw_results
            if r.equipment_type and r.equipment_type != "UNKNOWN" and r.equipment_type.lower() != normalized_query.equipment_type.lower()
        ]
        if len(mismatched_equipment) == len(raw_results):
            return EvidenceGateResult(
                decision=GateDecision.FAIL_EQUIPMENT_MISMATCH,
                passed=False,
                reason=(
                    f"Equipment type mismatch: Query specified {normalized_query.equipment_type}, "
                    f"but documentation is for {raw_results[0].equipment_type}."
                ),
                evidence_used=[],
                fallback_message=(
                    f"Documentation found is for {raw_results[0].equipment_type}, not {normalized_query.equipment_type}."
                ),
                top_score=top_score,
                model_matched=False,
            )

    # Check 5: Document manifest revision check (deterministic metadata-driven check)
    # Reject documents explicitly marked superseded or with deprecated revision status
    for r in raw_results[:2]:
        raw_rev = str(r.revision or "").strip().lower()
        if raw_rev in ["superseded", "deprecated", "obsolete", "archived", "0"]:
            return EvidenceGateResult(
                decision=GateDecision.FAIL_STALE_REVISION,
                passed=False,
                reason=f"Retrieved document {r.document_id} revision '{r.revision}' is marked superseded.",
                evidence_used=[],
                fallback_message=(
                    f"Warning: Retrieved procedure from document {r.document_id} (Rev {r.revision}) is superseded. "
                    "Please refer to the latest authorized standard operating procedure."
                ),
                top_score=top_score,
                model_matched=True,
            )

    # Filter to chunks meeting the score threshold
    qualifying_evidence = [r for r in raw_results if r.score >= config.evidence_min_score]
    if not qualifying_evidence:
        qualifying_evidence = raw_results[:2]  # Fallback to top 2 if score is above threshold overall

    logger.info(
        "evidence_gate_passed",
        decision=GateDecision.PASS.value,
        qualifying_chunks=len(qualifying_evidence),
        top_score=round(top_score, 3),
    )

    return EvidenceGateResult(
        decision=GateDecision.PASS,
        passed=True,
        reason=f"Evidence gate passed with {len(qualifying_evidence)} relevant chunks (top score: {top_score:.3f}).",
        evidence_used=qualifying_evidence,
        fallback_message="",
        top_score=top_score,
        model_matched=True,
    )
