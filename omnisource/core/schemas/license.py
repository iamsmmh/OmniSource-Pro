"""Pydantic schemas for licenses."""

from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class LicenseSchema(BaseSchema):
    """Schema for a software license."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    license_id: str = Field(..., description="License identifier")
    spdx_id: str | None = Field(default=None, description="SPDX identifier")
    name: str = Field(..., description="Name")
    short_name: str | None = Field(default=None, description="Short name")
    description: str | None = Field(default=None, description="Description")
    url: str | None = Field(default=None, description="URL")
    is_osi_approved: bool = Field(default=False, description="OSI approved")
    is_fsf_approved: bool = Field(default=False, description="FSF approved")
