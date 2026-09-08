"""Linux platform feed."""

from omnisource.feeds.platform_feeds.base import PlatformFeed


class LinuxFeed(PlatformFeed):
    platform_type = "linux"
