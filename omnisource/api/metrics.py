"""Prometheus metrics for OmniSource.

Exposes a ``/metrics`` endpoint plus middleware-instrumented HTTP metrics and
helpers used by the automation worker to report job outcomes. Metric names
follow Prometheus conventions; all labels are low-cardinality.
"""

import time

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# --- HTTP metrics ------------------------------------------------------------------

HTTP_REQUESTS = Counter(
    "omnisource_http_requests_total",
    "Total HTTP requests by method, endpoint template, and status code.",
    ["method", "endpoint", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "omnisource_http_request_duration_seconds",
    "HTTP request latency in seconds by method and endpoint template.",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# --- Job metrics ---------------------------------------------------------------------

JOB_TOTAL = Counter(
    "omnisource_jobs_total",
    "Automation jobs by type and outcome.",
    ["type", "status"],
)
JOB_DURATION = Histogram(
    "omnisource_job_duration_seconds",
    "Automation job runtime in seconds by type.",
    ["type"],
    buckets=(0.1, 0.5, 1, 5, 15, 30, 60, 300, 900, 3600),
)
JOBS_RUNNING = Gauge(
    "omnisource_jobs_running",
    "Automation jobs currently executing.",
)

# --- Connector metrics -----------------------------------------------------------------

CONNECTOR_REQUESTS = Counter(
    "omnisource_connector_requests_total",
    "Outbound connector requests by source and outcome.",
    ["source", "status"],
)

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


def render_metrics() -> bytes:
    """Render all metrics in the Prometheus text exposition format."""
    return generate_latest()


def _endpoint_template(request: Request) -> str:
    """Best-effort low-cardinality endpoint template for labels."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if template:
        return str(template)
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/feeds/"):
        return path  # these are structured APIs; per-path is acceptable at first
    return "other"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records request count and latency for every HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        endpoint = _endpoint_template(request)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status="500").inc()
            HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
                time.perf_counter() - started
            )
            raise
        status_code = str(response.status_code)
        HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status=status_code).inc()
        HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
            time.perf_counter() - started
        )
        return response


def record_job(type_name: str, status_name: str, duration_seconds: float | None = None) -> None:
    """Record a job outcome; call from the automation worker."""
    JOB_TOTAL.labels(type=type_name, status=status_name).inc()
    if duration_seconds is not None:
        JOB_DURATION.labels(type=type_name).observe(duration_seconds)


def record_connector_request(source: str, status_name: str) -> None:
    """Record an outbound connector request outcome."""
    CONNECTOR_REQUESTS.labels(source=source, status=status_name).inc()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "HTTP_REQUESTS",
    "JOBS_RUNNING",
    "MetricsMiddleware",
    "record_connector_request",
    "record_job",
    "render_metrics",
]
