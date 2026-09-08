"""Android platform feed."""

from omnisource.feeds.platform_feeds.base import PlatformFeed


class AndroidFeed(PlatformFeed):
    platform_type = "android"
