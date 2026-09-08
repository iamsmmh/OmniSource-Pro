"""iOS platform feed."""

from omnisource.feeds.platform_feeds.base import PlatformFeed


class IOSFeed(PlatformFeed):
    platform_type = "ios"
