"""Feed normalization: canonicalize validated items before persistence.

Normalization is deterministic: the same upstream payload always produces the
same canonical form, and the resulting ``content_hash`` is a stable
fingerprint used for change detection (incremental sync) and duplicate
detection.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from app.services.feed_sync.schemas import FeedItem
from omnisource.config.logging import get_logger

logger = get_logger(__name__)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_SPACES = re.compile(r"\s+")


def canonical_slug(value: str, max_length: int = 80) -> str:
    """Lowercase, ASCII-fold, dash-joined slug (max 80 chars, no leading dash)."""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", folded.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = "app"
    return slug[:max_length].rstrip("-") or "app"


def canonical_bundle_id(value: str | None) -> str | None:
    """Lowercase and trim a bundle id; return None when unusable."""
    if not value:
        return None
    bundle = value.strip().lower()
    if not bundle or len(bundle) > 255 or " " in bundle:
        return None
    return bundle


def canonical_url(value: str | None) -> str | None:
    """Trim trailing whitespace/slash from a URL, lowercasing scheme+host."""
    if not value:
        return None
    url = value.strip()
    if not url:
        return None
    match = re.match(r"^(https?)://([^/]+)(.*)$", url)
    if match:
        return f"{match.group(1).lower()}://{match.group(2).lower()}{match.group(3).rstrip('/')}"
    return url


def canonical_checksum(value: str | None) -> str | None:
    if not value:
        return None
    digest = value.strip().lower()
    return digest if re.fullmatch(r"[0-9a-f]{64}", digest) else None


def canonical_version(value: str) -> str:
    return value.strip().lstrip("vV").strip()


def canonical_tags(tags: list[str], max_tags: int = 20) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        cleaned = re.sub(r"\s+", "-", str(tag).strip().lower()).strip("-")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned[:40])
        if len(result) >= max_tags:
            break
    return result


class FeedNormalizer:
    """Produces canonical feed items and their content fingerprints."""

    def normalize(self, item: FeedItem) -> FeedItem:
        """Return a canonicalized copy of the item (input is not mutated)."""
        data = item.model_dump(mode="json")

        data["slug"] = canonical_slug(data.get("slug") or data.get("name") or item.repository)
        data["name"] = _SPACES.sub(" ", str(data.get("name") or "")).strip()[:200]
        data["bundle_id"] = canonical_bundle_id(data.get("bundle_id"))
        data["homepage"] = canonical_url(data.get("homepage"))
        data["documentation_url"] = canonical_url(data.get("documentation_url"))
        data["tags"] = canonical_tags(data.get("tags") or [])
        data["platforms"] = sorted({p for p in (data.get("platforms") or []) if p})

        if data.get("license"):
            data["license"] = (
                str(data["license"]).upper().replace("LICENSE/", "").replace(" ", "")[:64]
            )

        releases = data.get("releases") or []
        for release in releases:
            release["version"] = canonical_version(release.get("version") or "")
            release["tag"] = (release.get("tag") or "").strip() or None
            if release["tag"] is None:
                release.pop("tag", None)
            if not release.get("notes"):
                release.pop("notes", None)
            for asset in release.get("assets") or []:
                asset["sha256"] = canonical_checksum(asset.get("sha256"))
                if not asset["sha256"]:
                    asset["sha256"] = None
                asset["filename"] = str(asset.get("filename") or "").strip()[:255]

        # Newest release first; the list is capped upstream by the schema.
        releases.sort(key=lambda r: r.get("published_at") or "", reverse=True)
        data["releases"] = releases

        normalized = FeedItem(**data)
        normalized.content_hash = hashlib.sha256(
            json.dumps(normalized.canonical(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return normalized

    @staticmethod
    def content_hash_of(item: FeedItem) -> str:
        """Stable fingerprint of an already-normalized item."""
        return hashlib.sha256(
            json.dumps(item.canonical(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


__all__ = [
    "FeedNormalizer",
    "canonical_bundle_id",
    "canonical_checksum",
    "canonical_slug",
    "canonical_tags",
    "canonical_url",
    "canonical_version",
]
