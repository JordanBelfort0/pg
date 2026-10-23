#!/usr/bin/env bash
# Virtual wearable (Linux / macOS): the real firmware compiled for the PC, driven by a scenario file,
# connected to the gateway and dashboard exactly like a real ESP32. For rehearsing the demo only.
#   ./demo/run_virtual_wearable.sh [scenario.csv]
cd "$(dirname "$0")/.."
SC=${1:-tools/esp32_emu/demo_scenario.csv}
tools/esp32_emu/build.sh || exit 1
tools/esp32_emu/pestguard_emu "$SC" > /tmp/pg_emu_port.txt 2> logs_emu_lcd.txt &
EMU=$!; sleep 1; PORT=$(head -1 /tmp/pg_emu_port.txt)
echo "virtual wearable on $PORT (LCD output in logs_emu_lcd.txt)"
python3 gateway/pestguard_gateway.py --port "$PORT" &
sleep 2
streamlit run dashboard/dashboard.py
kill $(jobs -p) $EMU 2>/dev/null
