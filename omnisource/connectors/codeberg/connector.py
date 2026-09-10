"""Codeberg connector for OmniSource."""

from omnisource.connectors.gitea.connector import GiteaConnectorBase


class CodebergConnector(GiteaConnectorBase):
    """Connects to codeberg.org through the Gitea-compatible API."""

    source_name = "codeberg"
    source_type = "codeberg"
    base_url = "https://codeberg.org"
    api_url = "https://codeberg.org/api/v1"
    _settings_token_attr = "CODEBERG_TOKEN"  # noqa: S105 - settings key name, not a secret
