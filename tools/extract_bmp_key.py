"""Extract the hidden Tuya/ThingClips signing key from an app's assets/t_s.bmp.

Port of nalajcie/tuya-sign-hacking read-keys-from-bmp (read_keys.c + coeffs_to_key.c).

Usage: python3 extract_bmp_key.py <t_s.bmp> <appKey>
"""
import struct
import sys
from fractions import Fraction


def java_hash(s: str) -> int:
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h - (1 << 32) if h & 0x80000000 else h


def be32(px: bytes, off: int) -> int:
    n = len(px)
    v = (px[off % n] << 24) | (px[(off + 1) % n] << 16) | (px[(off + 2) % n] << 8) | px[(off + 3) % n]
    return v - (1 << 32) if v & 0x80000000 else v


def hexrun(px: bytes, length: int, off: int) -> str:
    n = len(px)
    return "".join(f"{px[(off + i) % n]:02x}" for i in range(length))


def read_records(px: bytes, app_key: str):
    n = len(px)
    h = abs(java_hash(app_key))
    h = (h % n) // 2
    keys_cnt = px[(h + 1) % n]
    coeffs_cnt = px[(h + 2) % n]
    offs = h ^ be32(px, h + 3)
    records = []
    for _ in range(keys_cnt * coeffs_cnt):
        v1_off = offs % n
        v1_len = px[v1_off]
        a = hexrun(px, v1_len, v1_off + 1)
        v2_off = (v1_off + v1_len + 1) % n
        v2_len = px[v2_off]
        b = hexrun(px, v2_len, v2_off + 1)
        nxt = be32(px, (v2_off + v2_len + 1) % n)
        offs = v1_off ^ nxt
        if offs < 0:  # C does uint32 modulo on the next read
            offs &= 0xFFFFFFFF
        records.append((int(a, 16), int(b, 16)))
    return keys_cnt, coeffs_cnt, records


def constant_term(points):
    """Constant term of the polynomial through `points` (Lagrange at x=0)."""
    total = Fraction(0)
    for i, (xi, yi) in enumerate(points):
        term = Fraction(yi)
        for j, (xj, _) in enumerate(points):
            if i != j:
                term *= Fraction(-xj, xi - xj)
        total += term
    if total.denominator != 1:
        raise ValueError("non-integer key; decoding is wrong")
    return int(total)


def int_to_ascii(v: int) -> str:
    raw = v.to_bytes((v.bit_length() + 7) // 8, "big")
    return raw.decode("ascii")


def extract(bmp_path: str, app_key: str):
    data = open(bmp_path, "rb").read()
    pix_off = struct.unpack("<I", data[10:14])[0]
    px = data[pix_off:]
    keys_cnt, coeffs_cnt, recs = read_records(px, app_key)
    if not (1 <= keys_cnt <= 4) or coeffs_cnt == 0:
        raise ValueError(f"bad header keys_cnt={keys_cnt} coeffs_cnt={coeffs_cnt}; wrong appKey?")
    return [int_to_ascii(constant_term(recs[k * coeffs_cnt:(k + 1) * coeffs_cnt])) for k in range(keys_cnt)]


if __name__ == "__main__":
    for key in extract(sys.argv[1], sys.argv[2]):
        print(key)
