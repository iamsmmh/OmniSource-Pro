"""
OmniSource - Autonomous Open-Source Software Discovery & Distribution Platform

This package provides the core functionality for discovering, indexing, validating,
and distributing open-source software metadata to power OmniStore.
"""

__version__ = "0.1.0"
__author__ = "OmniSource Team"
__license__ = "AGPL-3.0"

from omnisource.config.settings import get_settings

# Initialize settings
settings = get_settings()

__all__ = ["__author__", "__license__", "__version__", "settings"]
