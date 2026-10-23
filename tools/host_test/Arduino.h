// Minimal stand-in for Arduino.h so the firmware logic can be compiled and tested on a PC.
#pragma once
#include <stdint.h>
#include <string.h>
#include <math.h>
#define PROGMEM
#define memcpy_P memcpy
#define constrain(x, lo, hi) ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))
