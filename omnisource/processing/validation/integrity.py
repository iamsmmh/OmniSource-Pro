"""Release-asset integrity verification.

Extends the checksum module with the two checks the pipeline performs on
every asset before it can leave ``pending`` status:

1. **Checksum sidecar verification** — compare the asset's digest against a
   published ``SHA256SUMS``-style file or a ``<name>.sha256`` sidecar.
2. **Signature presence** — detect ``.sig``/``.asc``/``.minisig``/``.sbom``
   companions and record signed status. (Full GPG/cosign verification
   requires external tooling and is intentionally out of scope here.)
"""

import re
from typing import Any

from omnisource.processing.validation.checksum import is_valid_hex_digest


def parse_checksum_file(content: str) -> dict[str, str]:
    """Parse a ``sha256sum``-style file into ``{filename: digest}``.

    Supports the standard ``<digest>  <filename>`` layout (two spaces),
    ``<digest> *<filename>`` (binary marker), and ``<filename>: <digest>``
    (BSD style, e.g. ``SHA256 (file) = <digest>``).
    """
    checksums: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # BSD style: SHA256 (file) = digest
        bsd = re.match(r"^(\w+)\s*\((.+)\)\s*=\s*([0-9a-fA-F]+)\s*$", line)
        if bsd:
            checksums[bsd.group(2).strip()] = bsd.group(3).lower()
            continue
        # GNU style: digest [ ]*filename
        gnu = re.match(r"^([0-9a-fA-F]{8,128})\s+\*?(.+)$", line)
        if gnu:
            checksums[gnu.group(2).strip()] = gnu.group(1).lower()
    return checksums


def verify_against_checksum_file(
    filename: str, actual_digest: str, checksum_file_content: str
) -> dict[str, Any]:
    """Verify an asset digest against a published checksum file.

    Returns ``{"verified": bool|None, "reason": str}`` where ``verified``
    is ``None`` when the file lists no entry for the asset (no information).
    """
    expected = parse_checksum_file(checksum_file_content).get(filename)
    if expected is None:
        return {"verified": None, "reason": "no_entry_in_checksum_file"}
    if not is_valid_hex_digest(actual_digest):
        return {"verified": False, "reason": "invalid_actual_digest"}
    ok = expected.lower() == actual_digest.strip().lower()
    return {
        "verified": ok,
        "reason": "checksum_match" if ok else "checksum_mismatch",
    }


SIGNATURE_SUFFIXES = (".sig", ".asc", ".minisig", ".sbom", ".pem")


def find_signature_companion(assets: list[str]) -> dict[str, str | None]:
    """Map each asset filename to its signature companion, if one exists.

    Given ``["app.dmg", "app.dmg.sig"]`` returns ``{"app.dmg": "app.dmg.sig"}``.
    """
    asset_set = {a.rsplit("/", 1)[-1] for a in assets}
    companions: dict[str, str | None] = {}
    for asset in asset_set:
        companions[asset] = None
        for suffix in SIGNATURE_SUFFIXES:
            if f"{asset}{suffix}" in asset_set:
                companions[asset] = f"{asset}{suffix}"
                break
    return companions


def evaluate_asset_integrity(
    filename: str,
    actual_sha256: str | None,
    checksum_file_content: str | None = None,
    companion_assets: list[str] | None = None,
) -> dict[str, Any]:
    """Full integrity evaluation for a single asset.

    Combines checksum-file verification with signature presence into one
    verdict used by the validation pipeline:
    ``{"status": "verified" | "signed" | "unverified" | "failed", ...}``.
    """
    result: dict[str, Any] = {
        "filename": filename,
        "checksum_verified": None,
        "signed": False,
        "signature_file": None,
        "status": "unverified",
        "reasons": [],
    }

    if checksum_file_content and actual_sha256:
        verdict = verify_against_checksum_file(filename, actual_sha256, checksum_file_content)
        result["checksum_verified"] = verdict["verified"]
        result["reasons"].append(verdict["reason"])
        if verdict["verified"] is False:
            result["status"] = "failed"
            return result

    if companion_assets:
        companions = find_signature_companion([filename, *(companion_assets or [])])
        signature_file = companions.get(filename)
        if signature_file:
            result["signed"] = True
            result["signature_file"] = signature_file
            result["reasons"].append("signature_present")

    if result["checksum_verified"] is True:
        result["status"] = "verified"
    elif result["signed"]:
        result["status"] = "signed"
    return result


__all__ = [
    "evaluate_asset_integrity",
    "find_signature_companion",
    "parse_checksum_file",
    "verify_against_checksum_file",
]
