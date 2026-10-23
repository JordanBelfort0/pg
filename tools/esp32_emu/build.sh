#!/usr/bin/env bash
# Builds the virtual wearable (Linux / macOS): the real sketch compiled against PC stand-ins.
set -e; D=$(cd "$(dirname "$0")" && pwd); SK=$D/../../firmware/pestguard_node; B=$(mktemp -d); trap "rm -rf $B" EXIT
(echo '#include <Arduino.h>'; cat $SK/pestguard_node.ino) > $B/sketch.cpp
g++ -std=gnu++17 -O1 -w -include $D/Arduino.h -I$D -I$SK -DUSE_BT=0 ${EXTRA:-} \
    $B/sketch.cpp $SK/pg_logic.cpp $D/emu.cpp -o $D/pestguard_emu
echo "built $D/pestguard_emu"
