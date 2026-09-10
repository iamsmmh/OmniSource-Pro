"""Forgejo connector for OmniSource.

Forgejo is the software powering codeberg.org; any Forgejo instance can be
indexed by passing ``base_url``/``api_url`` to the constructor.
"""

from omnisource.connectors.gitea.connector import GiteaConnectorBase


class ForgejoConnector(GiteaConnectorBase):
    """Connects to a Forgejo instance (defaults to codeberg.org)."""

    source_name = "forgejo"
    source_type = "forgejo"
    base_url = "https://codeberg.org"
    api_url = "https://codeberg.org/api/v1"
    _settings_token_attr = "FORGEJO_TOKEN"  # noqa: S105 - settings key name, not a secret
