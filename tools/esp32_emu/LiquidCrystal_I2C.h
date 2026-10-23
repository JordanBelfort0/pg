#pragma once
#include "Arduino.h"
// Prints the 16x2 screen to stderr whenever it changes (virtual wearable)
class LiquidCrystal_I2C : public Print { public:
  char scr[2][17]; char shown[2][17]; uint8_t r = 0, c = 0;
  LiquidCrystal_I2C(uint8_t, uint8_t, uint8_t) { memset(scr, ' ', sizeof scr); scr[0][16] = scr[1][16] = 0; memcpy(shown, scr, sizeof scr); }
  void init() {} void backlight() {}
  void setCursor(uint8_t col, uint8_t row) {
    if (row == 0 && col == 0 && memcmp(scr, shown, sizeof scr)) { memcpy(shown, scr, sizeof scr); fprintf(stderr, "LCD |%s|%s|\n", scr[0], scr[1]); }
    r = row & 1; c = col; }
  size_t write(uint8_t ch) override { if (c < 16) scr[r][c++] = (char)ch; return 1; } };
