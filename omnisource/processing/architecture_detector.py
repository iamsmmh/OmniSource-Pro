"""CPU architecture detection for software assets."""

from typing import Optional

from omnisource.core.models.platform import (
    ARCH_ALIASES,
    normalize_architecture,
)
from omnisource.core.models.release import detect_architecture


def detect_architecture_from_asset(filename: str) -> Optional[str]:
    """Detect and normalize architecture from an asset filename."""
    arch = detect_architecture(filename)
    if arch is None:
        return None
    return normalize_architecture(arch)


__all__ = [
    "ARCH_ALIASES",
    "normalize_architecture",
    "detect_architecture",
    "detect_architecture_from_asset",
]
