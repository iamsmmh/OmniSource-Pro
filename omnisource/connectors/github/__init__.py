"""GitHub connector for OmniSource."""

from omnisource.connectors.github.client import GitHubClient
from omnisource.connectors.github.connector import GitHubConnector
from omnisource.connectors.github.models import GitHubAsset, GitHubRelease, GitHubRepository

__all__ = [
    "GitHubAsset",
    "GitHubClient",
    "GitHubConnector",
    "GitHubRelease",
    "GitHubRepository",
]
