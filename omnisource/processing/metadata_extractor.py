"""Metadata extraction from raw repository data."""

import re
from typing import Any

from omnisource.processing.license_engine import normalize_license

# Patterns for common links found in README bodies.
_URL_PATTERN = re.compile(r"https?://[^\s)\]]+")


def extract_description(data: dict[str, Any]) -> str | None:
    """Extract a clean description from repository data."""
    description = data.get("description")
    if isinstance(description, str):
        description = " ".join(description.split())
        return description or None
    return None


def extract_topics(data: dict[str, Any]) -> list[str]:
    """Extract topics from repository data (handles list and dict forms)."""
    topics = data.get("topics", [])
    if isinstance(topics, dict):
        topics = topics.get("names", [])
    if not isinstance(topics, list):
        return []
    return [str(t).strip().lower() for t in topics if t][:50]


def extract_license_spdx(data: dict[str, Any]) -> str | None:
    """Extract a normalized SPDX license identifier from repository data."""
    license_data = data.get("license")
    if isinstance(license_data, dict):
        spdx = license_data.get("spdx_id") or license_data.get("key")
        return normalize_license(spdx)
    if isinstance(license_data, str):
        return normalize_license(license_data)
    return None


def extract_homepage(data: dict[str, Any]) -> str | None:
    """Extract homepage URL, preferring a real homepage over the repo URL."""
    homepage = data.get("homepage")
    if isinstance(homepage, str) and homepage.strip():
        return homepage.strip()
    return None


def extract_documentation_url(data: dict[str, Any]) -> str | None:
    """Attempt to derive a documentation URL from the repository data."""
    docs = data.get("documentation_url")
    if docs:
        return docs
    homepage = extract_homepage(data)
    if homepage and ("docs" in homepage or "readthedocs" in homepage):
        return homepage
    return None


def extract_urls(text: str | None) -> list[str]:
    """Extract URLs from a text blob."""
    if not text:
        return []
    return list(dict.fromkeys(_URL_PATTERN.findall(text)))


def extract_languages(data: dict[str, Any]) -> list[str]:
    """Extract language names from repository data."""
    languages = data.get("languages", {})
    if isinstance(languages, dict):
        return sorted(languages.keys(), key=lambda k: -(languages[k] or 0))
    if isinstance(languages, list):
        return [str(lang) for lang in languages]
    return []


class MetadataExtractor:
    """Extracts structured metadata from raw source data."""

    def extract(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract all supported metadata fields into a flat dictionary."""
        return {
            "description": extract_description(data),
            "topics": extract_topics(data),
            "license_spdx": extract_license_spdx(data),
            "homepage": extract_homepage(data),
            "documentation_url": extract_documentation_url(data),
            "languages": extract_languages(data),
            "stars": data.get("stargazers_count") or data.get("stars") or 0,
            "forks": data.get("forks_count") or data.get("forks") or 0,
            "open_issues": data.get("open_issues_count") or data.get("open_issues") or 0,
            "default_branch": data.get("default_branch"),
            "has_wiki": bool(data.get("has_wiki")),
            "has_issues": bool(data.get("has_issues")),
            "has_discussions": bool(data.get("has_discussions")),
            "has_projects": bool(data.get("has_projects")),
            "has_downloads": bool(data.get("has_downloads")),
            "contributors_count": len(data.get("contributors") or []),
        }
