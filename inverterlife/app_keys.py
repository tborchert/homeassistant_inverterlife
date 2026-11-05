"""Passphrase-protected storage for the app keys extracted from the InverterLife APK.

The repo ships app_keys.enc.json: the four keys encrypted with AES-256-GCM under a key derived
from a passphrase with scrypt. The integration asks the user for the passphrase.

This keeps the keys out of plain text in the repo (no scanner or casual reader finds them).
Anyone who has the passphrase can recover them.

Lookup order in load_app_keys():
1. $INVERTERLIFE_KEYS or app_keys.json: plain local file, git-ignored (development)
2. app_keys.enc.json + passphrase
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    def _encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        return AESGCM(key).encrypt(nonce, data, None)

    def _decrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        return AESGCM(key).decrypt(nonce, data, None)

except ImportError:  # pragma: no cover - fallback for dev machines
    from Crypto.Cipher import AES

    def _encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        ct, tag = AES.new(key, AES.MODE_GCM, nonce=nonce).encrypt_and_digest(data)
        return ct + tag

    def _decrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(data[:-16], data[-16:])


KEY_FIELDS = ("app_key", "app_secret", "bmp_key", "cert_sha256")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAIN_PATH = os.path.join(ROOT, "app_keys.json")
ENC_PATH = os.path.join(ROOT, "app_keys.enc.json")

# scrypt cost: 2^15 x 8 uses ~32 MB and takes well under a second, even on a Raspberry Pi.
_N, _R, _P = 2**15, 8, 1


class BadPassphrase(Exception):
    pass


def _derive(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(passphrase.encode(), salt=salt, n=n, r=r, p=p,
                          maxmem=128 * n * r * 2, dklen=32)


def _check(keys: dict, source: str) -> dict:
    missing = [k for k in KEY_FIELDS if not keys.get(k)]
    if missing:
        raise RuntimeError(f"{source} is missing: {', '.join(missing)}")
    return {k: keys[k] for k in KEY_FIELDS}


def encrypt_keys(keys: dict, passphrase: str) -> dict:
    keys = _check(keys, "keys")
    salt, nonce = os.urandom(16), os.urandom(12)
    ct = _encrypt(_derive(passphrase, salt, _N, _R, _P), nonce, json.dumps(keys).encode())
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return {"v": 1, "kdf": "scrypt", "n": _N, "r": _R, "p": _P,
            "salt": b64(salt), "nonce": b64(nonce), "ct": b64(ct)}


def decrypt_keys(blob: dict, passphrase: str) -> dict:
    if blob.get("v") != 1 or blob.get("kdf") != "scrypt":
        raise RuntimeError("unsupported app_keys.enc.json format")
    salt, nonce, ct = (base64.b64decode(blob[k]) for k in ("salt", "nonce", "ct"))
    key = _derive(passphrase, salt, blob["n"], blob["r"], blob["p"])
    try:
        plain = _decrypt(key, nonce, ct)
    except Exception:  # GCM tag mismatch
        raise BadPassphrase("wrong passphrase for app_keys.enc.json") from None
    return _check(json.loads(plain), "app_keys.enc.json")


def load_app_keys(passphrase: str | None = None, path: str | None = None) -> dict:
    plain = path or os.environ.get("INVERTERLIFE_KEYS") or PLAIN_PATH
    if os.path.exists(plain):
        with open(plain) as f:
            return _check(json.load(f), plain)
    if not os.path.exists(ENC_PATH):
        raise RuntimeError(f"no app keys: neither {plain} nor {ENC_PATH} exists")
    if not passphrase:
        raise BadPassphrase("a passphrase is needed to unlock app_keys.enc.json")
    with open(ENC_PATH) as f:
        return decrypt_keys(json.load(f), passphrase)
