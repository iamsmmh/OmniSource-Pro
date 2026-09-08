"""Platform detection for software assets."""

from typing import Optional

from omnisource.core.models.release import (
    detect_package_type,
    detect_platform,
)


def detect_platform_from_asset(
    filename: str,
    mime_type: Optional[str] = None,
) -> Optional[str]:
    """Detect platform from an asset filename (optionally using MIME type)."""
    platform = detect_platform(filename)
    if platform:
        return platform

    if mime_type:
        mime_lower = mime_type.lower()
        if "android" in mime_lower or mime_lower == "application/vnd.android.package-archive":
            return "android"
        if "msi" in mime_lower or "msdownload" in mime_lower:
            return "windows"
        if "apple-diskimage" in mime_lower or "x-newton-compatible-pkg" in mime_lower:
            return "macos"
        if "debian" in mime_lower or "x-rpm" in mime_lower or "x-flatpak" in mime_lower:
            return "linux"

    return None


__all__ = ["detect_platform", "detect_package_type", "detect_platform_from_asset"]
