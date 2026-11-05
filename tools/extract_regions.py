"""Decrypt assets/thing_domains_v1/regions from the APK to list per-region API hosts.

Format (see DomainHelper.parseDomainsConfig + AESCTRUtil in the APK):
  base64-decode the file -> first 32 bytes = AES-256 key, rest = payload;
  payload = 16-byte IV || ciphertext; AES-256-CTR.

Usage: python3 tools/extract_regions.py <path to assets/thing_domains_v1/regions>
"""
import base64
import json
import sys

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    def _ctr(key: bytes, iv: bytes, ct: bytes) -> bytes:
        d = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor()
        return d.update(ct) + d.finalize()

except ImportError:
    from Crypto.Cipher import AES

    def _ctr(key: bytes, iv: bytes, ct: bytes) -> bytes:
        return AES.new(key, AES.MODE_CTR, nonce=b"", initial_value=iv).decrypt(ct)


def extract(path: str):
    dec = base64.b64decode(open(path, "rb").read().strip())
    key, payload = dec[:32], dec[32:]
    plain = _ctr(key, payload[:16], payload[16:])
    return json.loads(plain.decode().replace('\\"', '"'))


if __name__ == "__main__":
    for e in extract(sys.argv[1]):
        rc = e.get("regionConfig", {})
        print(f"{e.get('region'):4} default={e.get('defaultConfig')!s:5} "
              f"{rc.get('mobileApiUrl')}")
