# Capturing the native crypto with Frida

Goal: run the real InverterLife app with `tools/frida_hook_security.js` attached, log in, open the
inverter, and record what the native security functions produce. From that we learn the real
`chKey`, the exact signed string, and real `requestId → AES key` pairs — and whether they're
stable (bakeable) or device-specific.

You need an Android environment the app runs in. Easiest on a Mac is a **rootable emulator**
(Google APIs image, *not* Google Play — Play images can't be rooted). A rooted physical phone
works too; skip to step 4.

## 1. Host tools (Mac)

```bash
brew install --cask android-platform-tools   # adb
```

Install Frida into the project venv (host side):

```bash
/private/tmp/claude-501/-Users-tom-src-homeassistant-inverterlife/f63bd0eb-9fc3-489d-8b90-980a3b870e90/scratchpad/venv/bin/pip install frida-tools
```

Note the version — the on-device frida-server must match it exactly:

```bash
/private/tmp/claude-501/-Users-tom-src-homeassistant-inverterlife/f63bd0eb-9fc3-489d-8b90-980a3b870e90/scratchpad/venv/bin/frida --version
```

## 2. Emulator (Android Studio)

Install Android Studio, then in **Device Manager** create a virtual device with a **Google APIs**
system image (arm64-v8a on Apple Silicon), API 33 or 34. Start it, then:

```bash
adb root        # must succeed; if it says "adbd cannot run as root", the image is a Play image — recreate with Google APIs
```

## 3. Install the app

From the folder with the two APKs:

```bash
cd /Users/tom/src/homeassistant_inverterlife
adb install-multiple base.apk split_config.arm64_v8a.apk
```

## 4. frida-server on the device

Download the server matching your Frida version and the device arch (arm64) from
`https://github.com/frida/frida/releases` (file `frida-server-<version>-android-arm64.xz`), then:

```bash
xz -d frida-server-*-android-arm64.xz
adb push frida-server-*-android-arm64 /data/local/tmp/frida-server
adb shell "chmod 755 /data/local/tmp/frida-server && /data/local/tmp/frida-server &"
```

## 5. Run the hook and capture

```bash
cd /Users/tom/src/homeassistant_inverterlife
/private/tmp/claude-501/-Users-tom-src-homeassistant-inverterlife/f63bd0eb-9fc3-489d-8b90-980a3b870e90/scratchpad/venv/bin/frida -U -f com.InverterLife -l tools/frida_hook_security.js | tee frida_capture.log
```

In the app: log in with your InverterLife account, open the inverter, let the dashboard load.

## 6. What to send back

From `frida_capture.log`, the useful lines are:

- `[getChKey] ... => chKey=...`
- `[request params]` blocks (the full key=value set, incl. `chKey`, `time`, `requestId`, `postData`)
- `[computeDigest] signString=... => sign=...`
- `[getEncryptoKey] requestId=... ecode=... => key=...`

**Before pasting: redact.** `sid`, `ecode`, `access_token`, and the `postData`/response plaintext
can contain your session and account data. The values I need are `chKey`, the *shape* of the
`signString`, and a couple of `requestId → key` pairs — not your session tokens. Paste a login
request and one data request, with `sid`/`ecode`/token values X'd out.

If the app crashes on the emulator (root/emulator detection), use a rooted physical phone for
steps 4–5; everything else is the same.
