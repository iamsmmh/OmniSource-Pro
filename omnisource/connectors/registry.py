"""Connector registry mapping source types to connector classes."""

from omnisource.connectors.base import SourceConnector

# Lazily imported connector class paths keyed by source type.
_CONNECTOR_PATHS: dict[str, str] = {
    "github": "omnisource.connectors.github.connector:GitHubConnector",
    "gitlab": "omnisource.connectors.gitlab.connector:GitLabConnector",
    "codeberg": "omnisource.connectors.codeberg.connector:CodebergConnector",
    "forgejo": "omnisource.connectors.forgejo.connector:ForgejoConnector",
    "fdroid": "omnisource.connectors.fdroid.connector:FDroidConnector",
    "flathub": "omnisource.connectors.flathub.connector:FlathubConnector",
    "winget": "omnisource.connectors.winget.connector:WingetConnector",
    "homebrew": "omnisource.connectors.homebrew.connector:HomebrewConnector",
    "fmhy": "omnisource.connectors.fmhy.connector:FMHYConnector",
}

_connector_cache: dict[str, type[SourceConnector]] = {}


def _import_class(path: str) -> type[SourceConnector]:
    module_path, _, class_name = path.partition(":")
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def get_connector_class(source_type: str) -> type[SourceConnector]:
    """Return the connector class for a source type."""
    source_type = source_type.lower()
    if source_type not in _CONNECTOR_PATHS:
        raise ValueError(f"No connector registered for source type: {source_type}")
    if source_type not in _connector_cache:
        _connector_cache[source_type] = _import_class(_CONNECTOR_PATHS[source_type])
    return _connector_cache[source_type]


def create_connector(source_type: str, **kwargs) -> SourceConnector:
    """Instantiate a connector for a source type."""
    return get_connector_class(source_type)(**kwargs)


def register_connector(source_type: str, path: str) -> None:
    """Register a connector class path for a source type."""
    _CONNECTOR_PATHS[source_type.lower()] = path
    _connector_cache.pop(source_type.lower(), None)


def available_sources() -> list:
    """Return the list of registered source types."""
    return sorted(_CONNECTOR_PATHS.keys())


__all__ = [
    "available_sources",
    "create_connector",
    "get_connector_class",
    "register_connector",
]
