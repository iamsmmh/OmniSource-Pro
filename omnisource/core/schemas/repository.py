"""Pydantic schemas for software repositories."""

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class RepositoryStatus(str, Enum):
    """Status of a repository."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    MIRROR = "mirror"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class RepositoryVisibility(str, Enum):
    """Visibility of a repository."""

    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class RepositorySchema(BaseSchema):
    """Schema for a software repository."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    external_id: str = Field(..., description="External identifier from the source")
    full_name: str = Field(..., description="Full name (owner/repo)")
    name: str = Field(..., description="Repository name")
    description: Optional[str] = Field(default=None, description="Description")
    homepage: Optional[str] = Field(default=None, description="Homepage URL")
    html_url: str = Field(..., description="HTML URL")
    api_url: Optional[str] = Field(default=None, description="API URL")
    status: RepositoryStatus = Field(default=RepositoryStatus.UNKNOWN, description="Status")
    visibility: RepositoryVisibility = Field(
        default=RepositoryVisibility.PUBLIC, description="Visibility"
    )
    is_fork: bool = Field(default=False, description="Is a fork")
    is_archived: bool = Field(default=False, description="Is archived")
    stars: int = Field(default=0, description="Star count")
    forks: int = Field(default=0, description="Fork count")
    open_issues: int = Field(default=0, description="Open issues count")
    size_kb: int = Field(default=0, description="Size in kilobytes")
    language: Optional[str] = Field(default=None, description="Primary language")
    default_branch: Optional[str] = Field(default=None, description="Default branch")
    created_at_external: Optional[datetime] = Field(default=None, description="External creation time")
    updated_at_external: Optional[datetime] = Field(default=None, description="External update time")
    pushed_at: Optional[datetime] = Field(default=None, description="Last push time")
    license_spdx: Optional[str] = Field(default=None, description="SPDX license identifier")
    topics: List[str] = Field(default_factory=list, description="Repository topics")
    source_type: Optional[str] = Field(default=None, description="Source type")


class RepositoryMetadataSchema(BaseSchema):
    """Schema for extended repository metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    repository_id: UUID = Field(..., description="Repository identifier")
    readme: Optional[str] = Field(default=None, description="README content")
    readme_html: Optional[str] = Field(default=None, description="Rendered README")
    topics: List[str] = Field(default_factory=list, description="Topics")
    license_spdx: Optional[str] = Field(default=None, description="SPDX license identifier")
    has_wiki: bool = Field(default=False, description="Has wiki")
    has_issues: bool = Field(default=False, description="Has issues")
    has_discussions: bool = Field(default=False, description="Has discussions")
    has_projects: bool = Field(default=False, description="Has projects")
    has_downloads: bool = Field(default=False, description="Has downloads")
    contributors_count: int = Field(default=0, description="Contributors count")
    commit_count: int = Field(default=0, description="Commit count")
    last_commit_sha: Optional[str] = Field(default=None, description="Last commit SHA")
    last_commit_message: Optional[str] = Field(default=None, description="Last commit message")
    last_commit_date: Optional[datetime] = Field(default=None, description="Last commit date")
