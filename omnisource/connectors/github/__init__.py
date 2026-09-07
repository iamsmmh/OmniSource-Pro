"""GitHub connector for OmniSource."""

from omnisource.connectors.github.connector import GitHubConnector
from omnisource.connectors.github.client import GitHubClient
from omnisource.connectors.github.models import GitHubRepository, GitHubRelease, GitHubAsset

__all__ = [
    "GitHubConnector",
    "GitHubClient",
    "GitHubRepository",
    "GitHubRelease",
    "GitHubAsset",
]
