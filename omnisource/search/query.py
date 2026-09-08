"""Search query construction utilities."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def build_filter_string(filters: Dict[str, Any]) -> Optional[str]:
    """Build a Meilisearch filter expression from a filters dictionary.

    Example::

        build_filter_string({"platform": "linux", "open_source": True})
        # -> "platform = 'linux' AND open_source = true"
    """
    parts: List[str] = []
    for key, value in filters.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            parts.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, (int, float)):
            parts.append(f"{key} = {value}")
        elif isinstance(value, list):
            quoted = ", ".join(f"'{str(v)}'" for v in value)
            parts.append(f"{key} IN [{quoted}]")
        else:
            escaped = str(value).replace("'", "\\'")
            parts.append(f"{key} = '{escaped}'")
    return " AND ".join(parts) if parts else None


@dataclass
class SearchQuery:
    """A structured search query."""

    q: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    sort: Optional[List[str]] = None
    limit: int = 30
    offset: int = 0
    facets: Optional[List[str]] = None

    def filter_string(self) -> Optional[str]:
        return build_filter_string(self.filters)

    def to_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": self.limit, "offset": self.offset}
        if self.q:
            params["q"] = self.q
        filter_str = self.filter_string()
        if filter_str:
            params["filter"] = filter_str
        if self.sort:
            params["sort"] = self.sort
        if self.facets:
            params["facets"] = self.facets
        return params
