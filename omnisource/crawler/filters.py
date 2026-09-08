"""Repository filtering policies for discovery."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RepositoryFilter:
    """Filters raw repository records before they are ingested."""

    min_stars: int = 0
    exclude_forks: bool = True
    exclude_archived: bool = True
    exclude_disabled: bool = True
    require_description: bool = False
    allowed_licenses: Optional[set] = None

    def should_include(self, repo: Dict[str, Any]) -> bool:
        """Return True if the repository should be ingested."""
        if self.exclude_forks and repo.get("fork"):
            return False
        if self.exclude_archived and repo.get("archived"):
            return False
        if self.exclude_disabled and repo.get("disabled"):
            return False

        stars = int(repo.get("stargazers_count") or repo.get("stars") or 0)
        if stars < self.min_stars:
            return False

        if self.require_description and not repo.get("description"):
            return False

        if self.allowed_licenses is not None:
            license_spdx = repo.get("license", {}).get("spdx_id") if isinstance(repo.get("license"), dict) else None
            if license_spdx not in self.allowed_licenses:
                return False

        return True

    def apply(self, repositories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter a list of raw repository records."""
        return [repo for repo in repositories if self.should_include(repo)]


__all__ = ["RepositoryFilter"]
