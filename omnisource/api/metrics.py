"""Prometheus metrics for OmniSource.

Exposes a ``/metrics`` endpoint plus middleware-instrumented HTTP metrics and
helpers used by the automation worker to report job outcomes. Metric names
follow Prometheus conventions; all labels are low-cardinality.
"""

import time
from typing import Any

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

# --- Feed sync metrics ---------------------------------------------------------------

SYNC_RUNS = Counter(
    "omnisource_feed_sync_runs_total",
    "Feed sync runs by source and outcome.",
    ["source", "status"],
)
SYNC_REPOSITORIES = Counter(
    "omnisource_feed_sync_repositories_total",
    "Repositories processed per feed sync run, by outcome.",
    ["outcome"],
)

# --- Webhook metrics -------------------------------------------------------------------

WEBHOOK_DELIVERIES = Counter(
    "omnisource_webhook_deliveries_total",
    "Outbound webhook deliveries by event and outcome.",
    ["event", "status"],
)
WEBHOOK_DELIVERY_LATENCY = Histogram(
    "omnisource_webhook_delivery_latency_seconds",
    "Latency of a single webhook delivery attempt.",
    ["event"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# --- Database metrics ------------------------------------------------------------------

DB_QUERY_DURATION = Histogram(
    "omnisource_db_query_duration_seconds",
    "Database query latency in seconds (SQLAlchemy cursor executions).",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# --- Search metrics ----------------------------------------------------------------------

SEARCH_DURATION = Histogram(
    "omnisource_search_duration_seconds",
    "Search request latency in seconds.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
SEARCH_RESULTS = Histogram(
    "omnisource_search_results",
    "Number of results returned per search.",
    buckets=(0, 1, 5, 10, 25, 50, 100, 250, 500),
)

# --- Cache metrics -----------------------------------------------------------------------

CACHE_HITS = Counter("omnisource_cache_hits_total", "Response cache hits.", ["tier"])
CACHE_MISSES = Counter("omnisource_cache_misses_total", "Response cache misses.", ["tier"])

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


def setup_db_query_metrics(engine: Any) -> None:
    """Attach SQLAlchemy event hooks that observe DB query latency.

    Idempotent: safe to call from both the API and worker processes.
    """
    from sqlalchemy import event

    if getattr(engine, "_omnisource_metrics_attached", False):
        return

    def _before(_conn, _cursor, _statement, _params, _context, _executemany):
        _conn.info["omnisource_query_start"] = time.perf_counter()

    def _after(_conn, _cursor, _statement, _params, _context, _executemany):
        started = _conn.info.pop("omnisource_query_start", None)
        if started is not None:
            DB_QUERY_DURATION.observe(time.perf_counter() - started)

    sync_engine = getattr(engine, "sync_engine", engine)
    event.listen(sync_engine, "before_cursor_execute", _before)
    event.listen(sync_engine, "after_cursor_execute", _after)
    engine._omnisource_metrics_attached = True


__all__ = [
    "CACHE_HITS",
    "CACHE_MISSES",
    "CONTENT_TYPE_LATEST",
    "DB_QUERY_DURATION",
    "HTTP_REQUESTS",
    "JOBS_RUNNING",
    "SEARCH_DURATION",
    "SEARCH_RESULTS",
    "SYNC_REPOSITORIES",
    "SYNC_RUNS",
    "WEBHOOK_DELIVERIES",
    "WEBHOOK_DELIVERY_LATENCY",
    "MetricsMiddleware",
    "record_connector_request",
    "record_job",
    "render_metrics",
    "setup_db_query_metrics",
]
