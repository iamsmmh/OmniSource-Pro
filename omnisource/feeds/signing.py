"""Canonical Ed25519 signing and verification for published feed envelopes."""

import base64
import hashlib
import hmac
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from omnisource.config.settings import get_settings


class FeedSignatureError(ValueError):
    """Raised when signing material or a feed signature is invalid."""


def canonical_json(value: dict[str, Any]) -> bytes:
    """Serialize a feed deterministically for hashing and signing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


class FeedSigner:
    """Ed25519 feed signer loaded exclusively from configuration.

    ``FEED_SIGNING_PRIVATE_KEY`` accepts a PEM private key or a base64 encoded
    32-byte Ed25519 seed. Production refuses ephemeral keys. Development may
    opt into an ephemeral process-local key for local experimentation only.
    """

    def __init__(
        self,
        private_key: str | None = None,
        public_key: str | None = None,
        allow_ephemeral: bool | None = None,
    ) -> None:
        settings = get_settings()
        private_key = (
            private_key if private_key is not None else settings.feeds.FEED_SIGNING_PRIVATE_KEY
        )
        public_key = (
            public_key if public_key is not None else settings.feeds.FEED_SIGNING_PUBLIC_KEY
        )
        allow_ephemeral = (
            allow_ephemeral
            if allow_ephemeral is not None
            else settings.feeds.FEED_ALLOW_EPHEMERAL_SIGNING and settings.APP_ENV != "production"
        )
        self._private = self._load_private(private_key, allow_ephemeral)
        self._public = self._load_public(public_key) if public_key else self._private.public_key()

    @staticmethod
    def _load_private(value: str | None, allow_ephemeral: bool) -> Ed25519PrivateKey:
        if not value:
            if allow_ephemeral:
                return Ed25519PrivateKey.generate()
            raise FeedSignatureError("FEED_SIGNING_PRIVATE_KEY is required outside development")
        raw = value.strip().encode("utf-8")
        try:
            if b"BEGIN" in raw:
                loaded = serialization.load_pem_private_key(raw, password=None)
                if isinstance(loaded, Ed25519PrivateKey):
                    return loaded
                raise FeedSignatureError("feed signing key is not an Ed25519 private key")
            decoded = base64.b64decode(raw, validate=True)
            return Ed25519PrivateKey.from_private_bytes(decoded)
        except (ValueError, TypeError) as exc:
            raise FeedSignatureError("invalid FEED_SIGNING_PRIVATE_KEY") from exc

    @staticmethod
    def _load_public(value: str) -> Ed25519PublicKey:
        raw = value.strip().encode("utf-8")
        try:
            if b"BEGIN" in raw:
                loaded = serialization.load_pem_public_key(raw)
                if isinstance(loaded, Ed25519PublicKey):
                    return loaded
                raise FeedSignatureError("feed signing key is not an Ed25519 public key")
            return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw, validate=True))
        except (ValueError, TypeError) as exc:
            raise FeedSignatureError("invalid FEED_SIGNING_PUBLIC_KEY") from exc

    @property
    def public_key_base64(self) -> str:
        """The raw Ed25519 public key, suitable for client verification."""
        raw = self._public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    def sign(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Return a signed copy of an unsigned envelope."""
        unsigned = {
            key: value for key, value in envelope.items() if key not in {"sha256", "signature"}
        }
        digest = hashlib.sha256(canonical_json(unsigned)).hexdigest()
        signed_payload = {**unsigned, "sha256": digest}
        signature = base64.b64encode(self._private.sign(canonical_json(signed_payload))).decode(
            "ascii"
        )
        return {**signed_payload, "signature": signature}

    def verify(self, envelope: dict[str, Any]) -> bool:
        """Validate a feed using this signer's configured/public verification key."""
        return verify_signed_envelope(envelope, public_key=self.public_key_base64)


def verify_signed_envelope(envelope: dict[str, Any], public_key: str | None = None) -> bool:
    """Verify a signed feed using an explicitly supplied or embedded public key.

    Consumers should pin an expected key rather than relying solely on the
    embedded key. The embedded key is used by the publisher's post-write
    validation and local development tooling.
    """
    signature = envelope.get("signature")
    expected_digest = envelope.get("sha256")
    encoded_public_key = public_key or envelope.get("signing_key")
    if not all(
        isinstance(value, str) for value in (signature, expected_digest, encoded_public_key)
    ):
        return False
    signature_text = str(signature)
    digest_text = str(expected_digest)
    public_key_text = str(encoded_public_key)
    unsigned = {key: value for key, value in envelope.items() if key not in {"sha256", "signature"}}
    actual_digest = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    if not hmac.compare_digest(actual_digest, digest_text.lower()):
        return False
    signed_payload = {**unsigned, "sha256": digest_text}
    try:
        verifier = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_text, validate=True)
        )
        verifier.verify(
            base64.b64decode(signature_text, validate=True), canonical_json(signed_payload)
        )
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


__all__ = ["FeedSignatureError", "FeedSigner", "canonical_json", "verify_signed_envelope"]
