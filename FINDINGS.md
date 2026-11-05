# InverterLife app — API / auth findings

> **This cloud-clone route is stalled on native crypto — prefer one of the alternatives.**
> The device is a Fairland AquaX 20 (FAI-150-0017) pool heat pump.
> - **[REPAIRING.md](REPAIRING.md)** — re-pair into Smart Life, then HA Tuya Local/cloud. No
>   opening the unit, no rooting. Best fit if you only have the control panel.
> - **[MODBUS.md](MODBUS.md)** — read the RS485 bus directly. Fully local and robust, but needs
>   opening the unit.
> - This cloud clone stalled on native `chKey`/sign/AES in `libthing_security.so` (needs a
>   rooted/arm64 Android env to capture — see [FRIDA.md](FRIDA.md)).


App: `com.InverterLife` v1.1.6 (base.apk + split_config.arm64_v8a.apk)

## Summary

InverterLife is a **white-label Tuya app**. Tuya built it from their OEM SDK, renamed
"ThingClips" (`com.thingclips.*`), and signed it with Tuya's own certificate. The inverter's
Wi-Fi dongle is a standard Tuya device. The app talks to Tuya's mobile API; there is no
InverterLife-specific backend.

## App keys

The four values the client needs are never committed in plain text.

- **Repo:** `app_keys.enc.json`, encrypted with AES-256-GCM using a key derived from a passphrase
  with scrypt (N=2^15, r=8). The integration asks the user for the passphrase:
  `InverterLifeClient(passphrase=...)`. A wrong passphrase raises `BadPassphrase`.
- **Development:** a plain, git-ignored `app_keys.json` (format: `app_keys.example.json`) takes
  precedence when it exists.
- **Create or update the encrypted file:** `python3 tools/encrypt_app_keys.py`, which prompts for
  the passphrase.

This keeps the keys away from secret scanners and casual readers. Anyone who has the passphrase
can recover them.

To extract the keys from the APK (`base.apk`, InverterLife 1.1.6):

| Field | How to get it |
|---|---|
| `app_key` | Decompile with jadx; `THING_SMART_APPKEY` in `com/thingclips/sample/BuildConfig.java` |
| `app_secret` | `THING_SMART_SECRET` in the same file |
| `cert_sha256` | `keytool -printcert -jarfile base.apk`: the SHA256 line (uppercase hex with colons; the cert is CN=www.tuya.com) |
| `bmp_key` | `unzip base.apk assets/t_s.bmp`, then `python3 tools/extract_bmp_key.py assets/t_s.bmp <app_key>` |

## Request format

- Endpoint: `POST https://a1.tuya{us,eu,cn,in}.com/api.json` (region depends on the account)
- Query params: `a` (action, e.g. `thing.m.user.email.password.login`), `v`, `clientId`,
  `os=Android`, `lang`, `deviceId`, `appVersion`, `ttid`, `time` (unix secs), `requestId` (UUID),
  `et=3`, `sid` (session id after login), `sign`
- Body: `postData=<json>`, **encrypted** because `et=3`

### Signature (`com/thingclips/sdk/network/ThingApiSignManager.java`)

1. Take only these param keys: `a v lat lon lang deviceId appVersion ttid isH5 h5Token os clientId
   postData time requestId et n4h5 sid chKey sp`. Drop any that are empty.
2. Sort the keys, then join them as `key=value` pairs separated by `||`.
3. Before joining, replace `postData`'s value with `swapSignString(md5AsBase64(postData))`.
4. `sign` = HMAC-SHA256 over that string. The HMAC is computed in native code
   (`SecureNativeApi.computeDigest`) with key `"{certSHA256}_{bmpKey}_{appSecret}"`. This is
   the community-documented Tuya scheme and still needs confirming against a live request.

### Encryption (`et=3`)

`ThingApiParams` sets `ET_VERSION = "3"`. Request bodies and responses are AES-GCM encrypted,
with a key derived from `requestId` plus the session's `ecode`
(`ThingNetworkSecurity.getEncryptoKey`).

## Still unknown

- Which data points (DPs) the inverter reports.

## Local network check (2026-11-05)

Scanned from 192.168.178.33 (Fritz!Box LAN 192.168.178.0/24):

- No Tuya UDP discovery broadcasts were heard. Sending the v3.5 broadcast on :7000 failed with
  "No route to host", probably because of the shell sandbox; the TCP scan below doesn't depend on it.
- **No host accepts connections on TCP 6668**, the port every LAN-capable Tuya device listens on.
- Twelve live hosts. The only HTTP ones (.124, .182) are internet radios. Nothing on 502 (Modbus TCP)
  or 8899 (Solarman).

So the inverter's dongle is either on a different network (guest Wi-Fi or VLAN), offline, or a
cloud-only Tuya module that doesn't expose the local protocol.

## Cloud scheme details (from public reverse-engineering; still to verify for this app)

Sources: github.com/nalajcie/tuya-sign-hacking, gist.github.com/bahorn/9bebbbf37c2167f7057aea0244ff2d92

- BMP key: skip the 54-byte BMP header and treat the pixel bytes as a circular array of length L.
  `h = javaHash(appKey)`, `h = (abs(h) % L) / 2`. Read a count and a magic value at h+1..h+6, then
  walk a linked list of `(len,a)(len,b)(next)` records. The key is the constant term of the
  polynomial interpolated through the (a,b) points.
- Sign: `postData` is replaced by `md5hex[8:16]+[0:8]+[24:32]+[16:24]` of the *encrypted*
  postData; `sign = HMAC-SHA256(key="{CERT:SHA256 upper, colons}_{bmpKey}_{appSecret}", msg="k=v||k=v…")`.
- et=3 AES key: `HMAC-SHA256(key=requestId, msg="{cert}_{bmpKey}_{appSecret}_{ecode}").hex()[:16]`
  is used as an ASCII AES-128-GCM key. postData = base64(nonce12 ‖ ciphertext ‖ tag16); responses
  use the same format.
- Login: password-login with an RSA-encrypted MD5(password), using a key from a prior token call.
  `ecode` and `sid` come from the login response.

## Native wall (current blocker)

`tools/probe_hosts.py` returns `ILLEGAL_CLIENT_ID` on **every** cluster (tuyaeu, all iotbing, iot334).
The appKey isn't rejected for the region — it isn't accepted anywhere — so the request is missing
something the server uses to identify the client. The likely cause is `chKey`, a channel key the
real app attaches to every request, which this client doesn't send.

Four things are computed in `libthing_security.so` and cannot be reproduced from static analysis:

| native (SecureNativeApi) | used for | client currently |
|---|---|---|
| `getChKey(ctx, appKey)` | per-request `chKey` client id | **omitted** — probable cause of ILLEGAL_CLIENT_ID |
| `computeDigest(signStr, ?)` | request `sign` | guessed HMAC key format from a public gist; unverified |
| `getEncryptoKey(reqId, ecode)` | per-request AES key | guessed HMAC→hex[:16] from the gist; unverified |
| `decryptResponseData` | response decrypt | guessed (same key); unverified |

The app also pins TLS (`assets/thing_domains_v1/pins`, `h2.ca.der`), so a plain proxy can't read
traffic.

### Plan: capture the real values with Frida

`tools/frida_hook_security.js` hooks the Java wrappers of those native calls and logs their inputs
and outputs. On a rooted device or emulator with frida-server:

```
frida -U -f com.InverterLife -l tools/frida_hook_security.js
```

Log in and open the inverter in the app, then read off: the real `chKey`, the exact `signString`
that `computeDigest` receives (confirms the sign param list/order/key), and real
`requestId → AES key` pairs (confirms `getEncryptoKey`). Those let us correct the client. If `chKey`
turns out device-specific, the cloud reimplementation may not be portable and local/Smart-Life
re-pairing (see below) becomes the better route.

## Client status

- `tools/extract_bmp_key.py` decodes the BMP key (a 32-character string like the app secret).
- `inverterlife/tuya_mobile.py` is a read-only client. It implements signing, et=3 AES-GCM, and
  RSA+MD5 password login (`thing.m.user.username.token.get` v2.0, then
  `thing.m.user.email.password.login` v3.0). Calls outside `READ_ONLY_ACTIONS` raise
  `PermissionError`.
- The Java side was checked against the decompiled code: sign key list, `||` and `=` separators,
  MD5 swap, lowercase hex, nonce‖ciphertext‖tag layout, gzip on responses, `ttid=smarterpool`, and
  no custom cloud domain.
- **Not yet tested against the live server.** Unconfirmed: the native HMAC key format, the AES key
  derivation without `ecode` (pre-login), and whether `chKey` (computed natively) is required.

## API endpoint / data center

The app does **not** hardcode a single host. `assets/thing_domains_v1/regions` (AES-256-CTR;
32-byte key prepended, then 16-byte IV, base64-wrapped) decrypts to a per-region domain list:

| region | mobileApiUrl |
|---|---|
| EU (default) | `https://a1.tuyaeu.com` |
| AZ (W. America) | `https://a1-us.iotbing.com` |
| IN | `https://a1-in.iotbing.com` |
| RU | `https://a1.iot334.com` |

`tools/extract_regions.py` reproduces this. There is no `t_cdc.tcfg` in the APK, so these baked-in
values are authoritative and the BuildConfig appKey is used as-is.

This OEM ("smarterpool" ttid) runs on Tuya's **iotbing**/**iot334** OEM clouds. The EU entry is
just Tuya's generic default, so an EU OEM account likely lives on `a1-eu.iotbing.com`, not
`a1.tuyaeu.com`. That matches the live error: `thing.m.country.list` on `a1.tuyaeu.com` returns
`ILLEGAL_CLIENT_ID / Invalid client; No access` — the appKey isn't on that cluster.

**Next:** `python3 tools/probe_hosts.py` sends the no-login country list to each candidate host.
The host that returns anything other than `ILLEGAL_CLIENT_ID` is the right cluster; set it with
`InverterLifeClient(host=...)`. The authoritative routing is the `*.iot-dns.com` discovery service
(`h2-eu.iot-dns.com`), which can be implemented later if the static hosts don't resolve it.

## Options for Home Assistant

1. **Local control (likely best):** the dongle is a Tuya device, so `tuya-local` (HACS) or
   LocalTuya can poll it on the LAN with no cloud. They need the device's `devId` and `localKey`,
   which can be fetched once from the cloud (via this API, or by re-pairing the device into the
   Smart Life app and using the Tuya IoT developer platform).
2. **Official Tuya cloud:** HA's built-in Tuya integration works with Smart Life / Tuya Smart
   accounts. It won't log in with an InverterLife account, but re-pairing the dongle into Smart
   Life usually works, because white-label devices are interchangeable.
3. **Replicate the InverterLife app's API:** possible, but it needs the BMP key and the `et=3`
   crypto. It's fragile because Tuya rotates SDK versions.
