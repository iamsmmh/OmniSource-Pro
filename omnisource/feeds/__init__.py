"""Feed generation for OmniSource."""

from omnisource.feeds.generator import FeedGenerator
from omnisource.feeds.platform_feeds import FEED_REGISTRY

__all__ = ["FEED_REGISTRY", "FeedGenerator"]
