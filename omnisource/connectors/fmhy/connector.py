"""FMHY (freemediaheckyeah) connector for OmniSource.

Indexes the curated "iOS iPAs" listing from
https://fmhy.net/mobile#ios-ipas .

fmhy.net is a VitePress static site, so the connector fetches the rendered
mobile page and locates the "iOS iPAs" section in the HTML. Each list entry
of the section is shaped like::

    * 🌐 **[CyPwn](https://ipa.cypwn.xyz/)** - Tweaked App Library / [AltStore](...)
    * [IPALibrary](https://ipalibrary.me/) - Tweaked Apps
    * ⭐ **PDALife** - [Games](...) / [Apps](...)

and is materialized as a repository schema:

- **name** = the emphasized (``<strong>``) label, or the first linked label
- **url** = the primary link (the link in the emphasized label when present,
  otherwise the first link of the entry)
- **description** = the text after the `` - `` separator with the extra
  reference links stripped out

Entries without a resolvable label and URL (plain prose lines, tips) are
skipped. The listing has no versioned releases, so ``get_releases`` /
``get_assets`` return empty lists; the entries exist to be surfaced as
applications (name, homepage, description) in the catalogue.
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
_SECTION_TITLE = "ios ipas"

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


class _ListEntry:
    """Accumulator for one ``<li>`` inside the section being parsed."""

    __slots__ = ("_in_strong", "_strong_parts", "anchors", "full_text", "strong_texts")

    def __init__(self) -> None:
        # (href, text, was_inside_strong) in document order
        self.anchors: list[tuple[str, str, bool]] = []
        self.strong_texts: list[str] = []
        self.full_text: list[str] = []
        self._in_strong = False
        self._strong_parts: list[str] = []


class _SectionParser(html_parser.HTMLParser):
    """Extract list entries from the FMHY section whose heading matches.

    The section starts at the first heading containing ``section_title``
    (case-insensitive) and ends at the next heading.
    """

    HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self, section_title: str) -> None:
        super().__init__(convert_charrefs=True)
        self._section_title = section_title.casefold()
        self.entries: list[_ListEntry] = []
        self._in_heading = False
        self._heading_parts: list[str] = []
        self._in_section = False
        self._entry: _ListEntry | None = None
        self._li_depth = 0
        self._in_anchor = False
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    # -- event handlers --------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HEADING_TAGS:
            if self._in_section and self.entries:
                self._in_section = False
            self._in_heading = True
            self._heading_parts = []
            return
        if tag == "li":
            if self._in_section:
                self._li_depth += 1
                if self._li_depth == 1:
                    self._entry = _ListEntry()
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

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HEADING_TAGS:
            if self._in_heading:
                self._in_heading = False
                title = _WS_RE.sub(" ", "".join(self._heading_parts)).casefold()
                if self._section_title in title:
                    self._in_section = True
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
        if self._in_heading:
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


def _resolve_entry(entry: _ListEntry) -> dict[str, str] | None:
    """Turn a parsed list entry into {name, url, description} or None."""
    label = _clean_label(entry.strong_texts[0]) if entry.strong_texts else ""
    anchors = [(href, text) for href, text, _ in entry.anchors if href and text]
    if not label and anchors:
        label = _clean_label(anchors[0][1])
    if not label:
        return None

    if entry.strong_texts:
        emphasized = [href for href, _, inside in entry.anchors if inside and href]
        url = emphasized[0] if emphasized else (anchors[0][0] if anchors else "")
    else:
        url = anchors[0][0] if anchors else ""
    if not url:
        return None

    description = _clean_description("".join(entry.full_text), label)
    for _, text, _ in entry.anchors:
        anchor_label = _clean_label(text)
        if anchor_label and anchor_label in description:
            description = description.replace(anchor_label, " ")
    description = _WS_RE.sub(" ", description)
    description = _TRAILING_SEPS_RE.sub("", description)
    description = _LEADING_SEPS_RE.sub("", description)
    return {"name": label, "url": url, "description": description.strip()}


def parse_fmhy_entries(html: str, section_title: str = "iOS iPAs") -> list[dict[str, str]]:
    """Parse the FMHY section out of rendered page HTML."""
    page = _SectionParser(section_title)
    page.feed(html)
    page.close()
    entries: list[dict[str, str]] = []
    for entry in page.entries:
        resolved = _resolve_entry(entry)
        if resolved is not None:
            entries.append(resolved)
    return entries


class FMHYConnector(SourceConnector):
    """Connector for the fmhy.net mobile (iOS iPAs) listing."""

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
        """Parse the section once per initialized connector instance."""
        if self._entries is None:
            html = await self._fetch_page()
            self._entries = parse_fmhy_entries(html, "iOS iPAs")
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
        """Page through the iOS iPAs listing using an offset cursor."""
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
            external_id = self._external_id(entry["name"], entry["url"], entries)
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
        return {
            "source": "fmhy",
            "homepage": repository.homepage,
            "topics": ["ios", "ios-ipas", "ipa"],
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
    def _external_id(name: str, url: str, entries: list[dict[str, str]]) -> str:
        """Stable unique external id: name slug, hash-disambiguated on clashes."""
        base = slugify(name) or "entry"
        same_name = [e for e in entries if slugify(e["name"]) == base]
        if len(same_name) <= 1:
            return base
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        return f"{base}-{digest}"

    def _entry_to_repository(
        self, entry: dict[str, str], entries: list[dict[str, str]]
    ) -> RepositorySchema:
        external_id = self._external_id(entry["name"], entry["url"], entries)
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
            source_type=self.source_type,
        )
