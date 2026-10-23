# PestGuard - wearable pesticide re-entry and exposure tracker

Course project (Wearable Computing). An ESP32 wearable that knows which plots were sprayed,
counts down each plot's restricted-entry interval (REI), warns the worker before and after unsafe
entry, and keeps a per-worker exposure estimate. Each wearable sends one data line per second to a
laptop (USB cable or the ESP32's built-in Bluetooth); a small gateway program logs it and a dashboard shows it to the supervisor.

```
firmware/pestguard_node/   Arduino-IDE sketch for the ESP32 DevKit (still builds for an Uno). Edit config.h.
                           Zone tables: zones_beacon.h (Wi-Fi beacon zones, default), zones_week.h (scripted
                           walk over the synthetic farm), zones_gps.h (GPS polygons); made by tools/make_zones_h.py.
firmware/wokwi/            Files to run the sketch in the Wokwi simulator (no hardware).
gateway/                   pestguard_gateway.py: reads serial ports (or replays data) -> logs/ for the dashboard.
dashboard/                 Streamlit supervisor dashboard: live view, supervisor console (record sprays, test
                           markers), bench test results, week review.
sim/                       Python reference model, one-week data generator, analysis.
data/week/                 One week (5-11 Oct 2026) of SYNTHETIC data for 5 workers. See data/week/README.md.
demo/                      run_virtual_demo (no hardware) and run_live (real wearables).
tools/                     make_zones_h.py, hw_results.py (bench results from the logs), esp32_emu (virtual
                           wearable: the real sketch running on a PC), esp32_check, avr_build_check, host_test.
```

## Quick start without hardware
1. Install Python 3.9+ and run `pip install -r requirements.txt`.
2. Run `demo\run_virtual_demo.bat` (or `./demo/run_virtual_demo.sh`). The gateway replays Monday 5 October
   from 09:50 at 20x speed for five workers and the dashboard opens in the browser. Worker W03 walks into
   plot P2 at about 10:03 (data time) and the alert goes WARNING, CRITICAL, ESCALATED.

## With the ESP32 (bench demo, no GPS needed)
Zones are phone hotspots named `PG-ZONE-1`, `PG-ZONE-2`. The wearable estimates its distance to each from
the Wi-Fi signal strength and decides inside / near / outside with the same rules as the GPS version.
1. In the Arduino IDE, add the ESP32 boards (Boards Manager: "esp32 by Espressif Systems", version 3.x) and
   select "ESP32 Dev Module". Install TinyGPSPlus, LiquidCrystal I2C and DHT sensor library.
2. Wire as in the Bench Demo Guide; check `config.h` (USE_BEACON 1, USE_SIM_PATH 0).
3. Turn on the hotspots, upload, close the Serial Monitor, then `demo\run_live.bat COM5` (your port).
4. In the dashboard: Supervisor console > Record a spray (zone 1). The device answers with the REI it applies.
5. Walk towards the zone phone; use the Entered / Left markers; Bench test results computes the delays.
For the GPS version set USE_BEACON 0 and make zones_gps.h with `--demo-zone`.

## Virtual wearable (Linux / macOS, no hardware)
`tools/esp32_emu/build.sh` compiles the unchanged sketch for the PC; `./pestguard_emu demo_scenario.csv`
prints a serial port name to give to the gateway (`--port`). The scenario file supplies beacon strengths,
gas, activity and button presses. It is for testing the gateway and dashboard; it is not a hardware result.

## Reproducing the results in the IDF-B
```
cd sim
python generate_week.py        # ~3 min, writes data/week
python analyse_week.py         # results + figures in data/week/outputs and data/week/figures
cd ../tools/host_test && g++ -I. -I../../firmware/pestguard_node -DPG_ZONES_FILE='"zones_week.h"' test_logic.cpp ../../firmware/pestguard_node/pg_logic.cpp -o test_logic && python compare.py
```

All pesticide parameters are illustrative placeholders. The gas sensor is a proxy signal only; it does not
measure pesticide concentration. 

`tools/esp32_check/check.sh` type-checks the sketch against the ESP32 core API on a PC;
`tools/avr_build_check.sh` compiles the Uno fallback build.
