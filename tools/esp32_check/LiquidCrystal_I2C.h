#pragma once
#include "Arduino.h"
class LiquidCrystal_I2C : public Print { public: LiquidCrystal_I2C(uint8_t, uint8_t, uint8_t) {}
  void init() {} void backlight() {} void setCursor(uint8_t, uint8_t) {} size_t write(uint8_t) override { return 1; } };
