#pragma once
#include "Arduino.h"
class BluetoothSerial : public Stream { public:
  bool begin(String localName = String(), bool isMaster = false, bool disableBLE = false) { return true; }
  bool hasClient(void) { return false; }
  size_t write(uint8_t c) override { return 1; } size_t write(const uint8_t *buffer, size_t size) override { return size; } };
