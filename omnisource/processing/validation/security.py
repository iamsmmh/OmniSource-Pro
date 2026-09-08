"""Security evaluation and quarantine decision support."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    reasons: List[str] = field(default_factory=list)
    confidence: float = 0.0
    scan_type: str = "static"


def evaluate_security(
    filename: Optional[str] = None,
    checksum_changed: bool = False,
    binary_replacement: bool = False,
    maintainer_anomaly: bool = False,
) -> QuarantineDecision:
    """Evaluate static security signals and return a quarantine decision."""
    reasons: List[str] = []
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

    def scan(self, filename: Optional[str] = None, **signals: Any) -> Dict[str, Any]:
        decision = evaluate_security(filename=filename, **signals)
        severity = "high" if decision.confidence >= 0.8 else "medium" if decision.confidence >= 0.5 else "low"
        return {
            "scan_type": "static",
            "scan_status": "flagged" if decision.quarantine else "passed_static_checks",
            "findings": [
                {"reason": reason, "confidence": decision.confidence}
                for reason in decision.reasons
            ],
            "vulnerabilities": [],
            "severity": severity if decision.quarantine else None,
            "confidence": decision.confidence,
            "quarantine": decision.quarantine,
        }
