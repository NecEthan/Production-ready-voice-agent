"""
OpenTelemetry setup for the Peptide Voice Agent.

Call setup_tracing() once at process startup before any instrumented code runs.

Exporters:
  - ENVIRONMENT=development  → ConsoleSpanExporter (stdout, human-readable)
  - ENVIRONMENT=production   → OTLPSpanExporter (gRPC to OTEL_EXPORTER_OTLP_ENDPOINT)

livekit-agents already emits spans for LLM/STT/TTS calls using the same OTel
API, so those flows will appear automatically inside our session spans once a
TracerProvider is configured.
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes

logger = logging.getLogger(__name__)

SERVICE_NAME = "peptide-voice-agent"
SERVICE_VERSION = "1.0.0"

_tracer: trace.Tracer | None = None


def setup_tracing() -> None:
    """
    Configure the global TracerProvider.

    Call once at startup — idempotent (re-calls are no-ops after first call).
    """
    global _tracer
    if _tracer is not None:
        return

    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAME: SERVICE_NAME,
            ResourceAttributes.SERVICE_VERSION: SERVICE_VERSION,
        }
    )

    provider = TracerProvider(resource=resource)

    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production":
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        logger.info("OTel tracing → OTLP gRPC at %s", endpoint)
    else:
        exporter = ConsoleSpanExporter()
        logger.info("OTel tracing → Console (development mode)")

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _tracer = trace.get_tracer(SERVICE_NAME, SERVICE_VERSION)
    logger.info("Distributed tracing initialised (service=%s)", SERVICE_NAME)


def get_tracer() -> trace.Tracer:
    """Return the module-level tracer. setup_tracing() must have been called first."""
    if _tracer is None:
        raise RuntimeError("setup_tracing() must be called before get_tracer()")
    return _tracer
