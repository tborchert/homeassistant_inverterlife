"""Find which Tuya cluster this app's appKey is registered on.

Sends the no-login, read-only thing.m.country.list to each candidate host and prints the
result. ILLEGAL_CLIENT_ID means wrong cluster; anything else (success, or a sign/param error)
means the appKey IS recognised there, so that's the host to use.

Usage: python3 tools/probe_hosts.py [extra-host ...]
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inverterlife.tuya_mobile import InverterLifeClient, TuyaApiError  # noqa: E402

HOSTS = [
    "a1.tuyaeu.com",
    "a1-eu.iotbing.com",
    "a1-us.iotbing.com",
    "a1-in.iotbing.com",
    "a1.iot334.com",
    "a1-ueaz.iotbing.com",
] + sys.argv[1:]

for host in HOSTS:
    try:
        c = InverterLifeClient(host=host)
        r = c.request("thing.m.country.list", "3.0", session=False)
        print(f"{host:28} OK  ({len(r) if hasattr(r, '__len__') else type(r).__name__})")
    except TuyaApiError as e:
        verdict = "wrong cluster" if e.code == "ILLEGAL_CLIENT_ID" else "APPKEY OK, other error"
        print(f"{host:28} {e.code}  <- {verdict}")
    except Exception as e:  # network/TLS/decrypt
        print(f"{host:28} {type(e).__name__}: {str(e)[:60]}")
