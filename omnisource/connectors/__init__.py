"""Source connectors for OmniSource."""

from omnisource.connectors.base import SourceConnector
from omnisource.connectors.cache import ResponseCache
from omnisource.connectors.codeberg import CodebergConnector
from omnisource.connectors.fdroid import FDroidConnector
from omnisource.connectors.flathub import FlathubConnector
from omnisource.connectors.forgejo import ForgejoConnector
from omnisource.connectors.github import GitHubConnector
from omnisource.connectors.gitlab import GitLabConnector
from omnisource.connectors.homebrew import HomebrewConnector
from omnisource.connectors.rate_limiter import RateLimiter
from omnisource.connectors.winget import WingetConnector

__all__ = [
    "CodebergConnector",
    "FDroidConnector",
    "FlathubConnector",
    "ForgejoConnector",
    "GitHubConnector",
    "GitLabConnector",
    "HomebrewConnector",
    "RateLimiter",
    "ResponseCache",
    "SourceConnector",
    "WingetConnector",
]
