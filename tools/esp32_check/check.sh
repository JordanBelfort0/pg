#!/usr/bin/env bash
# Type-check the sketch against ESP32 core 3.x signatures on a PC (no Xtensa toolchain needed).
# This catches API and type errors; the real build is done in the Arduino IDE (board "ESP32 Dev Module").
set -e; D=$(cd "$(dirname "$0")" && pwd); SK=$D/../../firmware/pestguard_node; B=$(mktemp -d); trap "rm -rf $B" EXIT
(echo '#include <Arduino.h>'; cat $SK/pestguard_node.ino) > $B/sketch.cpp
for sim in 0 1; do for bt in 0 1; do for bc in 0 1; do
  g++ -std=gnu++17 -fsyntax-only -Wall -Wno-unused-variable -Wno-unused-function -include $D/Arduino.h -I$D -I$SK \
      -DUSE_SIM_PATH=$sim -DUSE_BT=$bt -DUSE_BEACON=$bc $B/sketch.cpp
  g++ -std=gnu++17 -fsyntax-only -Wall -include $D/Arduino.h -I$D -I$SK -DUSE_SIM_PATH=$sim -DUSE_BEACON=$bc $SK/pg_logic.cpp
  echo "ESP32 type-check OK (USE_SIM_PATH=$sim, USE_BT=$bt, USE_BEACON=$bc)"
done; done; done
