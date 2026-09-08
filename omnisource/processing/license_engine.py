"""License detection and normalization engine."""

from typing import Dict, Optional, Tuple

# Common license identifiers normalized to SPDX ids.
_LICENSE_ALIASES: Dict[str, str] = {
    "mit": "MIT",
    "mit license": "MIT",
    "apache": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "gpl": "GPL-3.0",
    "gpl2": "GPL-2.0",
    "gpl-2.0": "GPL-2.0",
    "gpl3": "GPL-3.0",
    "gpl-3.0": "GPL-3.0",
    "gplv2": "GPL-2.0",
    "gplv3": "GPL-3.0",
    "lgpl": "LGPL-3.0",
    "lgpl-2.1": "LGPL-2.1",
    "lgpl-3.0": "LGPL-3.0",
    "agpl": "AGPL-3.0",
    "agpl-3.0": "AGPL-3.0",
    "bsd": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd3": "BSD-3-Clause",
    "mpl": "MPL-2.0",
    "mpl-2.0": "MPL-2.0",
    "isc": "ISC",
    "unlicense": "Unlicense",
    "zlib": "Zlib",
    "wtfpl": "WTFPL",
    "cc0": "CC0-1.0",
    "cc0-1.0": "CC0-1.0",
    "apache 2.0 with llvm exception": "Apache-2.0",
    "no license": None,
    "none": None,
    "other": "LicenseRef-Other",
}

# Licenses considered open source (OSI-approved or broadly accepted).
_OPEN_SOURCE_LICENSES = {
    "MIT",
    "Apache-2.0",
    "GPL-2.0",
    "GPL-3.0",
    "LGPL-2.1",
    "LGPL-3.0",
    "AGPL-3.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD-4-Clause",
    "MPL-2.0",
    "ISC",
    "Unlicense",
    "Zlib",
    "WTFPL",
    "CC0-1.0",
    "EPL-1.0",
    "EPL-2.0",
    "0BSD",
    "BlueOak-1.0.0",
    "PostgreSQL",
    "Python-2.0",
    "OFL-1.1",
}


def normalize_license(value: Optional[str]) -> Optional[str]:
    """Normalize a license string to an SPDX identifier if possible."""
    if not value:
        return None

    key = value.strip().lower()
    if key in _LICENSE_ALIASES:
        return _LICENSE_ALIASES[key]

    # Fall back to the raw value if it already looks like an SPDX id.
    if "-" in value and not any(c in value for c in (" ", "\n")):
        return value.strip()

    # Return an opaque license reference for unknown strings.
    return f"LicenseRef-{value.strip().replace(' ', '-')[:50]}"


def classify_license(value: Optional[str]) -> Tuple[Optional[str], bool]:
    """Return (spdx_id, is_open_source) for a license string."""
    spdx = normalize_license(value)
    if spdx is None:
        return None, False
    is_open = spdx in _OPEN_SOURCE_LICENSES or spdx.startswith("LicenseRef-")
    # Unknown custom licenses are conservatively treated as not-open unless recognized.
    if spdx.startswith("LicenseRef-"):
        is_open = False
    return spdx, is_open


class LicenseEngine:
    """Stateless license normalization helper."""

    def normalize(self, value: Optional[str]) -> Optional[str]:
        return normalize_license(value)

    def classify(self, value: Optional[str]) -> Tuple[Optional[str], bool]:
        return classify_license(value)

    @property
    def open_source_licenses(self) -> set:
        return set(_OPEN_SOURCE_LICENSES)
