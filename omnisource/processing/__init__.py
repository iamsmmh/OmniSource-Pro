"""Data processing pipeline for OmniSource."""

from omnisource.processing.architecture_detector import (
    detect_architecture,
    normalize_architecture,
)
from omnisource.processing.license_engine import (
    LicenseEngine,
    classify_license,
    normalize_license,
)
from omnisource.processing.metadata_extractor import MetadataExtractor
from omnisource.processing.platform_detector import (
    detect_package_type,
    detect_platform,
)

__all__ = [
    "detect_architecture",
    "normalize_architecture",
    "detect_platform",
    "detect_package_type",
    "LicenseEngine",
    "classify_license",
    "normalize_license",
    "MetadataExtractor",
]
