"""Pydantic schemas for OmniSource."""

from omnisource.core.schemas.application import (
    ApplicationRelationshipSchema,
    ApplicationSchema,
    ApplicationStatusSchema,
    OpenSourceStatusSchema,
)
from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
from omnisource.core.schemas.base import BaseSchema
from omnisource.core.schemas.category import CategorySchema, CategoryType, TagSchema
from omnisource.core.schemas.developer import DeveloperSchema, OrganizationSchema
from omnisource.core.schemas.experience import (
    AnalyticsEventRequest,
    AnalyticsSummary,
    CollectionCreate,
    CollectionItemRequest,
    CollectionResponse,
    FavoriteRequest,
    FavoriteResponse,
    InteractionTypeSchema,
    PaginatedCollections,
    PaginatedFavorites,
)
from omnisource.core.schemas.icon import IconSchema
from omnisource.core.schemas.license import LicenseSchema

# OmniStore-compatible schemas
from omnisource.core.schemas.omnistore import (
    OmniStoreAppSchema,
    OmniStoreAssetSchema,
    OmniStoreDeveloperSchema,
    OmniStoreReleaseSchema,
    OmniStoreScoresSchema,
    PaginatedAppsSchema,
)
from omnisource.core.schemas.platform import (
    ArchitectureSchema,
    ArchitectureType,
    PlatformSchema,
    PlatformType,
)
from omnisource.core.schemas.quarantine import (
    QuarantineReasonSchema,
    QuarantineSchema,
    QuarantineStatusSchema,
)
from omnisource.core.schemas.recommendations import (
    RecommendationItem,
    RecommendationKind,
    RecommendationResponse,
    SecurityResponse,
    TrustBadge,
    TrustResponse,
)
from omnisource.core.schemas.release import (
    PackageTypeSchema,
    ReleaseAssetSchema,
    ReleaseSchema,
    ReleaseStatusSchema,
)
from omnisource.core.schemas.repository import RepositoryMetadataSchema, RepositorySchema
from omnisource.core.schemas.scores import (
    PopularityScoreSchema,
    QualityScoreSchema,
    TrustScoreSchema,
)
from omnisource.core.schemas.screenshot import ScreenshotSchema
from omnisource.core.schemas.security import SecurityScanSchema, SecurityStatusSchema
from omnisource.core.schemas.source import SourceHealthSchema, SourceSchema
from omnisource.core.schemas.sync import (
    SyncJobSchema,
    SyncJobStatusSchema,
    SyncJobTypeSchema,
    SyncStateSchema,
)
from omnisource.core.schemas.validation import (
    ValidationResultSchema,
    ValidationStatusSchema,
    ValidationTypeSchema,
)

__all__ = [
    "AnalyticsEventRequest",
    "AnalyticsSummary",
    "ApplicationRelationshipSchema",
    # Application
    "ApplicationSchema",
    "ApplicationStatusSchema",
    "ArchitectureSchema",
    "ArchitectureType",
    # Asset
    "AssetSchema",
    "AssetSourceSchema",
    "AssetStatusSchema",
    # Base
    "BaseSchema",
    # Category
    "CategorySchema",
    "CategoryType",
    "CollectionCreate",
    "CollectionItemRequest",
    "CollectionResponse",
    # Developer
    "DeveloperSchema",
    # Icon
    "FavoriteRequest",
    "FavoriteResponse",
    "IconSchema",
    "InteractionTypeSchema",
    # License
    "LicenseSchema",
    # OmniStore
    "OmniStoreAppSchema",
    "OmniStoreAssetSchema",
    "OmniStoreDeveloperSchema",
    "OmniStoreReleaseSchema",
    "OmniStoreScoresSchema",
    "OpenSourceStatusSchema",
    "OrganizationSchema",
    "PackageTypeSchema",
    "PaginatedAppsSchema",
    "PaginatedCollections",
    "PaginatedFavorites",
    # Platform
    "PlatformSchema",
    "PlatformType",
    "PopularityScoreSchema",
    "QualityScoreSchema",
    "QuarantineReasonSchema",
    # Quarantine
    "QuarantineSchema",
    "QuarantineStatusSchema",
    "RecommendationItem",
    "RecommendationKind",
    "RecommendationResponse",
    "ReleaseAssetSchema",
    # Release
    "ReleaseSchema",
    "ReleaseStatusSchema",
    "RepositoryMetadataSchema",
    # Repository
    "RepositorySchema",
    # Screenshot
    "ScreenshotSchema",
    "SecurityResponse",
    # Security
    "SecurityScanSchema",
    "SecurityStatusSchema",
    "SourceHealthSchema",
    # Source
    "SourceSchema",
    "SyncJobSchema",
    "SyncJobStatusSchema",
    "SyncJobTypeSchema",
    # Sync
    "SyncStateSchema",
    "TagSchema",
    # Scores
    "TrustBadge",
    "TrustResponse",
    "TrustScoreSchema",
    # Validation
    "ValidationResultSchema",
    "ValidationStatusSchema",
    "ValidationTypeSchema",
]
