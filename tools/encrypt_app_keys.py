"""Encrypt app_keys.json into app_keys.enc.json with a passphrase.

Usage: python3 tools/encrypt_app_keys.py [app_keys.json] [app_keys.enc.json]

Prompts for the passphrase twice (it is never echoed or stored). Commit app_keys.enc.json;
app_keys.json stays git-ignored.
"""
import getpass
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from inverterlife.app_keys import (  # noqa: E402
    ENC_PATH, KEY_FIELDS, PLAIN_PATH, decrypt_keys, encrypt_keys,
)

src = sys.argv[1] if len(sys.argv) > 1 else PLAIN_PATH
dst = sys.argv[2] if len(sys.argv) > 2 else ENC_PATH

keys = json.load(open(src))
pw = getpass.getpass("Passphrase: ")
if not pw or pw != getpass.getpass("Repeat passphrase: "):
    sys.exit("Passphrases are empty or don't match; nothing written.")

blob = encrypt_keys(keys, pw)
if decrypt_keys(blob, pw) != {k: keys[k] for k in KEY_FIELDS}:
    sys.exit("Round-trip check failed; nothing written.")
with open(dst, "w") as f:
    json.dump(blob, f, indent=2)
    f.write("\n")
print(f"Wrote {dst}")
