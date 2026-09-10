"""URL validation utilities."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Hostnames that must never be contacted during validation (SSRF guard).
_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",  # cloud metadata
    "metadata.google.internal",
}

_ALLOWED_SCHEMES = {"http", "https"}


@dataclass
class URLValidationResult:
    """Result of a URL validation."""

    valid: bool
    reason: str | None = None
    url: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.valid


def _is_private_host(hostname: str) -> bool:
    """Return True if the hostname is a private/loopback address."""
    if hostname in _BLOCKED_HOSTS:
        return True
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        return True
    # Match private IPv4 ranges
    if re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", hostname):
        return True
    return False


def validate_url(url: str, allow_private: bool = False) -> URLValidationResult:
    """Validate a URL string for structure and safety."""
    if not url or not isinstance(url, str):
        return URLValidationResult(valid=False, reason="empty", errors=["URL is empty"])

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return URLValidationResult(
            valid=False,
            url=url,
            reason="scheme",
            errors=[f"Unsupported scheme: {parsed.scheme or '(none)'}"],
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return URLValidationResult(valid=False, url=url, reason="host", errors=["Missing hostname"])

    if not allow_private and _is_private_host(hostname):
        return URLValidationResult(
            valid=False,
            url=url,
            reason="private_host",
            errors=[f"Private/loopback host not allowed: {hostname}"],
        )

    return URLValidationResult(valid=True, url=url)


def is_valid_url(url: str, allow_private: bool = False) -> bool:
    """Return True if the URL is structurally valid and safe."""
    return validate_url(url, allow_private=allow_private).valid
