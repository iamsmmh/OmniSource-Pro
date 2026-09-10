"""Asset validation orchestrator."""

from dataclasses import dataclass, field
from typing import Any

from omnisource.processing.validation.checksum import is_valid_hex_digest
from omnisource.processing.validation.url_validator import validate_url


@dataclass
class AssetValidationOutcome:
    """Outcome of validating a single asset."""

    status: str  # valid | invalid | review_required | unknown
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    http_status: int | None = None
    content_length: int | None = None
    sha256: str | None = None
    sha512: str | None = None
    mime_type: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


def validate_asset(asset: dict[str, Any]) -> AssetValidationOutcome:
    """Validate an asset described as a dictionary of fields.

    Expected keys include ``download_url``, ``filename``, ``size_bytes``,
    ``sha256``, ``sha512``, ``package_type``, ``detected_platform``.
    """
    errors: list[str] = []
    warnings: list[str] = []

    url = (asset.get("download_url") or asset.get("browser_download_url") or "").strip()
    filename = asset.get("filename") or asset.get("name") or ""

    # URL validation
    url_result = validate_url(url)
    if not url_result.valid:
        errors.append(f"Invalid download URL: {url_result.reason}")

    # Filename validation
    if not filename:
        errors.append("Missing filename")
    elif any(c in filename for c in ("\n", "\r", "\\")):
        errors.append("Suspicious filename characters")

    # Package type validation
    package_type = asset.get("package_type") or asset.get("file_type")
    if package_type in (None, "", "binary", "source"):
        warnings.append(f"Undetermined package type for {filename}")

    # Checksum sanity checks
    sha256 = asset.get("sha256")
    sha512 = asset.get("sha512")
    if sha256 and not is_valid_hex_digest(sha256, "sha256"):
        errors.append("Invalid SHA-256 checksum format")
    if sha512 and not is_valid_hex_digest(sha512, "sha512"):
        errors.append("Invalid SHA-512 checksum format")

    # Size sanity checks
    size = asset.get("size_bytes")
    if size is not None:
        try:
            size_int = int(size)
            if size_int < 0:
                errors.append("Negative size")
            elif size_int == 0:
                warnings.append("Zero-byte asset")
        except (TypeError, ValueError):
            errors.append("Invalid size value")

    if errors:
        status = "invalid"
    elif warnings:
        status = "review_required" if package_type in (None, "", "binary", "source") else "valid"
    else:
        status = "valid"

    return AssetValidationOutcome(
        status=status,
        errors=errors,
        warnings=warnings,
        http_status=asset.get("http_status"),
        content_length=size if isinstance(size, int) else None,
        sha256=sha256,
        sha512=sha512,
        mime_type=asset.get("mime_type"),
    )


class AssetValidator:
    """Validates assets and records outcomes."""

    def validate(self, asset: dict[str, Any]) -> AssetValidationOutcome:
        return validate_asset(asset)
