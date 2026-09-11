"""Optional Sentry and OpenTelemetry setup for the API process.

Prometheus metrics are always available at ``/metrics``. Managed error
reporting and trace export are enabled only when their explicit environment
settings are supplied, keeping local/test execution dependency-free at runtime
while providing a production-grade integration path.
"""

from typing import Any

from omnisource.config.logging import get_logger
from omnisource.config.settings import Settings

logger = get_logger(__name__)


def configure_observability(app: Any, settings: Settings) -> None:
    """Enable configured error reporting and tracing once for this app instance."""
    if getattr(app.state, "observability_configured", False):
        return
    app.state.observability_configured = True
    if settings.observability.SENTRY_DSN:
        _configure_sentry(settings)
    if settings.observability.OTEL_EXPORTER_OTLP_ENDPOINT:
        _configure_tracing(app, settings)


def _configure_sentry(settings: Settings) -> None:
    """Configure Sentry without identity or request-body collection."""
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.observability.SENTRY_DSN,
            integrations=[FastApiIntegration()],
            environment=settings.APP_ENV,
            release=f"{settings.APP_NAME}@{settings.APP_VERSION}",
            send_default_pii=False,
            traces_sample_rate=0.0,
        )
        logger.info("Sentry error reporting configured")
    except Exception:
        # Observability must not prevent an otherwise healthy API from serving.
        logger.error("Sentry configuration failed", exc_info=True)


def _configure_tracing(app: Any, settings: Settings) -> None:
    """Configure OTLP HTTP trace export with resource attributes for correlation."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                SERVICE_NAME: settings.observability.OTEL_SERVICE_NAME,
                SERVICE_VERSION: settings.APP_VERSION,
                "deployment.environment.name": settings.APP_ENV,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.observability.OTEL_EXPORTER_OTLP_ENDPOINT)
            )
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,metrics")
        app.state.otel_tracer_provider = provider
        logger.info("OpenTelemetry OTLP tracing configured")
    except Exception:
        logger.error("OpenTelemetry configuration failed", exc_info=True)


def shutdown_observability(app: Any) -> None:
    """Flush queued trace spans during orderly FastAPI shutdown."""
    provider = getattr(app.state, "otel_tracer_provider", None)
    if provider is not None:
        try:
            provider.force_flush(timeout_millis=5000)
            provider.shutdown()
        except Exception:
            logger.warning("OpenTelemetry shutdown failed", exc_info=True)


__all__ = ["configure_observability", "shutdown_observability"]
