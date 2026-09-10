"""Database models for OmniSource."""

from omnisource.core.models.application import Application, ApplicationRelationship
from omnisource.core.models.asset import Asset, AssetValidation
from omnisource.core.models.base import Base
from omnisource.core.models.category import Category, Tag
from omnisource.core.models.developer import Developer, Organization
from omnisource.core.models.license import License
from omnisource.core.models.platform import Architecture, Platform
from omnisource.core.models.quarantine import Quarantine, SecurityScan, SecurityStatus
from omnisource.core.models.release import Release, ReleaseAsset, ReleaseHistory
from omnisource.core.models.repository import Repository, RepositoryMetadata
from omnisource.core.models.scores import PopularityScore, QualityScore, TrustScore
from omnisource.core.models.screenshot import Icon, Screenshot
from omnisource.core.models.source import Source, SourceHealth
from omnisource.core.models.sync import SyncJob, SyncState
from omnisource.core.models.validation import ValidationResult

__all__ = [
    "Application",
    "ApplicationRelationship",
    "Architecture",
    "Asset",
    "AssetValidation",
    "Base",
    "Category",
    "Developer",
    "Icon",
    "License",
    "Organization",
    "Platform",
    "PopularityScore",
    "QualityScore",
    "Quarantine",
    "Release",
    "ReleaseAsset",
    "ReleaseHistory",
    "Repository",
    "RepositoryMetadata",
    "Screenshot",
    "SecurityScan",
    "SecurityStatus",
    "Source",
    "SourceHealth",
    "SyncJob",
    "SyncState",
    "Tag",
    "TrustScore",
    "ValidationResult",
]
