"""Smoke test: one signed, no-login, read-only request (thing.m.country.list).

Success prints the country list, which means signing and decryption work.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inverterlife.tuya_mobile import InverterLifeClient, TuyaApiError  # noqa: E402

c = InverterLifeClient("EU")
try:
    r = c.request("thing.m.country.list", "3.0", session=False)
    print("OK", type(r).__name__, json.dumps(r)[:400])
except TuyaApiError as e:
    print("API ERROR", e, json.dumps(e.raw)[:400])
