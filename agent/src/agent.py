"""
FieldOps Voice Copilot — Realtime Voice AI Agent

Architecture Hot Path:
Technician Audio -> STT -> Query Normalizer -> Authorization Context ->
Embedded Moss Runtime -> Evidence Sufficiency Gate -> LLM Generator ->
Grounding Validator -> Streaming TTS -> LiveKit Realtime Audio -> Technician

FastAPI and PostgreSQL are NOT on this hot path.
All retrieval executes against the embedded, in-process Moss index with <10ms latency.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
import structlog
from openai import AsyncOpenAI

from .authorization import AuthorizationDeniedError, build_moss_metadata_filter, verify_retrieval_scope
from .config import AgentConfig, config
from .evidence_gate import GateDecision, run_evidence_gate
from .grounding import validate_grounding
from .normalizer import normalize_query
from .prompts import PROMPT_HASH, PROMPT_VERSION, build_response_messages
from .retrieval import MossRetriever
from .session import create_session_store
from .telemetry import get_tracer, setup_telemetry

logger = structlog.get_logger(__name__)
tracer = get_tracer()
session_store = create_session_store(config.redis_url)

# Global singleton embedded retriever (pre-warmed at worker startup)
retriever: Optional[MossRetriever] = None


def get_retriever() -> MossRetriever:
    global retriever
    if retriever is None:
        retriever = MossRetriever(config)
    return retriever


async def process_voice_turn(
    query_text: str,
    session_id: str,
    auth_context: Dict[str, Any],
    turn_id: int,
    conversation_context: List[Dict[str, str]],
    openai_client: Optional[AsyncOpenAI] = None,
    moss_retriever: Optional[MossRetriever] = None,
) -> Dict[str, Any]:
    """
    Executes a single voice interaction through the evidence-gated pipeline.

    Returns:
        Structured result dict containing:
        - spoken_response: text to be fed into streaming TTS
        - evidence_gate_decision: PASS | FAIL_*
        - grounding_status: PASS | FAIL
        - retrieved_evidence: metadata for UI attribution
        - latencies: granular timing breakdown (ms)
    """
    turn_start = time.perf_counter()
    active_retriever = moss_retriever or get_retriever()
    client = openai_client or AsyncOpenAI(api_key=config.openai_api_key)

    timing: Dict[str, float] = {}

    with tracer.start_as_current_span("voice_turn") as span:
        span.set_attribute("session_id", session_id)
        span.set_attribute("turn_id", turn_id)
        span.set_attribute("prompt_version", PROMPT_VERSION)
        span.set_attribute("prompt_hash", PROMPT_HASH)

        # ── Step 1: Query Normalization (<1ms) ────────────────────────────────
        t0 = time.perf_counter()
        normalized = normalize_query(query_text)
        timing["normalization_ms"] = (time.perf_counter() - t0) * 1000

        span.set_attribute("normalized.error_code", normalized.error_code or "")
        span.set_attribute("normalized.model", normalized.model or "")
        span.set_attribute("normalized.asset_id", normalized.asset_id or "")
        span.set_attribute("normalized.intent", normalized.intent)

        # ── Step 2: Authorization Scope Check (Pre-retrieval security boundary) ──
        t0 = time.perf_counter()
        try:
            approved_constraints = verify_retrieval_scope(
                auth_context=auth_context,
                requested_asset_id=normalized.asset_id,
                requested_model=normalized.model,
            )
            timing["authorization_ms"] = (time.perf_counter() - t0) * 1000
        except AuthorizationDeniedError as auth_err:
            timing["authorization_ms"] = (time.perf_counter() - t0) * 1000
            fallback = (
                f"Access denied: {str(auth_err)} Equipment outside your authorized maintenance "
                "scope cannot be accessed. Please contact your site supervisor."
            )
            return {
                "spoken_response": fallback,
                "evidence_gate_decision": "FAIL_UNAUTHORIZED",
                "grounding_status": "SKIPPED",
                "retrieved_evidence": [],
                "latencies": timing,
                "total_latency_ms": (time.perf_counter() - turn_start) * 1000,
            }

        # ── Step 3: Embedded Moss Retrieval (<10ms target) ────────────────────
        t0 = time.perf_counter()
        metadata_filter = build_moss_metadata_filter(approved_constraints, normalized)

        retrieval_response = await active_retriever.query(
            query_text=normalized.search_query,
            metadata_filter=metadata_filter,
            top_k=config.moss_top_k,
        )
        timing["retrieval_ms"] = (time.perf_counter() - t0) * 1000
        span.set_attribute("retrieval.id", retrieval_response.retrieval_id)
        span.set_attribute("retrieval.chunk_count", len(retrieval_response.results))
        span.set_attribute("retrieval.top_score", retrieval_response.top_score)

        # ── Step 4: Evidence Sufficiency Gate (Deterministic pre-LLM check) ───
        t0 = time.perf_counter()
        gate_result = run_evidence_gate(
            retrieval_response=retrieval_response,
            normalized_query=normalized,
            auth_context=auth_context,
            config=config,
        )
        timing["evidence_gate_ms"] = (time.perf_counter() - t0) * 1000
        span.set_attribute("evidence_gate.decision", gate_result.decision.value)

        # If evidence gate FAILS, safe fallback returned immediately — ZERO LLM calls!
        if not gate_result.passed:
            total_lat = (time.perf_counter() - turn_start) * 1000
            return {
                "spoken_response": gate_result.fallback_message,
                "evidence_gate_decision": gate_result.decision.value,
                "grounding_status": "SKIPPED",
                "retrieved_evidence": [
                    {
                        "document_id": r.document_id,
                        "revision": r.revision,
                        "score": r.score,
                        "model": r.model,
                        "section": r.section,
                    }
                    for r in retrieval_response.results[:2]
                ],
                "latencies": timing,
                "total_latency_ms": total_lat,
            }

        # ── Step 5: LLM Response Generation ───────────────────────────────────
        t0 = time.perf_counter()
        messages = build_response_messages(
            evidence_chunks=gate_result.evidence_used,
            query=query_text,
            conversation_context=conversation_context,
        )

        llm_response = await client.chat.completions.create(
            model=config.llm_model,
            messages=messages,
            temperature=config.llm_temperature,
            max_tokens=config.max_response_tokens,
        )
        candidate_text = llm_response.choices[0].message.content or ""
        timing["llm_generation_ms"] = (time.perf_counter() - t0) * 1000

        # ── Step 6: Grounding Validation (Post-generation safety audit) ────────
        t0 = time.perf_counter()
        grounding_result = await validate_grounding(
            candidate_response=candidate_text,
            evidence_chunks=gate_result.evidence_used,
            openai_client=client,
            model=config.llm_model,
        )
        timing["grounding_validation_ms"] = (time.perf_counter() - t0) * 1000
        span.set_attribute("grounding.passed", grounding_result.passed)

        final_response_text = candidate_text

        # Controlled regeneration if grounding failed (max 1 retry)
        if not grounding_result.passed and config.grounding_max_retries > 0:
            logger.warning(
                "grounding_failed_retrying_once",
                unsupported=grounding_result.unsupported_claims,
                reason=grounding_result.failure_reason,
            )
            t_retry = time.perf_counter()
            retry_messages = messages + [
                {"role": "assistant", "content": candidate_text},
                {
                    "role": "user",
                    "content": (
                        f"SAFETY ALERT: Your previous response contained unsupported claims: {grounding_result.unsupported_claims}. "
                        "Regenerate your answer using ONLY the explicit facts in the authorized evidence. "
                        "If the evidence does not state the answer, state that directly."
                    ),
                },
            ]
            retry_resp = await client.chat.completions.create(
                model=config.llm_model,
                messages=retry_messages,
                temperature=0.0,
                max_tokens=config.max_response_tokens,
            )
            candidate_text = retry_resp.choices[0].message.content or ""
            timing["llm_retry_ms"] = (time.perf_counter() - t_retry) * 1000

            # Audit retry
            grounding_retry = await validate_grounding(
                candidate_response=candidate_text,
                evidence_chunks=gate_result.evidence_used,
                openai_client=client,
                model=config.llm_model,
            )
            if grounding_retry.passed:
                final_response_text = candidate_text
                grounding_result = grounding_retry
            else:
                # Safe refusal on repeated failure
                final_response_text = (
                    "I located the relevant technical documentation, but was unable to verify the procedural "
                    "safety of the generated response. Please consult the physical manual directly."
                )

        total_lat = (time.perf_counter() - turn_start) * 1000
        timing["total_ms"] = total_lat

        # Format source attribution payload for realtime UI transmission
        evidence_payload = [
            {
                "document_id": r.document_id,
                "document_type": r.document_type,
                "revision": r.revision,
                "effective_date": r.effective_date,
                "model": r.model,
                "section": r.section,
                "score": round(r.score, 3),
                "snippet": r.text[:200].replace("\n", " "),
            }
            for r in gate_result.evidence_used[:3]
        ]

        return {
            "spoken_response": final_response_text,
            "evidence_gate_decision": gate_result.decision.value,
            "grounding_status": "PASS" if grounding_result.passed else "FAIL",
            "retrieved_evidence": evidence_payload,
            "latencies": timing,
            "total_latency_ms": total_lat,
            "retrieval_id": retrieval_response.retrieval_id,
            "index_version": retrieval_response.index_version,
            "prompt_version": PROMPT_VERSION,
        }


# ══════════════════════════════════════════════════════════════════════════════
# LiveKit Worker Entrypoint (Official LiveKit Agents 1.x Server Pattern)
# ══════════════════════════════════════════════════════════════════════════════

try:
    from livekit.agents import AgentServer, AgentSession, Agent
    server = AgentServer()
except Exception:
    server = None


class FieldOpsVoiceAgent(Agent if "Agent" in locals() and Agent is not None else object):  # type: ignore
    """
    FieldOps Realtime Voice Agent with Pre-LLM Evidence Gating.
    Implements on_user_turn_completed to execute:
    query normalization -> scope authorization -> embedded Moss retrieval -> Evidence Sufficiency Gate
    BEFORE the LLM begins generating a response.
    """

    def __init__(
        self,
        auth_context: Dict[str, Any],
        session_id: str,
        retriever_instance: MossRetriever,
    ):
        super().__init__(
            instructions=SYSTEM_PROMPT_RESPONSE_GENERATOR,
        )
        self.auth_context = auth_context
        self.session_id = session_id
        self.retriever = retriever_instance
        self.turn_counter = 0

    async def on_user_turn_completed(
        self, turn_ctx: Any, new_message: Any
    ) -> None:
        """
        Official LiveKit lifecycle hook invoked immediately when user finishes speaking,
        BEFORE LLM generation begins.
        """
        self.turn_counter += 1
        query_text = getattr(new_message, "text_content", "") or str(new_message)
        logger.info(
            "on_user_turn_completed_rag",
            session_id=self.session_id,
            turn=self.turn_counter,
            query=query_text[:60],
        )

        normalized = normalize_query(query_text)

        # 1. Pre-retrieval scope check
        try:
            approved_constraints = verify_retrieval_scope(
                auth_context=self.auth_context,
                requested_asset_id=normalized.asset_id,
                requested_model=normalized.model,
            )
        except AuthorizationDeniedError as auth_err:
            refusal_text = (
                f"Access denied: {str(auth_err)} Equipment outside your authorized maintenance "
                "scope cannot be accessed. Please contact your site supervisor."
            )
            if hasattr(new_message, "text_content"):
                new_message.text_content = f"Instruction: Speak this exact refusal: '{refusal_text}'"
            return

        # 2. Embedded Moss Retrieval (<10ms)
        metadata_filter = build_moss_metadata_filter(approved_constraints, normalized)
        try:
            retrieval_response = await self.retriever.query(
                query_text=normalized.search_query,
                metadata_filter=metadata_filter,
                top_k=config.moss_top_k,
            )
        except Exception as exc:
            logger.error("moss_query_in_turn_failed", error=str(exc))
            return

        # 3. Deterministic Evidence Sufficiency Gate
        gate_result = run_evidence_gate(
            retrieval_response=retrieval_response,
            normalized_query=normalized,
            auth_context=self.auth_context,
            config=config,
        )

        if not gate_result.passed:
            logger.warning(
                "evidence_gate_blocked_llm",
                decision=gate_result.decision.value,
                reason=gate_result.reason,
            )
            if hasattr(new_message, "text_content"):
                new_message.text_content = (
                    f"Instruction: Speak this exact authorized fallback message: '{gate_result.fallback_message}'"
                )
            return

        # 4. Inject validated evidence into prompt context
        evidence_blocks = []
        for idx, r in enumerate(gate_result.evidence_used[:3], 1):
            evidence_blocks.append(
                f"[Evidence #{idx} | Doc: {r.document_id} Rev {r.revision} | Model: {r.model} | Section: {r.section}]\n{r.text}"
            )
        evidence_str = "\n\n".join(evidence_blocks)

        augmented_prompt = (
            f"=== AUTHORIZED TECHNICAL EVIDENCE ===\n{evidence_str}\n\n"
            f"=== TECHNICIAN QUESTION ===\n{query_text}\n\n"
            "Deliver 2 to 4 concise spoken sentences citing document ID and revision."
        )
        if hasattr(new_message, "text_content"):
            new_message.text_content = augmented_prompt


async def rtc_session_entrypoint(ctx: Any) -> None:
    """
    LiveKit Agents 1.x session handler.
    Connects to room, verifies auth context, configures voice pipeline, and runs agent session.
    """
    logger.info("livekit_session_connecting", room=ctx.room.name)
    await ctx.connect()

    session_id = f"sess-{uuid.uuid4().hex[:10]}"

    # Extract authorization context from room metadata (populated by FastAPI control plane)
    raw_metadata = ctx.room.metadata or "{}"
    try:
        meta = json.loads(raw_metadata)
        auth_context = meta.get("auth_context", {})
    except Exception:
        auth_context = {}

    # FAIL CLOSED: Never default to hardcoded demo privileges
    if not auth_context or not auth_context.get("tenant_id"):
        logger.error(
            "unauthorized_voice_session_rejected",
            room=ctx.room.name,
            reason="No valid server-derived auth_context found in room metadata. Session closed.",
        )
        await ctx.room.disconnect()
        return

    logger.info("livekit_session_authorized", session_id=session_id, tenant=auth_context.get("tenant_id"))

    active_retriever = get_retriever()
    if not active_retriever.is_ready:
        try:
            await active_retriever.initialize()
        except Exception as exc:
            logger.warning("moss_retriever_deferred_init", note=str(exc))

    try:
        from livekit.agents import AgentSession
        from livekit.plugins import openai as lk_openai
        from livekit.plugins import silero as lk_silero

        stt_plugin = lk_openai.STT()
        tts_plugin = lk_openai.TTS(voice=config.tts_voice)
        vad_plugin = lk_silero.VAD.load()
        llm_plugin = lk_openai.LLM(model=config.llm_model)

        agent = FieldOpsVoiceAgent(
            auth_context=auth_context,
            session_id=session_id,
            retriever_instance=active_retriever,
        )

        session = AgentSession(
            stt=stt_plugin,
            vad=vad_plugin,
            llm=llm_plugin,
            tts=tts_plugin,
        )

        logger.info("starting_livekit_voice_session", session_id=session_id)
        await session.start(agent=agent, room=ctx.room)
    except Exception as exc:
        logger.error("voice_pipeline_session_error", error=str(exc))


if server is not None:
    server.rtc_session(agent_name="fieldops-voice-copilot")(rtc_session_entrypoint)


if __name__ == "__main__":
    setup_telemetry(config)
    try:
        from livekit.agents import cli
        if server is not None:
            cli.run_app(server)
    except Exception as exc:
        logger.error("livekit_server_failed_to_start", error=str(exc))

