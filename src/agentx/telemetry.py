"""OpenTelemetry wiring. Every agent hop becomes a span the audit log can cite.

Degrades to a no-op when opentelemetry is not installed, so the domain core --
deadline math, idempotency, supervisor resilience -- is testable on a laptop
and in CI with nothing but pydantic. Anything that needs a cloud SDK to import
is something you cannot write a fast test for.
"""
from __future__ import annotations

import contextlib
import logging

from .config import PROJECT_SLUG, settings

log = logging.getLogger(PROJECT_SLUG)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _OTEL = True
except ImportError:  # local dev without cloud extras
    _OTEL = False

_configured = False


class _NullSpan:
    def set_attribute(self, *_a, **_k) -> None: ...


def configure() -> None:
    """Export to Cloud Trace when running on GCP, console otherwise."""
    global _configured
    if _configured or not _OTEL:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": PROJECT_SLUG}))
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        exporter = CloudTraceSpanExporter(project_id=settings.project_id)
    except Exception:  # no credentials, or running locally
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


@contextlib.contextmanager
def span(name: str, **attrs):
    if not _OTEL:
        yield _NullSpan()
        return
    configure()
    with trace.get_tracer(PROJECT_SLUG).start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v)
        yield s
