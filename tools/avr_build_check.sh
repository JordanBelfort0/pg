#!/usr/bin/env bash
# Compile-check the firmware for an Arduino Uno without the Arduino IDE (used during development).
# Needs: avr-gcc, ArduinoCore-avr, TinyGPSPlus, LiquidCrystal_I2C, DHT-sensor-library checked out in $T.
set -e
T=${T:-/home/claude/tools}; MCU=${MCU:-atmega328p}; VARIANT=${VARIANT:-standard}; BOARD=${BOARD:-ARDUINO_AVR_UNO}
CC=$T/${GCCDIR:-avr-gcc-7.3.0-x64-linux}/bin/avr-gcc; CXX=$T/${GCCDIR:-avr-gcc-7.3.0-x64-linux}/bin/avr-g++
CORE=$T/ArduinoCore-avr; SK=$(cd "$(dirname "$0")/../firmware/pestguard_node" && pwd)
B=$(mktemp -d); trap "rm -rf $B" EXIT
INC="-I$CORE/cores/arduino -I$CORE/variants/$VARIANT -I$CORE/libraries/Wire/src -I$CORE/libraries/Wire/src/utility -I$CORE/libraries/SoftwareSerial/src -I$T/TinyGPSPlus/src -I$T/LiquidCrystal_I2C -I$T/DHT-sensor-library -I$SK"
F="-mmcu=$MCU -DF_CPU=16000000L -DARDUINO=10819 -D$BOARD -DARDUINO_ARCH_AVR -Os -g -flto -ffunction-sections -fdata-sections -w"
SRC="$(ls $CORE/cores/arduino/*.c $CORE/cores/arduino/*.cpp) $CORE/libraries/Wire/src/Wire.cpp $CORE/libraries/Wire/src/utility/twi.c $CORE/libraries/SoftwareSerial/src/SoftwareSerial.cpp $T/TinyGPSPlus/src/TinyGPS++.cpp $T/LiquidCrystal_I2C/LiquidCrystal_I2C.cpp $T/DHT-sensor-library/DHT.cpp $SK/pg_logic.cpp"
(echo '#include <Arduino.h>'; echo '#line 1 "pestguard_node.ino"'; cat $SK/pestguard_node.ino) > $B/sketch.cpp
OBJS=""
for s in $SRC $B/sketch.cpp; do o=$B/$(echo $s | md5sum | cut -c1-8).o
  case $s in *.c) $CC $F -std=gnu11 $INC -c $s -o $o;; *.S) $CC $F -x assembler-with-cpp $INC -c $s -o $o;; *) $CXX $F -std=gnu++11 -fpermissive -fno-exceptions -fno-threadsafe-statics $INC -c $s -o $o;; esac
  OBJS="$OBJS $o"; done
for s in $CORE/cores/arduino/*.S; do o=$B/$(basename $s).o; $CC $F -x assembler-with-cpp $INC -c $s -o $o; OBJS="$OBJS $o"; done
$CC -mmcu=$MCU -Os -flto -fuse-linker-plugin -Wl,--gc-sections -o $B/fw.elf $OBJS -lm
[ -n "$NM" ] && $T/${GCCDIR:-avr-gcc-7.3.0-x64-linux}/bin/avr-nm --size-sort -C -S $B/fw.elf | tail -40
$T/${GCCDIR:-avr-gcc-7.3.0-x64-linux}/bin/avr-size -A $B/fw.elf | grep -E "^\.(text|data|bss) "
$T/${GCCDIR:-avr-gcc-7.3.0-x64-linux}/bin/avr-size $B/fw.elf | tail -1 | awk '{printf "FLASH used: %d bytes (text+data)   RAM used by globals: %d bytes (data+bss)\n", $1+$2, $2+$3}'
