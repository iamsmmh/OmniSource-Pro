"""Windows platform feed."""

from omnisource.feeds.platform_feeds.base import PlatformFeed


class WindowsFeed(PlatformFeed):
    platform_type = "windows"
