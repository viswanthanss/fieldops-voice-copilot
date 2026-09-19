"""
OpenTelemetry Instrumentation for FieldOps Voice Copilot Agent.

Provides distributed tracing and latency metrics across the realtime voice hot path:
session_init -> stt -> normalization -> authorization -> moss_retrieval ->
evidence_gate -> llm_generation -> grounding_validation -> tts -> interruption.

Correlates: session_id, turn_id, retrieval_id, trace_id, index_version, prompt_version, prompt_hash.
"""
from __future__ import annotations

import logging
from typing import Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

from .config import AgentConfig
from .prompts import PROMPT_HASH, PROMPT_VERSION

logger = logging.getLogger(__name__)

_tracer: Optional[trace.Tracer] = None


def setup_telemetry(config: AgentConfig) -> trace.Tracer:
    """Initialize OpenTelemetry tracer provider with OTLP or standard processor."""
    global _tracer
    
    resource = Resource.create({
        "service.name": config.otel_service_name,
        "service.version": "1.0.0",
        "agent.prompt_version": PROMPT_VERSION,
        "agent.prompt_hash": PROMPT_HASH,
        "agent.moss_index_version": config.moss_index_version,
    })

    provider = TracerProvider(resource=resource)

    if config.otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=config.otel_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTel exporter connected to %s", config.otel_endpoint)
        except Exception as exc:
            logger.warning("Could not initialize OTLP exporter (%s); using default provider", exc)

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(config.otel_service_name, "1.0.0")
    return _tracer


def get_tracer() -> trace.Tracer:
    """Get the active OpenTelemetry tracer."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer("fieldops-agent", "1.0.0")
    return _tracer
