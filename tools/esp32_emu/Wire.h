#pragma once
#include "Arduino.h"
class TwoWire : public Stream { public:
  uint8_t buf[6]; uint8_t n = 0, pos = 0;
  bool begin(int sda = -1, int scl = -1, uint32_t f = 0) { return true; }
  void beginTransmission(uint8_t) {} uint8_t endTransmission(bool = true) { return 0; }
  size_t requestFrom(uint8_t address, size_t len, bool stopBit) { return requestFrom(address, len); }
  size_t requestFrom(uint8_t address, size_t len);
  int available() override { return n - pos; } int read() override { return pos < n ? buf[pos++] : -1; }
  size_t write(uint8_t) override { return 1; } };
extern TwoWire Wire;
