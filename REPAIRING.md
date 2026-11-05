# Re-pairing route (no disassembly, no rooting)

If you can't open the unit and won't root a phone, this is the most practical path. The AquaX 20's
Wi-Fi module is a standard Tuya module, so you move the heat pump from the vendor "InverterLife"
app onto the official **Smart Life** app, then connect Home Assistant to that — ideally
**locally**, with no cloud.

**This is confirmed to work on the sibling model.** A Home Assistant user put a Fairland **X20**
into Smart Life (no Fairland app involved) by triggering pairing and scanning in Smart Life, then
used the **Tuya Local** integration — i.e. fully local LAN control.
([HA forum](https://community.home-assistant.io/t/fairland-heat-pump-to-ha/304871))

## Trade-offs / risks

- A Tuya device binds to **one account at a time**. You must **remove it from InverterLife first**;
  another user confirmed it only appeared in Smart Life after unbinding from the vendor app.
- **Vendor lock is possible:** some OEM modules only ever show in their own app. If Smart Life
  can't find it, the step is reversible — re-add it in InverterLife. (You lose nothing by trying.)
- The result (via Tuya cloud integration) is **cloud-dependent** unless Tuya Local works. Our
  earlier LAN scan found nothing on port 6668, but that was under the OEM binding — re-scan after
  pairing to Smart Life, since the sibling model did expose local control.

## Steps

1. **Unbind from InverterLife:** in the InverterLife app, remove/delete the heat pump device.
2. **Put the unit in Wi-Fi pairing (AP) mode from the control panel.** On these controllers it's a
   button combo held ~5 s until the Wi-Fi symbol flashes (commonly power + temperature-down, but
   **check your AquaX manual for the exact combo**). Your phone/router must be on **2.4 GHz**.
3. **Add it in Smart Life:** install the official **Smart Life** app, "Add device", let it scan /
   use AP mode. If it appears and shows data, it's a standard Tuya device and you're through the
   hard part.
4. **Connect Home Assistant — try local first:**
   - **Local (best): Tuya Local / LocalTuya** (HACS). Needs the device's `device_id` + `local_key`,
     which you pull once from a free Tuya IoT Platform project (the `tinytuya` wizard automates it).
     No ongoing cloud dependency.
   - **Cloud (fallback): the built-in HA Tuya integration**, or the `Korkuttum/tuya_heat_pump`
     HACS integration (cloud mode + optional MQTT push), using a Tuya IoT project linked to your
     Smart Life account.
5. **Re-scan for local control:** after pairing, re-run the port-6668 scan
   (`tools/probe_hosts.py` is cloud-only; use a LAN scan) to see if Tuya Local is possible.

## If Smart Life can't see it

Then the module is OEM-locked and the no-disassembly options are exhausted. What's left needs
either hardware (the local Modbus route, `MODBUS.md`, which needs opening the unit) or
instrumentation (the cloud-clone route, `FINDINGS.md` / `FRIDA.md`, which needs a rooted/arm64
Android environment — e.g. a cloud Android VM like Corellium/Genymotion so you don't root your own
phone).

## Not your variant

`siedi/ha-fairland` talks to Fairland's **iGarden** cloud, not Tuya. Your unit uses the Tuya-based
InverterLife/Smarter Pool app, so that integration won't apply unless the unit also binds to
iGarden.
