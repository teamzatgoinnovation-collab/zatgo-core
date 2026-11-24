"""Ed25519 signing and verification for ZatGo licences (docs/licensing.md, Phase 5).

- **Public keys** that sites trust ship in code: `licensing/keys/public_keys.json` ({key_id: base64 raw public
  key}). Nothing on a site (database, site_config) can add a trusted key -- a customer who controls the site
  must not be able to trust their own key. A key id is the first 16 hex characters of SHA-256(raw public key),
  so a licence names the key that signed it and keys can be rotated by adding a new one.
- **The private key** exists only on the issuer host, in a file outside the bench's `sites/` folder (decision
  D2): never in a site database, a backup, this repository or a licence file. `load_private_key` refuses a key
  file inside `sites/` or readable by group / others.

Pure Python + `cryptography` (already a Frappe dependency): no frappe import, so the unit tests and the
key-generation script use it directly.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

KEYS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys", "public_keys.json")

# Tests install their own throwaway keys here (Python only; nothing a request can reach).
_extra_trusted: dict[str, str] = {}


class KeyError_(Exception):
    """A key problem (unknown key, unsafe private key file). Named apart from the builtin KeyError."""


def b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def raw_public(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id(public_key: Ed25519PublicKey | bytes) -> str:
    raw = public_key if isinstance(public_key, bytes) else raw_public(public_key)
    return hashlib.sha256(raw).hexdigest()[:16]


# -- trusted public keys ------------------------------------------------------------------------------------------

def shipped_keys() -> dict[str, str]:
    try:
        with open(KEYS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (data.get("keys") or {}).items() if isinstance(v, str)}


def trusted_keys() -> dict[str, str]:
    return {**shipped_keys(), **_extra_trusted}


def trust_for_tests(keys: Mapping[str, str] | None) -> None:
    """Replace the test-only trusted keys (None clears them)."""
    _extra_trusted.clear()
    if keys:
        _extra_trusted.update(keys)


def public_key_for(kid: str) -> Ed25519PublicKey:
    raw_b64 = trusted_keys().get(kid)
    if not raw_b64:
        raise KeyError_(f"the licence was signed with key {kid!r}, which this ZatGo version does not trust")
    raw = b64d(raw_b64)
    if key_id(raw) != kid:
        raise KeyError_(f"trusted key {kid!r} does not match its id")
    return Ed25519PublicKey.from_public_bytes(raw)


# -- sign / verify --------------------------------------------------------------------------------------------

def sign(private_key: Ed25519PrivateKey, message: bytes) -> bytes:
    return private_key.sign(message)


def verify(kid: str, message: bytes, signature: bytes) -> bool:
    """True when `signature` is a valid signature of `message` by trusted key `kid`. Raises KeyError_ for an
    untrusted key id; any other failure is False."""
    public_key = public_key_for(kid)
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False


# -- the issuer's private key --------------------------------------------------------------------------------

def generate_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_pem(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def write_private_key(private_key: Ed25519PrivateKey, path: str) -> None:
    """Write a new key file readable by its owner only. Never overwrites."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(private_pem(private_key))


def check_key_location(path: str, sites_dir: str | None) -> None:
    """Refuse a private key kept where backups or other users can reach it."""
    real = os.path.realpath(path)
    if sites_dir:
        sites = os.path.realpath(sites_dir)
        if real == sites or real.startswith(sites + os.sep):
            raise KeyError_("the licence signing key must not be inside the bench's sites/ folder (backups copy it)")
    try:
        mode = os.stat(real).st_mode
    except OSError as exc:
        raise KeyError_(f"cannot read the licence signing key: {exc.strerror}") from None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise KeyError_("the licence signing key file must be readable by its owner only (chmod 600)")


def load_private_key(path: str, sites_dir: str | None = None) -> Ed25519PrivateKey:
    check_key_location(path, sites_dir)
    with open(path, "rb") as fh:
        key = serialization.load_pem_private_key(fh.read(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise KeyError_("the licence signing key is not an Ed25519 key")
    return key
