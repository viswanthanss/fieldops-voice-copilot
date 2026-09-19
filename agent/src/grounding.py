"""
Post-Generation Grounding Validator for FieldOps Voice Copilot.

Acts as the safety firewall between LLM generation and Text-to-Speech synthesis.
Audits candidate responses for factual fidelity against retrieved Moss evidence chunks.
Supports one controlled regeneration attempt on failure before safe refusal.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional
import structlog

from .prompts import build_grounding_messages
from .retrieval import RetrievalResult

logger = structlog.get_logger(__name__)


@dataclass
class GroundingResult:
    """Audit verdict from the Grounding Validator."""
    passed: bool
    confidence: float
    supported_claims: List[str] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)
    failure_reason: str = ""
    latency_ms: float = 0.0


async def validate_grounding(
    candidate_response: str,
    evidence_chunks: List[RetrievalResult],
    openai_client: Any,
    model: str = "gpt-4o-mini",
) -> GroundingResult:
    """
    Validates that every substantive claim in the candidate response is directly
    supported by the provided evidence chunks.

    Returns:
        GroundingResult with passed=True/False, claims audited, and latency.
    """
    if not evidence_chunks:
        return GroundingResult(
            passed=False,
            confidence=0.0,
            supported_claims=[],
            unsupported_claims=["Response has no supporting evidence chunks."],
            failure_reason="Grounding validation failed: evidence set is empty.",
            latency_ms=0.0,
        )

    messages = build_grounding_messages(candidate_response, evidence_chunks)
    start = time.perf_counter()

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        latency = (time.perf_counter() - start) * 1000

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        decision = parsed.get("decision", "FAIL").upper()
        supported = parsed.get("supported_claims", [])
        unsupported = parsed.get("unsupported_claims", [])
        failure_reason = parsed.get("failure_reason", "")
        # Mandatory invariant: Acceptance criterion is strictly PASS/FAIL.
        # Confidence is purely informational metadata for telemetry, never an acceptance threshold.
        passed = (decision == "PASS") and (len(unsupported) == 0)
        confidence = float(parsed.get("confidence", 0.8))

        logger.info(
            "grounding_validation_complete",
            passed=passed,
            confidence=round(confidence, 2),
            unsupported_count=len(unsupported),
            latency_ms=round(latency, 2),
        )

        return GroundingResult(
            passed=passed,
            confidence=confidence,
            supported_claims=supported,
            unsupported_claims=unsupported,
            failure_reason=failure_reason,
            latency_ms=latency,
        )

    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        logger.error("grounding_validator_exception", error=str(exc), latency_ms=latency)
        # Fail-safe principle: if validator fails, fail safe rather than emitting unverified audio
        return GroundingResult(
            passed=False,
            confidence=0.0,
            supported_claims=[],
            unsupported_claims=[f"Validator error: {str(exc)}"],
            failure_reason=f"Grounding validator internal error: {str(exc)}",
            latency_ms=latency,
        )
