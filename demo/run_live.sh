#!/usr/bin/env bash
# Real wearable(s): ./run_live.sh /dev/cu.usbserial-0001   (Mac; Linux: /dev/ttyUSB0) [more ports ...]
cd "$(dirname "$0")/.."
ARGS=""; for p in "$@"; do ARGS="$ARGS --port $p"; done
python3 gateway/pestguard_gateway.py $ARGS &
sleep 2
streamlit run dashboard/dashboard.py
kill $(jobs -p) 2>/dev/null
