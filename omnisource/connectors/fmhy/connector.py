"""FMHY (freemediaheckyeah) connector for OmniSource.

Indexes the Android / iOS app listing at https://fmhy.net/mobile across both
platforms (the "cross platform" catalogue: Android APKs + iOS apps).

fmhy.net is a VitePress static site, so the connector fetches the rendered
mobile page and walks it top to bottom, tracking the **platform zone** from
the section headings. The page is organized per platform::

    #  Android / iOS                    (document title)
    ## Android APKs                     (platform sections -> set the zone)
    ### Modded APKs                     (subsections -> inherit the zone)
    ...
    ## Emulators                        (no platform in name -> inherit)
    ...
    ## iOS Tools
    ## iOS iPAs
    ...

Each list entry of the page is shaped like::

    * 🌐 **[CyPwn](https://ipa.cypwn.xyz/)** - Tweaked App Library / [AltStore](...)
    * [IPALibrary](https://ipalibrary.me/) - Tweaked Apps
    * ⭐ **PDALife** - [Games](...) / [Apps](...)

and is materialized as a repository schema:

- **name** = the emphasized (``<strong>``) label, or the first linked label
- **url** = the primary link (the link in the emphasized label when present,
  otherwise the first link of the entry)
- **description** = the text after the `` - `` separator with the extra
  reference links stripped out
- **platform** = the zone the entry appears in, overridden by an explicit
  store link (Play Store / APK mirrors -> android, App Store -> ios)

Entries without a resolvable label and an absolute http(s) URL (plain prose
lines, tips, outline/fragment links) are skipped. The listing has no
versioned releases, so ``get_releases`` / ``get_assets`` return empty lists;
the entries exist to be surfaced as applications (name, homepage,
description, platform) in the catalogue.
"""

import hashlib
import re
from datetime import datetime, timedelta
from html import parser as html_parser
from typing import Any

import httpx

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    PageInfo,
    SourceConnector,
)
from omnisource.connectors.http import get_with_retry
from omnisource.connectors.rate_limiter import RateLimiter
from omnisource.core.schemas.asset import AssetSchema
from omnisource.core.schemas.release import ReleaseSchema
from omnisource.core.schemas.repository import (
    RepositorySchema,
    RepositoryStatus,
    RepositoryVisibility,
)
from omnisource.processing.deduplication import slugify

logger = get_logger(__name__)

_USER_AGENT = "OmniSource/0.1.0"

# Explicit store links are unambiguous platform signals and override the
# section zone an entry appears in.
_ANDROID_STORE_MARKERS = (
    "play.google.com",
    "apkmirror.com",
    "apkpure.",
    "apkcombo.com",
    "f-droid.org",
    "izzysoft.de",
)
_IOS_STORE_MARKERS = ("apps.apple.com",)

# Zero-width characters FMHY uses in some labels (``⁠`` before certain names).
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
# Leading emoji / bullet / arrow characters that decorate list labels.
_LEADING_SYMBOLS_RE = re.compile(r"^[^\w]+")
_WS_RE = re.compile(r"\s+")
# Trailing / leading separator runs left behind after reference links are
# removed from the description (e.g. "Tweaked Apps / / / " -> "Tweaked Apps").
_TRAILING_SEPS_RE = re.compile(r"(?:\s*[/|]\s*)+$")
_LEADING_SEPS_RE = re.compile(r"^(?:\s*[/|]\s*)+")
_SEPARATORS_RE = re.compile(r"^\s*[-\u2013\u2014]\s*|\s*[-\u2013\u2014]\s*$")


def _clean_label(value: str | None) -> str:
    """Normalize a raw label into the canonical application name."""
    value = _ZERO_WIDTH_RE.sub("", value or "")
    value = _WS_RE.sub(" ", value).strip()
    value = _LEADING_SYMBOLS_RE.sub("", value).strip()
    return value


def _clean_description(raw: str, label: str) -> str:
    """Extract the " - description" tail of an entry, minus reference links."""
    text = _WS_RE.sub(" ", raw).strip()
    label_pos = text.find(label)
    if label_pos >= 0:
        search_from = label_pos + len(label)
    else:
        search_from = 0
    separator = text.find(" - ", search_from)
    if separator < 0:
        return ""
    description = text[separator + 3 :]
    description = _TRAILING_SEPS_RE.sub("", description)
    description = _LEADING_SEPS_RE.sub("", description)
    description = _SEPARATORS_RE.sub("", description.strip())
    return description.strip()


def _store_platform(url: str) -> str | None:
    """Platform implied by an explicit store link, if any."""
    lowered = url.lower()
    if any(marker in lowered for marker in _IOS_STORE_MARKERS):
        return "ios"
    if any(marker in lowered for marker in _ANDROID_STORE_MARKERS):
        return "android"
    return None


class _ListEntry:
    """Accumulator for one ``<li>`` while walking the page."""

    __slots__ = (
        "_anchors_before_first_strong",
        "_in_strong",
        "_saw_strong",
        "_strong_parts",
        "anchors",
        "full_text",
        "strong_texts",
        "zone",
    )

    def __init__(self) -> None:
        # (href, text, was_inside_strong) in document order
        self.anchors: list[tuple[str, str, bool]] = []
        self.strong_texts: list[str] = []
        self.full_text: list[str] = []
        self._in_strong = False
        self._strong_parts: list[str] = []
        # Platform zone in effect when the entry started (see _PageParser).
        self.zone: str | None = None
        # How many anchors appeared before the first <strong> opened. A
        # leading <strong> is the entry's emphasized label ("**[CyPwn](u)**",
        # "**PDALife**"); a <strong> after the links is a trailing note
        # ("... - Call Recorder / **Check Local Call Recording Laws**").
        self._anchors_before_first_strong = 0
        self._saw_strong = False


class _PageParser(html_parser.HTMLParser):
    """Walk the rendered FMHY page, collecting list entries with their zone.

    Top-level (``h1``/``h2``) section headings name the platform ("Android
    APKs", "iOS Tools", "iOS iPAs"); headings without a platform in the name
    (document title aside, e.g. "Emulators") inherit the current zone, and
    deeper subsections ("Modded APKs", "Social Media Apps") always inherit.
    Entries are only collected once a platform zone is known.
    """

    HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
    ZONE_LEVEL = 2  # h1/h2 set the zone; h3+ subsections inherit

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[_ListEntry] = []
        self.zone: str | None = None
        self._heading_level: int | None = None
        self._heading_parts: list[str] = []
        self._entry: _ListEntry | None = None
        self._li_depth = 0
        self._in_anchor = False
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    @staticmethod
    def _zone_from_title(title: str) -> str | None:
        # "Android / iOS" (document title) names both; the page is laid out
        # Android-first, so android wins.
        if "android" in title:
            return "android"
        if "ios" in title:
            return "ios"
        return None

    # -- event handlers --------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HEADING_TAGS:
            self._heading_level = int(tag[1])
            self._heading_parts = []
            return
        if tag == "li":
            if self.zone is not None:
                self._li_depth += 1
                if self._li_depth == 1:
                    self._entry = _ListEntry()
                    self._entry.zone = self.zone
            return
        entry = self._entry
        if entry is None:
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._in_anchor = True
                self._anchor_href = href
                self._anchor_parts = []
        elif tag in {"strong", "b"}:
            entry._in_strong = True
            entry._strong_parts = []
            if not entry._saw_strong:
                entry._saw_strong = True
                entry._anchors_before_first_strong = len(entry.anchors)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HEADING_TAGS:
            level = self._heading_level
            self._heading_level = None
            if level is not None and level <= self.ZONE_LEVEL:
                title = _WS_RE.sub(" ", "".join(self._heading_parts)).casefold()
                self.zone = self._zone_from_title(title) or self.zone
            return
        if tag == "li":
            if self._entry is not None and self._li_depth > 0:
                self._li_depth -= 1
                if self._li_depth == 0:
                    self.entries.append(self._entry)
                    self._entry = None
            return
        entry = self._entry
        if entry is None:
            return
        if tag == "a":
            if self._in_anchor:
                self._in_anchor = False
                text = _WS_RE.sub(" ", "".join(self._anchor_parts)).strip()
                entry.anchors.append((self._anchor_href or "", text, entry._in_strong))
        elif tag in {"strong", "b"} and entry._in_strong:
            entry._in_strong = False
            entry.strong_texts.append(_WS_RE.sub(" ", "".join(entry._strong_parts)).strip())
            entry._strong_parts = []

    def handle_data(self, data: str) -> None:
        if self._heading_level is not None:
            self._heading_parts.append(data)
            return
        entry = self._entry
        if entry is None:
            return
        entry.full_text.append(data)
        if self._in_anchor:
            self._anchor_parts.append(data)
        if entry._in_strong:
            entry._strong_parts.append(data)


def _resolve_entry(entry: _ListEntry, zone: str) -> dict[str, str] | None:
    """Turn a parsed list entry into {name, url, description, platform}.

    Returns None when the entry has no resolvable label, no absolute http(s)
    URL, or no known platform.
    """
    anchors = [(href, text) for href, text, _ in entry.anchors if href and text]
    # A <strong> that opens before any anchor is the entry's emphasized label
    # ("**[CyPwn](u)**" or "**PDALife**"); a <strong> that follows the links
    # is a trailing note ("... - Call Recorder / **Check Local Call
    # Recording Laws**") and must not be mistaken for the label.
    strong_is_label = bool(entry.strong_texts) and entry._anchors_before_first_strong == 0

    label = ""
    url = ""
    if strong_is_label:
        label = _clean_label(entry.strong_texts[0])
        emphasized = [href for href, _, inside in entry.anchors if inside and href]
        url = emphasized[0] if emphasized else (anchors[0][0] if anchors else "")
    elif anchors:
        label = _clean_label(anchors[0][1])
        url = anchors[0][0]
    if not label:
        return None
    # Fragment/relative links (page outline, in-page anchors) are not apps.
    if not url.startswith(("http://", "https://")):
        return None

    platform = _store_platform(url) or zone
    if platform not in ("android", "ios"):
        return None

    description = _clean_description("".join(entry.full_text), label)
    for _, text, _ in entry.anchors:
        anchor_label = _clean_label(text)
        if anchor_label and anchor_label in description:
            description = description.replace(anchor_label, " ")
    description = _WS_RE.sub(" ", description)
    description = _TRAILING_SEPS_RE.sub("", description)
    description = _LEADING_SEPS_RE.sub("", description)
    return {
        "name": label,
        "url": url,
        "description": description.strip(),
        "platform": platform,
    }


def parse_fmhy_entries(html: str) -> list[dict[str, str]]:
    """Parse the FMHY mobile page (Android + iOS) out of rendered HTML.

    The listing cross-references apps between sections, so identical entries
    (same name and URL) are collapsed to their first occurrence.
    """
    page = _PageParser()
    page.feed(html)
    page.close()
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in page.entries:
        resolved = _resolve_entry(entry, entry.zone or "")
        if resolved is None:
            continue
        key = (resolved["name"].casefold(), resolved["url"])
        if key in seen:
            continue
        seen.add(key)
        entries.append(resolved)
    return entries


class FMHYConnector(SourceConnector):
    """Connector for the fmhy.net Android / iOS mobile listing."""

    source_name = "fmhy"
    source_type = "fmhy"
    base_url = "https://fmhy.net"
    api_url = ""

    def __init__(
        self,
        page_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__()
        settings = get_settings()
        self.page_url = (page_url or settings.sources.FMHY_MOBILE_URL).rstrip("/")
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=60, period=timedelta(minutes=1)
        )
        self._client: httpx.AsyncClient | None = None
        self._entries: list[dict[str, str]] | None = None

    async def initialize(self) -> None:
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": _USER_AGENT,
        }
        self._client = httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True)
        self._entries = None
        self._initialized = True
        logger.info("FMHY connector initialized (%s)", self.page_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorError("FMHY connector not initialized", is_retriable=False)
        return self._client

    async def _fetch_page(self) -> str:
        client = self._require_client()
        response = await get_with_retry(client, self.page_url, limiter=self.rate_limiter)
        if response.status_code >= 400:
            raise ConnectorError(
                f"FMHY page unavailable (HTTP {response.status_code})",
                error_code="HTTP_ERROR",
            )
        return response.text

    async def _get_entries(self) -> list[dict[str, str]]:
        """Parse the page once per initialized connector instance."""
        if self._entries is None:
            html = await self._fetch_page()
            self._entries = parse_fmhy_entries(html)
            logger.info("FMHY: parsed %d entries from %s", len(self._entries), self.page_url)
        return self._entries

    # --- Interface -------------------------------------------------------------

    async def discover(
        self,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> tuple[list[RepositorySchema], PageInfo]:
        """Page through the Android / iOS listing using an offset cursor."""
        entries = await self._get_entries()

        offset = 0
        if cursor:
            try:
                offset = max(0, int(cursor))
            except ValueError:
                offset = 0

        window = entries[offset : offset + limit]
        repositories = [self._entry_to_repository(entry, entries) for entry in window]

        if query:
            lowered = query.lower()
            repositories = [
                r
                for r in repositories
                if lowered in r.name.lower() or lowered in (r.description or "").lower()
            ]

        next_offset = offset + limit
        has_next = next_offset < len(entries)
        page_info = PageInfo(
            page=(offset // max(limit, 1)) + 1,
            per_page=limit,
            total=len(entries),
            has_next=has_next,
            has_previous=offset > 0,
            next_cursor=str(next_offset) if has_next else None,
            prev_cursor=str(max(0, offset - limit)) if offset > 0 else None,
        )
        return repositories, page_info

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        entries = await self._get_entries()
        for entry in entries:
            external_id = self._external_id(entry, entries)
            if repository_id in (external_id, f"fmhy/{external_id}", entry["name"]):
                return self._entry_to_repository(entry, entries)
        raise ConnectorError(
            f"FMHY entry not found: {repository_id}", error_code="HTTP_404", is_retriable=False
        )

    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        # The listing has no versioned releases; entries are catalogue records.
        return []

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        return []

    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        entries = await self._get_entries()
        platform: str | None = None
        for entry in entries:
            if self._external_id(entry, entries) == repository.external_id:
                platform = entry["platform"]
                break
        return {
            "source": "fmhy",
            "homepage": repository.homepage,
            # "platforms" is consumed by the sync service to associate the
            # application with the target platform(s) for feed generation.
            "platforms": [platform] if platform else [],
            "topics": [platform] if platform else [],
        }

    async def health_check(self) -> ConnectorHealth:
        started = datetime.now()
        try:
            response = await self._require_client().get(self.page_url)
            latency_ms = (datetime.now() - started).total_seconds() * 1000
            if response.status_code >= 400:
                self.update_health(
                    healthy=False,
                    last_check=datetime.now(),
                    last_error=f"HTTP {response.status_code}",
                )
            else:
                self.update_health(
                    healthy=True,
                    latency_ms=latency_ms,
                    last_check=datetime.now(),
                    last_success=datetime.now(),
                )
        except Exception as exc:
            self.update_health(
                healthy=False,
                last_check=datetime.now(),
                last_error=str(exc),
            )
        return self._health

    # --- Helpers ----------------------------------------------------------------

    @staticmethod
    def _external_id(entry: dict[str, str], entries: list[dict[str, str]]) -> str:
        """Stable unique external id for an entry.

        Names are slugs; when the same name is listed more than once (the
        listing covers both platforms, so e.g. "Brave" appears for Android
        and iOS) the platform is appended, and a URL hash resolves any
        remaining clash.
        """
        base = slugify(entry["name"]) or "entry"
        same_name = [e for e in entries if slugify(e["name"]) == base]
        if len(same_name) == 1:
            return base
        candidate = f"{base}-{entry['platform']}"
        same_name_platform = [e for e in same_name if e["platform"] == entry["platform"]]
        if len(same_name_platform) == 1:
            return candidate
        digest = hashlib.sha256(entry["url"].encode("utf-8")).hexdigest()[:8]
        return f"{candidate}-{digest}"

    def _entry_to_repository(
        self, entry: dict[str, str], entries: list[dict[str, str]]
    ) -> RepositorySchema:
        external_id = self._external_id(entry, entries)
        return RepositorySchema(
            external_id=external_id,
            full_name=f"fmhy/{external_id}",
            name=entry["name"],
            description=entry["description"] or None,
            homepage=entry["url"],
            html_url=entry["url"],
            api_url=None,
            status=RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            topics=[entry["platform"]],
            source_type=self.source_type,
        )
