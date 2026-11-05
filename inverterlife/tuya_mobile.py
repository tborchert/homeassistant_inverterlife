"""Read-only client for the InverterLife app's cloud API (Tuya/ThingClips mobile API, et=3).

Reimplemented from the decompiled com.InverterLife 1.1.6 APK. See FINDINGS.md.

Safety: only actions in READ_ONLY_ACTIONS can be sent. Anything else raises before a
request is built, so this client cannot change device or account settings.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import uuid

try:  # Home Assistant ships `cryptography`
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    def _gcm_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        return AESGCM(key).encrypt(nonce, data, None)  # ciphertext || tag

    def _gcm_decrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        return AESGCM(key).decrypt(nonce, data, None)

except ImportError:  # pragma: no cover - fallback for dev machines
    from Crypto.Cipher import AES

    def _gcm_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        ct, tag = AES.new(key, AES.MODE_GCM, nonce=nonce).encrypt_and_digest(data)
        return ct + tag

    def _gcm_decrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(data[:-16], data[-16:])


# --- App keys (extracted from the APK; kept out of the repo) ------------------------------
# Loaded from app_keys.json next to the project root (git-ignored), or from the path in
# $INVERTERLIFE_KEYS. See app_keys.example.json and FINDINGS.md for how to extract them.
KEY_FIELDS = ("app_key", "app_secret", "bmp_key", "cert_sha256")


def load_app_keys(path: str | None = None) -> dict:
    path = path or os.environ.get("INVERTERLIFE_KEYS") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_keys.json")
    try:
        with open(path) as f:
            keys = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"App keys file not found: {path} (see app_keys.example.json)") from None
    missing = [k for k in KEY_FIELDS if not keys.get(k)]
    if missing:
        raise RuntimeError(f"{path} is missing: {', '.join(missing)}")
    return keys


TTID = "smarterpool"
APP_VERSION = "1.1.6"

REGION_HOSTS = {
    "EU": "https://a1.tuyaeu.com/api.json",
    "US": "https://a1.tuyaus.com/api.json",
    "IN": "https://a1.tuyain.com/api.json",
    "CN": "https://a1.tuyacn.com/api.json",
}

# Only these may be sent. Login actions are included because they're needed to read anything.
READ_ONLY_ACTIONS = {
    "thing.m.country.list",
    "thing.m.user.username.token.get",
    "thing.m.user.email.password.login",
    "thing.m.location.list",
    "thing.m.my.group.device.list",
    "thing.m.device.get",
    "thing.m.device.dp.get",
    "thing.m.device.ref.info.list",
}

SIGN_KEYS = {
    "a", "v", "lat", "lon", "lang", "deviceId", "appVersion", "ttid", "isH5", "h5Token", "os",
    "clientId", "postData", "time", "requestId", "et", "n4h5", "sid", "chKey", "sp",
}


class TuyaApiError(Exception):
    def __init__(self, code: str, msg: str, raw: dict):
        super().__init__(f"{code}: {msg}")
        self.code, self.raw = code, raw


def hmac_key(keys: dict) -> str:
    return f"{keys['cert_sha256']}_{keys['bmp_key']}_{keys['app_secret']}"


def _swap_md5(s: str) -> str:
    h = hashlib.md5(s.encode()).hexdigest()
    return h[8:16] + h[0:8] + h[24:32] + h[16:24]


def sign(params: dict, key: str) -> str:
    parts = []
    for k in sorted(params):
        v = params[k]
        if k not in SIGN_KEYS or v in (None, ""):
            continue
        v = str(v)
        if k == "postData":
            v = _swap_md5(v)
        parts.append(f"{k}={v}")
    return hmac.new(key.encode(), "||".join(parts).encode(), hashlib.sha256).hexdigest()


def aes_key(request_id: str, ecode: str | None, key: str) -> bytes:
    msg = key + (f"_{ecode}" if ecode else "")
    return hmac.new(request_id.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16].encode()


def encrypt_post(data: dict, key: bytes) -> str:
    nonce = os.urandom(12)
    body = json.dumps(data, separators=(",", ":")).encode()
    return base64.b64encode(nonce + _gcm_encrypt(key, nonce, body)).decode()


def decrypt_result(result: str, key: bytes):
    raw = base64.b64decode(result)
    plain = _gcm_decrypt(key, raw[:12], raw[12:])
    if plain[:2] == b"\x1f\x8b":
        plain = gzip.decompress(plain)
    return json.loads(plain)


def _rsa_encrypt_pkcs1(modulus: int, exponent: int, data: bytes) -> str:
    k = (modulus.bit_length() + 7) // 8
    pad_len = k - 3 - len(data)
    pad = bytearray()
    while len(pad) < pad_len:
        b = secrets.token_bytes(1)
        if b != b"\x00":
            pad += b
    em = b"\x00\x02" + bytes(pad) + b"\x00" + data
    return pow(int.from_bytes(em, "big"), exponent, modulus).to_bytes(k, "big").hex()


class InverterLifeClient:
    def __init__(self, region: str = "EU", country_code: str = "49", lang: str = "en",
                 device_id: str | None = None, keys: dict | None = None):
        self.keys = keys or load_app_keys()
        self._hmac_key = hmac_key(self.keys)
        self.url = REGION_HOSTS[region]
        self.country_code = country_code
        self.lang = lang
        self.device_id = device_id or secrets.token_hex(22)
        self.sid: str | None = None
        self.ecode: str | None = None

    def request(self, action: str, version: str, post: dict | None = None,
                session: bool = True):
        if action not in READ_ONLY_ACTIONS:
            raise PermissionError(f"{action} is not an allowed read-only action")
        request_id = str(uuid.uuid4())
        key = aes_key(request_id, self.ecode if session else None, self._hmac_key)
        params = {
            "a": action, "v": version, "clientId": self.keys["app_key"], "os": "Android",
            "lang": self.lang, "deviceId": self.device_id, "appVersion": APP_VERSION,
            "ttid": TTID, "time": str(int(time.time())), "requestId": request_id,
            "et": "3", "cp": "gzip", "osSystem": "14", "platform": "Pixel 7",
            "timeZoneId": "Europe/Berlin",
        }
        if session and self.sid:
            params["sid"] = self.sid
        body = {}
        if post:
            params["postData"] = encrypt_post(post, key)
            body["postData"] = params["postData"]
        params["sign"] = sign(params, self._hmac_key)
        query = {k: v for k, v in params.items() if k != "postData"}
        req = urllib.request.Request(
            self.url + "?" + urllib.parse.urlencode(query),
            data=urllib.parse.urlencode(body).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": f"Thing-UA=APP/Android/{APP_VERSION}/SDK/null"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        if not data.get("success", False):
            raise TuyaApiError(data.get("errorCode", "?"), data.get("errorMsg", ""), data)
        result = data.get("result")
        if isinstance(result, str):
            result = decrypt_result(result, key)
        return result

    # --- Auth ---------------------------------------------------------------------------------
    def login(self, email: str, password: str) -> dict:
        tok = self.request("thing.m.user.username.token.get", "2.0",
                           {"countryCode": self.country_code, "username": email, "isUid": False},
                           session=False)
        pw_md5 = hashlib.md5(password.encode()).hexdigest()
        enc = _rsa_encrypt_pkcs1(int(tok["publicKey"]), int(tok["exponent"]), pw_md5.encode())
        user = self.request("thing.m.user.email.password.login", "3.0", {
            "countryCode": self.country_code, "email": email, "passwd": enc,
            "options": '{"group": 1,"mfaCode": "null"}', "token": tok["token"], "ifencrypt": 1,
        }, session=False)
        self.sid, self.ecode = user["sid"], user.get("ecode")
        return user

    # --- Reads --------------------------------------------------------------------------------
    def homes(self):
        return self.request("thing.m.location.list", "2.1")

    def devices(self, gid: int):
        return self.request("thing.m.my.group.device.list", "2.1", {"gid": gid})

    def device(self, dev_id: str):
        return self.request("thing.m.device.get", "1.0", {"devId": dev_id})

    def dps(self, dev_id: str):
        return self.request("thing.m.device.dp.get", "1.0", {"devId": dev_id})
