"""Security evaluation and quarantine decision support."""

from dataclasses import dataclass, field
from typing import Any

# Filename patterns that raise security signals during static analysis.
_SUSPICIOUS_PATTERNS = [
    "crack",
    "keygen",
    "malware",
    "trojan",
    "backdoor",
    "rat.exe",
    "miner",
    "stealer",
    "injector",
    "loader.exe",
    "password-stealer",
]

# Extensions that are never appropriate for a release asset and raise signals.
_DANGEROUS_EXTENSIONS = [".scr", ".vbs", ".js", ".bat", ".cmd", ".ps1", ".hta", ".jar"]


@dataclass
class QuarantineDecision:
    """Decision about whether to quarantine an asset or application."""

    quarantine: bool
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0
    scan_type: str = "static"


def evaluate_security(
    filename: str | None = None,
    checksum_changed: bool = False,
    binary_replacement: bool = False,
    maintainer_anomaly: bool = False,
) -> QuarantineDecision:
    """Evaluate static security signals and return a quarantine decision."""
    reasons: list[str] = []
    confidence = 0.0

    if filename:
        name = filename.lower()
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern in name:
                reasons.append("suspicious_filename")
                confidence = max(confidence, 0.7)
                break
        for ext in _DANGEROUS_EXTENSIONS:
            if name.endswith(ext):
                reasons.append("dangerous_extension")
                confidence = max(confidence, 0.5)
                break

    if checksum_changed:
        reasons.append("checksum_changed")
        confidence = max(confidence, 0.8)

    if binary_replacement:
        reasons.append("unexpected_binary_replacement")
        confidence = max(confidence, 0.85)

    if maintainer_anomaly:
        reasons.append("maintainer_anomaly")
        confidence = max(confidence, 0.6)

    return QuarantineDecision(
        quarantine=bool(reasons),
        reasons=reasons,
        confidence=confidence,
    )


class SecurityScanner:
    """Runs static security checks and produces scan summaries."""

    def scan(self, filename: str | None = None, **signals: Any) -> dict[str, Any]:
        decision = evaluate_security(filename=filename, **signals)
        severity = (
            "high"
            if decision.confidence >= 0.8
            else "medium"
            if decision.confidence >= 0.5
            else "low"
        )
        return {
            "scan_type": "static",
            "scan_status": "flagged" if decision.quarantine else "passed_static_checks",
            "findings": [
                {"reason": reason, "confidence": decision.confidence} for reason in decision.reasons
            ],
            "vulnerabilities": [],
            "severity": severity if decision.quarantine else None,
            "confidence": decision.confidence,
            "quarantine": decision.quarantine,
        }

    async def scan_vulnerabilities(
        self,
        packages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Query OSV.dev for known vulnerabilities in the given packages.

        Packages look like ``{"name": "requests", "ecosystem": "PyPI",
        "version": "2.25.1"}``. Returns a scan summary compatible with
        ``SecurityScan``-shaped records; degrades to ``error`` status when
        the advisory service is unreachable.
        """
        from omnisource.processing.validation.osv import query_batch, worst_severity

        batch = await query_batch(packages)
        if batch["status"] != "ok":
            return {
                "scan_type": "osv",
                "scan_status": "unavailable",
                "vulnerabilities": [],
                "severity": None,
                "error": batch.get("error"),
            }

        vulnerabilities: list[dict[str, Any]] = []
        for pkg, vulns in zip(packages, batch["results"], strict=False):
            for vuln in vulns:
                detail = await get_vuln_detail(vuln["id"]) if vuln.get("id") else None
                vulnerabilities.append(
                    {
                        "id": vuln.get("id"),
                        "package": pkg.get("name"),
                        "ecosystem": pkg.get("ecosystem"),
                        "version": pkg.get("version"),
                        "severity": worst_severity(detail) if detail else None,
                    }
                )

        high_risk = [v for v in vulnerabilities if v.get("severity") in {"high", "critical"}]
        return {
            "scan_type": "osv",
            "scan_status": "flagged" if vulnerabilities else "passed_vulnerability_scan",
            "vulnerabilities": vulnerabilities,
            "severity": "high" if high_risk else ("medium" if vulnerabilities else None),
            "quarantine": bool(high_risk),
        }


async def get_vuln_detail(vuln_id: str) -> dict[str, Any] | None:
    """Fetch (and cache in-process) an OSV vulnerability detail record."""
    cached = _VULN_CACHE.get(vuln_id)
    if cached is not None:
        return cached
    from omnisource.processing.validation.osv import get_vuln

    detail = await get_vuln(vuln_id)
    if detail is not None:
        _VULN_CACHE[vuln_id] = detail
    return detail


_VULN_CACHE: dict[str, dict[str, Any]] = {}
