#pragma once
#include "Arduino.h"
class TwoWire : public Stream { public:
  bool begin(int sda = -1, int scl = -1, uint32_t f = 0) { return true; }
  void beginTransmission(uint8_t) {} uint8_t endTransmission(bool = true) { return 0; }
  size_t requestFrom(uint8_t address, size_t len, bool stopBit) { return 0; } size_t requestFrom(uint8_t address, size_t len) { return 0; }
  size_t write(uint8_t) override { return 1; } };
extern TwoWire Wire;
