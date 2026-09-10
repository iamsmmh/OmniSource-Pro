"""Shared client and connector base for Gitea-compatible forges."""

from omnisource.connectors.gitea.client import GiteaClient
from omnisource.connectors.gitea.connector import GiteaConnectorBase

__all__ = ["GiteaClient", "GiteaConnectorBase"]
