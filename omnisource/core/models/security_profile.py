"""Application security profile model.

A security profile is the authoritative, auditable trust record for an
application: six boolean verification signals, each worth 20 points, produce a
deterministic ``trust_score`` in [0, 100] that clients (OmniStore and future
Omni ecosystem apps) can display and filter on.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from omnisource.core.models.base import Base


class VerificationStatus(str, Enum):
    """Overall verification state of the application."""

    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


# Points awarded per verified signal; the score is the sum of the active
# signals, so it is always an integer in [0, 100].
TRUST_SIGNAL_WEIGHTS: dict[str, int] = {
    "open_source": 20,
    "github_verified": 20,
    "signature_verified": 20,
    "hash_verified": 20,
    "maintainer_verified": 20,
    # ``verification_status == VERIFIED`` is the sixth signal: the
    # organisation-level attestation that the repository and its maintainers
    # are who they claim to be.
    "org_verified": 20,
}


def compute_trust_score(
    *,
    open_source: bool,
    github_verified: bool,
    signature_verified: bool,
    hash_verified: bool,
    maintainer_verified: bool,
    org_verified: bool,
) -> int:
    """Compute the deterministic 0-100 trust score from the six signals."""
    signals = {
        "open_source": open_source,
        "github_verified": github_verified,
        "signature_verified": signature_verified,
        "hash_verified": hash_verified,
        "maintainer_verified": maintainer_verified,
        "org_verified": org_verified,
    }
    return sum(TRUST_SIGNAL_WEIGHTS[name] for name, active in signals.items() if active)


class AppSecurityProfile(Base):
    """Per-application trust and security verification profile."""

    __tablename__ = "app_security_profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    verification_status: Mapped[VerificationStatus] = mapped_column(
        SQLEnum(VerificationStatus),
        default=VerificationStatus.UNVERIFIED,
        nullable=False,
        index=True,
    )

    open_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    github_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hash_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maintainer_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    trust_score: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, index=True
    )

    # Auditing
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    calculated_by: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover
        return f"AppSecurityProfile(application_id={self.application_id!r}, trust_score={self.trust_score})"
