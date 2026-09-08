"""Pydantic schemas for OmniSource."""

from omnisource.core.schemas.base import BaseSchema
from omnisource.core.schemas.source import SourceSchema, SourceHealthSchema
from omnisource.core.schemas.repository import RepositorySchema, RepositoryMetadataSchema
from omnisource.core.schemas.application import (
    ApplicationSchema,
    ApplicationRelationshipSchema,
    ApplicationStatusSchema,
    OpenSourceStatusSchema,
)
from omnisource.core.schemas.developer import DeveloperSchema, OrganizationSchema
from omnisource.core.schemas.license import LicenseSchema
from omnisource.core.schemas.platform import PlatformSchema, ArchitectureSchema, PlatformType, ArchitectureType
from omnisource.core.schemas.category import CategorySchema, TagSchema, CategoryType
from omnisource.core.schemas.release import ReleaseSchema, ReleaseAssetSchema, ReleaseStatusSchema, PackageTypeSchema
from omnisource.core.schemas.asset import AssetSchema, AssetStatusSchema, AssetSourceSchema
from omnisource.core.schemas.screenshot import ScreenshotSchema
from omnisource.core.schemas.icon import IconSchema
from omnisource.core.schemas.scores import TrustScoreSchema, QualityScoreSchema, PopularityScoreSchema
from omnisource.core.schemas.validation import ValidationResultSchema, ValidationTypeSchema, ValidationStatusSchema
from omnisource.core.schemas.sync import SyncStateSchema, SyncJobSchema, SyncJobTypeSchema, SyncJobStatusSchema
from omnisource.core.schemas.quarantine import QuarantineSchema, QuarantineReasonSchema, QuarantineStatusSchema
from omnisource.core.schemas.security import SecurityScanSchema, SecurityStatusSchema

# OmniStore-compatible schemas
from omnisource.core.schemas.omnistore import (
    OmniStoreAppSchema,
    OmniStoreAssetSchema,
    OmniStoreReleaseSchema,
    OmniStoreDeveloperSchema,
    OmniStoreScoresSchema,
    PaginatedAppsSchema,
)

__all__ = [
    # Base
    "BaseSchema",
    # Source
    "SourceSchema",
    "SourceHealthSchema",
    # Repository
    "RepositorySchema",
    "RepositoryMetadataSchema",
    # Application
    "ApplicationSchema",
    "ApplicationRelationshipSchema",
    "ApplicationStatusSchema",
    "OpenSourceStatusSchema",
    # Developer
    "DeveloperSchema",
    "OrganizationSchema",
    # License
    "LicenseSchema",
    # Platform
    "PlatformSchema",
    "ArchitectureSchema",
    "PlatformType",
    "ArchitectureType",
    # Category
    "CategorySchema",
    "TagSchema",
    "CategoryType",
    # Release
    "ReleaseSchema",
    "ReleaseAssetSchema",
    "ReleaseStatusSchema",
    "PackageTypeSchema",
    # Asset
    "AssetSchema",
    "AssetStatusSchema",
    "AssetSourceSchema",
    # Screenshot
    "ScreenshotSchema",
    # Icon
    "IconSchema",
    # Scores
    "TrustScoreSchema",
    "QualityScoreSchema",
    "PopularityScoreSchema",
    # Validation
    "ValidationResultSchema",
    "ValidationTypeSchema",
    "ValidationStatusSchema",
    # Sync
    "SyncStateSchema",
    "SyncJobSchema",
    "SyncJobTypeSchema",
    "SyncJobStatusSchema",
    # Quarantine
    "QuarantineSchema",
    "QuarantineReasonSchema",
    "QuarantineStatusSchema",
    # Security
    "SecurityScanSchema",
    "SecurityStatusSchema",
    # OmniStore
    "OmniStoreAppSchema",
    "OmniStoreAssetSchema",
    "OmniStoreReleaseSchema",
    "OmniStoreDeveloperSchema",
    "OmniStoreScoresSchema",
    "PaginatedAppsSchema",
]
