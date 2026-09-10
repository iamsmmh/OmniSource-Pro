"""Checksum computation and verification utilities."""

import hashlib


def hash_bytes(data: bytes, algorithm: str = "sha256") -> str:
    """Hash bytes using the given algorithm, returning a hex digest."""
    h = hashlib.new(algorithm)
    h.update(data)
    return h.hexdigest()


def compute_sha256(data: bytes) -> str:
    """Compute the SHA-256 hex digest of bytes."""
    return hash_bytes(data, "sha256")


def compute_sha512(data: bytes) -> str:
    """Compute the SHA-512 hex digest of bytes."""
    return hash_bytes(data, "sha512")


def verify_checksum(data: bytes, expected: str, algorithm: str = "sha256") -> bool:
    """Verify bytes against an expected hex digest (case-insensitive)."""
    if not expected:
        return False
    actual = hash_bytes(data, algorithm)
    return actual.lower() == expected.strip().lower()


def is_valid_hex_digest(value: str | None, algorithm: str = "sha256") -> bool:
    """Check whether a string looks like a valid hex digest for an algorithm."""
    if not value:
        return False
    lengths = {"md5": 32, "sha256": 64, "sha512": 128}
    expected_length = lengths.get(algorithm)
    if expected_length is None:
        return False
    value = value.strip()
    if len(value) != expected_length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
