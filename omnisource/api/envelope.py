"""Standard API response envelope.

All ``/api/v1`` data endpoints answer with:

    {
        "success": true,
        "data": <payload>,
        "meta": <request metadata: generated_at, source, freshness, ...>,
        "pagination": <list endpoints only: page, per_page, total, total_pages>
    }

Exceptions: signed ``/feeds/*`` endpoints keep their signed-feed contract,
``/api/v1/app/{id}`` keeps the legacy OmniStore contract, and error
responses use FastAPI's ``{"detail": ...}`` shape (handled by the global
exception handler).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

DEFAULT_TTL_SECONDS = 60


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def success(
    data: Any,
    meta: dict[str, Any] | None = None,
    pagination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a success envelope."""
    body: dict[str, Any] = {
        "success": True,
        "data": data,
        "meta": {
            "generated_at": now_iso(),
            "service": "omnisource",
            **(meta or {}),
        },
    }
    if pagination is not None:
        body["pagination"] = pagination
    return body


def failure(error: str, status_hint: int = 500, **meta: Any) -> tuple[dict[str, Any], int]:
    """Build an error envelope (used where non-2xx bodies are still JSON)."""
    return (
        {
            "success": False,
            "error": error,
            "meta": {
                "generated_at": now_iso(),
                "service": "omnisource",
                **meta,
            },
        },
        status_hint,
    )


def pagination_envelope(page: int, per_page: int, total: int) -> dict[str, Any]:
    """Standard pagination block for list endpoints."""
    per_page = max(1, per_page)
    total_pages = max(1, -(-int(total) // per_page))  # ceil division
    return {
        "page": page,
        "per_page": per_page,
        "total": int(total),
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


__all__ = ["DEFAULT_TTL_SECONDS", "failure", "now_iso", "pagination_envelope", "success"]
