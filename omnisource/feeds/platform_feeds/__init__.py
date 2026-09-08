"""Platform-specific feed definitions."""

from omnisource.feeds.platform_feeds.android import AndroidFeed
from omnisource.feeds.platform_feeds.base import PlatformFeed, UniversalFeed
from omnisource.feeds.platform_feeds.ios import IOSFeed
from omnisource.feeds.platform_feeds.linux import LinuxFeed
from omnisource.feeds.platform_feeds.macos import MacOSFeed
from omnisource.feeds.platform_feeds.windows import WindowsFeed

FEED_REGISTRY = {
    "all": UniversalFeed,
    "ios": IOSFeed,
    "android": AndroidFeed,
    "windows": WindowsFeed,
    "macos": MacOSFeed,
    "linux": LinuxFeed,
}

__all__ = [
    "PlatformFeed",
    "UniversalFeed",
    "IOSFeed",
    "AndroidFeed",
    "WindowsFeed",
    "MacOSFeed",
    "LinuxFeed",
    "FEED_REGISTRY",
]
