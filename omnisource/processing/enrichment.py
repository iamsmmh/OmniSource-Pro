"""Deterministic metadata enrichment for discovered software projects.

This module deliberately keeps enrichment explainable and offline. Optional AI
providers can augment the persisted result later, but category, language,
package, media, and project/developer profiles do not depend on a model call.
"""

from collections.abc import Iterable
from typing import Any

from omnisource.processing.categorization import categorize
from omnisource.processing.metadata_extractor import extract_urls
from omnisource.processing.package_detector import detect_package_ecosystems

_MEDIA_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".avif")


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _safe_http_urls(values: Iterable[object], limit: int = 20) -> list[str]:
    """Return unique HTTP(S) URLs only; never turn arbitrary text into a link."""
    urls: list[str] = []
    for value in values:
        url = str(value).strip()
        if not url.lower().startswith(("https://", "http://")) or url in urls:
            continue
        urls.append(url[:500])
        if len(urls) >= limit:
            break
    return urls


def _media_urls(
    metadata: dict[str, Any], readme: str | None
) -> tuple[str | None, str | None, list[str]]:
    icon = metadata.get("icon") or metadata.get("icon_url")
    banner = metadata.get("banner") or metadata.get("banner_url")
    screenshots = _as_strings(metadata.get("screenshots"))
    # Some AppStream sources include image URLs only in the long description/readme.
    readme_images = [
        url
        for url in extract_urls(readme)
        if url.lower().split("?", 1)[0].endswith(_MEDIA_SUFFIXES)
    ]
    screenshots = _safe_http_urls([*screenshots, *readme_images])
    safe_icon = _safe_http_urls([icon], 1)
    safe_banner = _safe_http_urls([banner], 1)
    return (
        safe_icon[0] if safe_icon else None,
        safe_banner[0] if safe_banner else None,
        screenshots,
    )


def _language_profile(languages: Any, fallback: str | None) -> tuple[dict[str, int], str | None]:
    if isinstance(languages, dict):
        cleaned = {str(name): int(value or 0) for name, value in languages.items()}
        primary = max(cleaned, key=lambda name: cleaned[name]) if cleaned else fallback
        return cleaned, primary
    if isinstance(languages, list):
        cleaned = {str(name): 0 for name in languages}
        return cleaned, next(iter(cleaned), fallback)
    return {}, fallback


class MetadataEnricher:
    """Builds a normalized project profile suitable for API and search indexing."""

    def enrich(
        self,
        repository: Any,
        metadata: dict[str, Any] | None,
        release_notes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        readme = metadata.get("readme") if isinstance(metadata.get("readme"), str) else None
        changelog = (
            metadata.get("changelog") if isinstance(metadata.get("changelog"), str) else None
        )
        topics = _as_strings(metadata.get("topics")) or _as_strings(
            getattr(repository, "topics", [])
        )
        languages, primary_language = _language_profile(
            metadata.get("languages"), getattr(repository, "language", None)
        )
        filenames = _as_strings(metadata.get("files"))
        packages = detect_package_ecosystems(filenames, readme)
        category = categorize(topics=topics, description=getattr(repository, "description", None))
        icon_url, banner_url, screenshot_urls = _media_urls(metadata, readme)
        contributors = metadata.get("contributors") or []
        contributor_count = (
            len(contributors)
            if isinstance(contributors, list)
            else int(metadata.get("contributors_count") or 0)
        )
        owner = (getattr(repository, "full_name", "") or "").split("/", 1)[0] or None
        return {
            "readme": readme,
            "changelog": changelog,
            "release_notes": release_notes or [],
            "languages": languages,
            "package_ecosystems": packages,
            "project_tags": sorted({topic.lower() for topic in topics})[:50],
            "icon_url": icon_url,
            "banner_url": banner_url,
            "screenshot_urls": screenshot_urls,
            "topics": topics[:50],
            "contributors_count": contributor_count,
            "enrichment": {
                "project_profile": {
                    "name": getattr(repository, "name", ""),
                    "primary_language": primary_language,
                    "categories": category,
                    "package_ecosystems": packages,
                    "has_readme": bool(readme),
                    "has_changelog": bool(changelog),
                    "has_release_notes": bool(release_notes),
                },
                "developer_profile": {
                    "source_owner": owner,
                    "contributor_count": contributor_count,
                },
                "enrichment_version": "v1",
            },
        }


__all__ = ["MetadataEnricher"]
