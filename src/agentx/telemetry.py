"""OpenTelemetry wiring. Every agent hop becomes a span the audit log can cite."""
from __future__ import annotations

import contextlib
import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import PROJECT_SLUG, settings

log = logging.getLogger(PROJECT_SLUG)
_configured = False


def configure() -> None:
    """Export to Cloud Trace when running on GCP, console otherwise."""
    global _configured
    if _configured:
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": PROJECT_SLUG})
    )
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        exporter = CloudTraceSpanExporter(project_id=settings.project_id)
    except Exception:  # local dev, or no credentials
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


def tracer():
    configure()
    return trace.get_tracer(PROJECT_SLUG)


@contextlib.contextmanager
def span(name: str, **attrs):
    with tracer().start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v)
        yield s
