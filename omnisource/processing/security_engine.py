"""Composable artifact-security integrations.

The scanner never downloads arbitrary release binaries by default. Callers pass
already-controlled bytes for YARA scanning and a SHA-256 to VirusTotal for a
hash-reputation lookup. This preserves SSRF and bandwidth boundaries while
allowing a sandboxed worker to implement its own artifact acquisition policy.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.processing.validation.security import SecurityScanner

logger = get_logger(__name__)


@dataclass(frozen=True)
class ScanEvidence:
    """Normalized scanner evidence persisted with an application security scan."""

    scan_type: str
    status: str
    severity: str | None
    findings: list[dict[str, Any]]
    confidence: float = 0.0


class VirusTotalClient:
    """Optional hash-reputation lookup using the VirusTotal v3 file endpoint."""

    def __init__(self, api_key: str | None = None, api_url: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.security.VIRUSTOTAL_API_KEY
        self.api_url = (api_url or settings.security.VIRUSTOTAL_API_URL).rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def lookup_sha256(self, sha256: str | None) -> ScanEvidence:
        if not sha256:
            return ScanEvidence("virustotal", "skipped", None, [{"reason": "missing_sha256"}])
        if not self.available:
            return ScanEvidence(
                "virustotal", "not_configured", None, [{"reason": "api_key_not_configured"}]
            )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self.api_url}/files/{sha256}", headers={"x-apikey": self.api_key or ""}
                )
            if response.status_code == 404:
                return ScanEvidence("virustotal", "unknown", None, [{"reason": "hash_not_known"}])
            response.raise_for_status()
            attributes = response.json().get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})
            malicious = int(stats.get("malicious") or 0)
            suspicious = int(stats.get("suspicious") or 0)
            severity = "high" if malicious else "medium" if suspicious else None
            status = "flagged" if malicious or suspicious else "passed_reputation"
            return ScanEvidence(
                "virustotal",
                status,
                severity,
                [
                    {
                        "malicious": malicious,
                        "suspicious": suspicious,
                        "undetected": int(stats.get("undetected") or 0),
                    }
                ],
                0.95 if malicious else 0.8,
            )
        except httpx.HTTPError as exc:
            logger.warning("VirusTotal lookup failed: %s", exc)
            return ScanEvidence("virustotal", "error", None, [{"reason": "provider_error"}])


class YaraScanner:
    """Optional YARA scanner for bytes acquired by a controlled worker."""

    def __init__(self, rules_dir: str | None = None) -> None:
        configured = rules_dir if rules_dir is not None else get_settings().security.YARA_RULES_DIR
        self.rules_dir = Path(configured) if configured else None

    @property
    def available(self) -> bool:
        return self.rules_dir is not None and self.rules_dir.is_dir()

    def scan_bytes(self, payload: bytes) -> ScanEvidence:
        if not self.available:
            return ScanEvidence(
                "yara", "not_configured", None, [{"reason": "rules_not_configured"}]
            )
        try:
            import yara
        except ImportError:
            return ScanEvidence(
                "yara", "unavailable", None, [{"reason": "yara_python_not_installed"}]
            )
        rules_dir = self.rules_dir
        if rules_dir is None:  # defensive narrowing for type checkers
            return ScanEvidence(
                "yara", "not_configured", None, [{"reason": "rules_not_configured"}]
            )
        rule_files = {path.stem: str(path) for path in rules_dir.glob("*.yar")} | {
            path.stem: str(path) for path in rules_dir.glob("*.yara")
        }
        if not rule_files:
            return ScanEvidence("yara", "not_configured", None, [{"reason": "no_rules_found"}])
        try:
            rules = yara.compile(filepaths=rule_files)
            matches = rules.match(data=payload)
        except Exception as exc:
            logger.warning("YARA scan failed: %s", exc)
            return ScanEvidence("yara", "error", None, [{"reason": "scan_error"}])
        findings = [
            {"rule": match.rule, "namespace": match.namespace, "tags": list(match.tags)}
            for match in matches
        ]
        return ScanEvidence(
            "yara",
            "flagged" if findings else "passed_yara",
            "high" if findings else None,
            findings,
            0.9 if findings else 0.8,
        )


def levenshtein(left: str, right: str) -> int:
    """Compute edit distance without an optional dependency."""
    if len(left) < len(right):
        left, right = right, left
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, 1):
        current = [index]
        for other_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def detect_typosquat(candidate: str, protected_names: list[str]) -> dict[str, Any]:
    """Flag names one edit away from a protected catalogue name."""
    normalized = candidate.lower().replace("-", "").replace("_", "")
    for protected in protected_names:
        protected_normalized = protected.lower().replace("-", "").replace("_", "")
        if (
            len(protected_normalized) >= 4
            and normalized != protected_normalized
            and levenshtein(normalized, protected_normalized) <= 1
        ):
            return {"suspicious": True, "matched_name": protected, "reason": "near_match"}
    return {"suspicious": False, "matched_name": None, "reason": None}


class SecurityOrchestrator:
    """Combines static, YARA, and reputation evidence for a release artifact."""

    def __init__(
        self, virustotal: VirusTotalClient | None = None, yara: YaraScanner | None = None
    ) -> None:
        self.virustotal = virustotal or VirusTotalClient()
        self.yara = yara or YaraScanner()
        self.static = SecurityScanner()

    async def scan_artifact(
        self,
        filename: str,
        sha256: str | None,
        payload: bytes | None = None,
        protected_names: list[str] | None = None,
    ) -> list[ScanEvidence]:
        """Generate available evidence; unavailable integrations are explicit, not silent."""
        static = self.static.scan(filename=filename)
        results = [
            ScanEvidence(
                "static",
                str(static["scan_status"]),
                static.get("severity"),
                list(static.get("findings") or []),
                float(static.get("confidence") or 0),
            ),
            await self.virustotal.lookup_sha256(sha256),
        ]
        if payload is not None:
            results.append(self.yara.scan_bytes(payload))
        if protected_names:
            typo = detect_typosquat(filename.rsplit(".", 1)[0], protected_names)
            results.append(
                ScanEvidence(
                    "typosquatting",
                    "flagged" if typo["suspicious"] else "passed",
                    "medium" if typo["suspicious"] else None,
                    [typo],
                    0.8 if typo["suspicious"] else 0.7,
                )
            )
        return results


__all__ = [
    "ScanEvidence",
    "SecurityOrchestrator",
    "VirusTotalClient",
    "YaraScanner",
    "detect_typosquat",
    "levenshtein",
]
