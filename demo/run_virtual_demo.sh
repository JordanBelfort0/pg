#!/usr/bin/env bash
# Demo without hardware: the gateway replays one day of the dataset for 5 workers
# (as if 5 wearables were connected) and the dashboard shows it.
# Usage: ./run_virtual_demo.sh [day=2026-10-05] [start=09:50] [speed=20]
DAY=${1:-2026-10-05}; START=${2:-09:50}; SPEED=${3:-20}
cd "$(dirname "$0")/.."
rm -rf logs
ARGS=""; for i in 1 2 3 4 5; do f=data/week/raw_1hz/W0${i}_${DAY}.csv.gz; [ -f "$f" ] && ARGS="$ARGS --replay $f"; done
python3 gateway/pestguard_gateway.py $ARGS --speed $SPEED --start $START &
sleep 2
streamlit run dashboard/dashboard.py
kill $(jobs -p) 2>/dev/null
