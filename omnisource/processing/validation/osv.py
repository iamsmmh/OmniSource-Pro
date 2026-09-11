"""OSV.dev vulnerability lookups for dependency and package scanning.

OSV (https://osv.dev) aggregates advisories from GitHub Advisory Database,
PyPI, npm, and other ecosystems. The batch endpoint allows checking many
packages in one round trip:

``POST https://api.osv.dev/v1/querybatch``
``{"queries": [{"package": {"name": "requests", "ecosystem": "PyPI"}}]}``

Failure modes degrade gracefully: network errors return an explicit
``error`` scan status rather than raising, so the validation pipeline never
blocks on the advisory service being down.
"""

from typing import Any

import httpx

from omnisource.config.logging import get_logger

logger = get_logger(__name__)

OSV_API_BASE = "https://api.osv.dev/v1"
_TIMEOUT_SECONDS = 15.0

# Map OmniSource platform/package ecosystems to OSV ecosystem names.
OSV_ECOSYSTEMS = {
    "pypi": "PyPI",
    "npm": "npm",
    "go": "Go",
    "crates.io": "crates.io",
    "rubygems": "RubyGems",
    "maven": "Maven",
    "nuget": "NuGet",
    "packagist": "Packagist",
    "hex": "Hex",
    "android": "Android",
    "linux": "Linux",
}


async def query_batch(
    packages: list[dict[str, str]],
    api_base: str = OSV_API_BASE,
    timeout: float = _TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Look up vulnerabilities for a batch of packages.

    Args:
        packages: List of ``{"name": ..., "ecosystem": ..., "version": optional}``.
        api_base: OSV API base URL (overridable for tests).
        timeout: Request timeout in seconds.

    Returns:
        ``{"status": "ok", "results": [[vuln_ids], ...]}`` aligned with the
        input order, or ``{"status": "error", "error": ...}`` on failure.
    """
    if not packages:
        return {"status": "ok", "results": []}

    queries = []
    for pkg in packages:
        entry: dict[str, Any] = {
            "package": {
                "name": pkg.get("name", ""),
                "ecosystem": OSV_ECOSYSTEMS.get(
                    pkg.get("ecosystem", "").lower(), pkg.get("ecosystem", "")
                ),
            }
        }
        if pkg.get("version"):
            entry["version"] = pkg["version"]
        queries.append(entry)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{api_base}/querybatch", json={"queries": queries})
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("OSV querybatch failed", exc_info=True)
        # This result can become persisted scan evidence, so keep the public
        # state diagnostic but never retain an upstream response or URL.
        return {"status": "error", "error": "advisory_service_unavailable"}

    results: list[list[dict[str, str]]] = []
    for entry in data.get("results", []):
        vulns = entry.get("vulns") or []
        results.append(
            [
                {"id": v.get("id", ""), "modified": v.get("modified", "")}
                for v in vulns
                if isinstance(v, dict)
            ]
        )
    return {"status": "ok", "results": results}


async def get_vuln(
    vuln_id: str,
    api_base: str = OSV_API_BASE,
    timeout: float = _TIMEOUT_SECONDS,
) -> dict[str, Any] | None:
    """Fetch vulnerability details (severity, summary, affected ranges)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{api_base}/vulns/{vuln_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("OSV vuln fetch failed for %s: %s", vuln_id, exc)
        return None


def worst_severity(vuln: dict[str, Any]) -> str | None:
    """Extract the highest severity from an OSV vulnerability detail object."""
    candidates: list[str] = []
    for item in vuln.get("severity", []) or []:
        score = item.get("score")
        if isinstance(score, str) and score.upper().startswith("CVSS:"):
            # crude CVSS v3 banding from the vector's base score is unavailable
            # without the full vector; classify by presence.
            candidates.append("high")
    severity_from_db = vuln.get("database_specific", {}).get("severity")
    if severity_from_db:
        candidates.append(str(severity_from_db).lower())
    order = {"low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}
    if not candidates:
        return None
    return max(candidates, key=lambda c: order.get(c, 0))


__all__ = ["OSV_ECOSYSTEMS", "get_vuln", "query_batch", "worst_severity"]
