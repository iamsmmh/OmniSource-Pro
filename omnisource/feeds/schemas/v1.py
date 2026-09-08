"""Version 1 feed schema."""

from omnisource.feeds.schemas.base import FeedEnvelope

V1_VERSION = "v1"


class FeedV1(FeedEnvelope):
    """Version 1 of the OmniSource feed schema."""

    version: str = V1_VERSION
