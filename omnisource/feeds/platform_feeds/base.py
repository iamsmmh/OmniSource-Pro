"""Base platform feed definition."""

from omnisource.core.schemas.omnistore import OmniStoreApp


class PlatformFeed:
    """Defines a platform-specific feed."""

    platform_type: str = "all"

    def filter(self, apps: list[OmniStoreApp]) -> list[OmniStoreApp]:
        """Filter applications for this platform."""
        return [app for app in apps if self.platform_type in (app.platforms or [])]


class UniversalFeed(PlatformFeed):
    """Universal feed containing all applications."""

    platform_type = "all"

    def filter(self, apps: list[OmniStoreApp]) -> list[OmniStoreApp]:
        return list(apps)
