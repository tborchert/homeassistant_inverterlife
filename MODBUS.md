# Local Modbus route (recommended)

The AquaX 20 (13.5 kW, model **FAI-150-0017**) is a **Fairland** inverter pool heat pump. The
Tuya "InverterLife" Wi-Fi module is a Modbus-RTU-to-WiFi bridge: it plugs into an **RS485** header
on the heat pump's main control board and polls the board over Modbus. So instead of cloning the
Tuya cloud API (blocked on native crypto — see `FINDINGS.md`), we can read the same RS485 bus
directly and keep everything **local**, with no Tuya cloud and no app-key/signing problems.

Two people have already done this on Fairland-family boards:
- **ESPHome config** (register map below): https://github.com/rstcologne/ESP-Home-Fairland-Heatpump
- **HACS integration + RS485 bus-dump tool**: https://github.com/spongioblast/spo_pool_heat_pump
- HA threads: ["Controlling a Fairland Pool Heatpump eliminating Tuya"](https://community.home-assistant.io/t/controlling-a-fairland-pool-heatpump-eliminating-tuya/579467),
  ["Local AquaTemp replacement via Modbus RS-485"](https://community.home-assistant.io/t/local-aquatemp-replacement-for-pool-heat-pump-modbus-rs-485-via-usr-dr164/1025364)

> **Unverified for this exact model.** The register map comes from Fairland **MWH216 / MWH298**
> boards. Nobody has published an AquaX 20 / FAI-150-0017 map, and registers can differ even
> between firmware versions of the same board. Treat the map as a strong starting point and
> confirm it with a bus dump (below) before trusting any value.

## Wiring

- On the main control board there is an RS485 header with pins labelled **A** and **B**, and it
  also provides **12 V** (enough to power an ESP + MAX485). This is the connector the Tuya Wi-Fi
  module plugs into.
- Options to tap it:
  - **In parallel** with the existing Wi-Fi module (both on the bus). One reporter runs the
    AquaTemp WiFi module and a reader in parallel and the app still works; another warns of a
    "short circuit / loop". **Safest is to unplug the Tuya module** and connect your reader in its
    place, at least while mapping.
- **Serial:** 9600 baud, Modbus slave/unit id **1** (`0x01`). Data/parity/stop not documented —
  assume **8N1** and confirm. Bus termination not discussed (short stubs inside the unit are fine).

## Hardware options (pick one)

1. **ESP8266/ESP32 + MAX485**, flashed with ESPHome (the rstcologne config). Powered from the
   board's 12 V via a buck converter. Talks to HA over WiFi with the ESPHome API. Cleanest HA
   integration; this is the best-documented option for Fairland.
2. **USB-RS485 adapter** into the HA host (or any Linux box) — simplest for a first **bus dump**
   and for HA's built-in `modbus:` platform if the host is near the unit.
3. **USR-DR164** (RS485-to-network gateway) — if the heat pump is far from the HA host; exposes
   Modbus-TCP over the LAN.

## Register map (Fairland MWH216/MWH298 — verify on your unit)

Temperature encoding for all temp registers: **°C = (raw − 96) / 2 + 18** (write: `raw = (°C − 18)*2 + 96`).

**Coils** (read fn 01 / write fn 05): `0` Power on/off · `1` compulsory defrost.

**Holding registers** (read fn 03 / write fn 06):
| reg | meaning |
|---|---|
| 0 | mode: 0 auto, 1 heating, 2 cooling |
| 1 | power mode: 0 normal, 1 silence, 2 super-silence, 3 turbo |
| 2 | target temp (auto) |
| 3 | target temp (heating) |
| 4 | target temp (cooling) |
| 5 | water-pump mode |
| 25 | power-off memory (default 1) |

**Input registers** (read fn 04): `0` speed % · `1` target compressor freq · `2` PFC voltage (V) ·
`3` **inlet water temp** · `4` **outlet water temp** · `5` **ambient air temp** · `6` discharge ·
`7` outer coil · `8` suction · `9` inner coil · `10` running compressor freq (Hz) ·
`11` compressor current (×0.1 A) · `13` EEV opening · `14` DC fan speed · `21–25` board version
(ASCII) · `26–29` model code (ASCII) · `30` supply voltage (V).

**Discrete inputs** (read fn 02): `0` on/off · `1` defrosting · `3` silence · `7` water-flow switch ·
`8` HP switch · `9` LP switch · `10` compressor · `11` fan · `12` 4-way valve · `17` circ pump.
`48–95` = fault bits E0..FF (e.g. 49 = E1 high-pressure, 51 = E3 no-water, 65 = P1 inlet-sensor).

Read-only monitoring (our goal, and read-only by the project's rule) only needs the **input
registers** and **discrete inputs** — no writes.

## Gotchas

- **Power** isn't current × 230 V; use PFC voltage (input reg 2). Turbo (power mode 3) doesn't work
  on all models. "Super-silence" is reachable only over Modbus, not from the panel or the app.
- Register maps differ by board/firmware — **record a clean bus dump** (spongioblast's rs485-dump
  tool) with the stock Tuya module running, to see which registers it actually reads, then match.
- On ESP8266, logging can steal the UART (`logger: hardware_uart: UART0_SWAP`); on ESP32 move UART
  off the log pins.

## Suggested plan

1. Open the unit's control box, find the A/B/12V RS485 header (where the Tuya module plugs in).
2. Capture a **bus dump** with a USB-RS485 adapter (stock module still attached) to learn the real
   registers for the AquaX 20.
3. Stand up **ESPHome** (rstcologne config as a base) or the **spo_pool_heat_pump** HACS
   integration; adjust registers to match the dump.
4. Expose inlet/outlet/ambient temps, setpoint, mode, compressor freq and fault state as HA
   sensors — read-only.

This supersedes the cloud-clone approach for monitoring; keep `FINDINGS.md` as the record of why
the cloud path stalled.
