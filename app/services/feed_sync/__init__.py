"""Production-grade feed ingestion pipeline.

Pipeline stages (in order):

    GitHub Sources
    -> Sync Engine          (incremental, retry, rate-limit aware)
    -> Validation Engine    (source + repository eligibility)
    -> Metadata Processing  (parse -> normalize -> deduplicate)
    -> Security Pipeline    (transactional publish with rollback,
                             security-profile refresh, search indexing)
    -> PostgreSQL / Redis / Meilisearch
    -> REST API / OmniStore-Pro
"""

from app.services.feed_sync.feed_deduplicator import FeedDeduplicator
from app.services.feed_sync.feed_normalizer import FeedNormalizer
from app.services.feed_sync.feed_parser import FeedParser, FeedValidationError
from app.services.feed_sync.feed_publisher import FeedPublisher, FeedPublishError
from app.services.feed_sync.github_provider import GitHubFeedProvider
from app.services.feed_sync.schemas import (
    FeedAsset,
    FeedDocument,
    FeedItem,
    FeedRelease,
    SyncCheckpoint,
)
from app.services.feed_sync.source_validator import SourceValidator
from app.services.feed_sync.sync_engine import FeedSyncEngine, SyncReport

__all__ = [
    "FeedAsset",
    "FeedDeduplicator",
    "FeedDocument",
    "FeedItem",
    "FeedNormalizer",
    "FeedParser",
    "FeedPublishError",
    "FeedPublisher",
    "FeedRelease",
    "FeedSyncEngine",
    "FeedValidationError",
    "GitHubFeedProvider",
    "SourceValidator",
    "SyncCheckpoint",
    "SyncReport",
]
