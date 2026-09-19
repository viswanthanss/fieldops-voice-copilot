"""
OpenTelemetry setup for FieldOps Voice Copilot.

Instruments FastAPI with tracing. Session and user context are injected
into spans so traces can be correlated with audit events.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def setup_telemetry(app) -> Optional[object]:  # noqa: ANN001
    """
    Configure OpenTelemetry tracing for the FastAPI application.

    When OTEL_ENDPOINT is set, exports traces via OTLP/gRPC to that endpoint
    (e.g. a local Jaeger or Grafana Tempo instance). When absent, a
    no-op tracer is used so the application runs without any observability
    infrastructure.

    Args:
        app: The FastAPI application instance.

    Returns:
        The tracer provider, or None if telemetry is disabled.
    """
    from app.config import settings

    if not settings.OTEL_ENDPOINT:
        logger.info("OTEL_ENDPOINT not set — telemetry disabled.")
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": "fieldops-voice-copilot-backend"})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=settings.OTEL_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry configured → %s", settings.OTEL_ENDPOINT)
        return provider

    except ImportError as exc:
        logger.warning("OpenTelemetry packages not installed (%s) — telemetry disabled.", exc)
        return None
    except Exception as exc:
        logger.error("Failed to set up OpenTelemetry: %s", exc)
        return None


def get_tracer():
    """
    Return the application-level OpenTelemetry tracer.

    Returns:
        An OpenTelemetry Tracer (real or no-op depending on configuration).
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer("fieldops.backend")
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """Minimal no-op tracer to avoid ImportError in environments without OTel."""

    class _Span:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def set_attribute(self, *_):
            pass

    def start_as_current_span(self, name: str, **_):  # noqa: D102
        return self._Span()
