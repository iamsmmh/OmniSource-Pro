"""Connector registry mapping source types to connector classes."""

from typing import Dict, Type

from omnisource.connectors.base import SourceConnector

# Lazily imported connector class paths keyed by source type.
# Note: Codeberg and Forgejo expose the Gitea API (future work).
_CONNECTOR_PATHS: Dict[str, str] = {
    "github": "omnisource.connectors.github.connector:GitHubConnector",
    "gitlab": "omnisource.connectors.gitlab.connector:GitLabConnector",
}

_connector_cache: Dict[str, Type[SourceConnector]] = {}


def _import_class(path: str) -> Type[SourceConnector]:
    module_path, _, class_name = path.partition(":")
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)


def get_connector_class(source_type: str) -> Type[SourceConnector]:
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
    "get_connector_class",
    "create_connector",
    "register_connector",
    "available_sources",
]
