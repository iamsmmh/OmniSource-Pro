"""macOS platform feed."""

from omnisource.feeds.platform_feeds.base import PlatformFeed


class MacOSFeed(PlatformFeed):
    platform_type = "macos"
