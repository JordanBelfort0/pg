// PC stand-in for the ESP32 Arduino core, used to run the real PestGuard sketch on a laptop as a
// "virtual wearable" (tools/esp32_emu). Serial goes to a pseudo-terminal, Wi-Fi beacons, buttons
// and the gas channel come from a scenario file. For testing the gateway and dashboard only.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string>
#define ARDUINO_ARCH_ESP32 1
#define PROGMEM
#define memcpy_P memcpy
#define HIGH 1
#define LOW 0
#define INPUT 1
#define OUTPUT 3
#define INPUT_PULLUP 5
#define SERIAL_8N1 0x800001c
#define DEC 10
#define constrain(amt, low, high) ((amt) < (low) ? (low) : ((amt) > (high) ? (high) : (amt)))
class __FlashStringHelper;
#define F(s) (reinterpret_cast<const __FlashStringHelper *>(s))
class String { public: std::string s; String(const char *c = "") : s(c) {} String(const std::string &x) : s(x) {}
  bool operator==(const char *c) const { return s == c; } };
typedef enum { ADC_0db, ADC_2_5db, ADC_6db, ADC_11db } adc_attenuation_t;
class Print {
public:
  virtual ~Print() {}
  virtual size_t write(uint8_t) = 0;
  virtual size_t write(const uint8_t *b, size_t n) { size_t k = 0; while (n--) k += write(*b++); return k; }
  size_t w(const char *s) { return write((const uint8_t *)s, strlen(s)); }
  size_t print(const __FlashStringHelper *f) { return w((const char *)f); } size_t print(const char *s) { return w(s); }
  size_t print(char c) { return write((uint8_t)c); }
  size_t print(unsigned char v, int = DEC) { return print((unsigned long)v); } size_t print(int v, int = DEC) { return print((long)v); }
  size_t print(unsigned int v, int = DEC) { return print((unsigned long)v); }
  size_t print(long v, int = DEC) { char b[24]; snprintf(b, sizeof b, "%ld", v); return w(b); }
  size_t print(unsigned long v, int = DEC) { char b[24]; snprintf(b, sizeof b, "%lu", v); return w(b); }
  size_t print(double v, int d = 2) { char b[32]; snprintf(b, sizeof b, "%.*f", d, v); return w(b); }
  size_t println() { return w("\r\n"); }
  template <typename T> size_t println(T v) { size_t n = print(v); return n + println(); }
  template <typename T> size_t println(T v, int d) { size_t n = print(v, d); return n + println(); }
};
class Stream : public Print { public: virtual int available() { return 0; } virtual int read() { return -1; } virtual int peek() { return -1; } };
class HardwareSerial : public Stream {
public:
  int fd = -1;
  HardwareSerial(int) {}
  void begin(unsigned long baud, uint32_t config = SERIAL_8N1, int8_t rxPin = -1, int8_t txPin = -1, bool invert = false, unsigned long timeout_ms = 20000UL, uint8_t rx = 120) {}
  size_t write(uint8_t c) override; size_t write(const uint8_t *b, size_t n) override;
  int available() override; int read() override;
};
extern HardwareSerial Serial;
unsigned long millis(); void delay(uint32_t);
void pinMode(uint8_t, uint8_t); void digitalWrite(uint8_t, uint8_t); int digitalRead(uint8_t);
uint16_t analogRead(uint8_t); uint32_t analogReadMilliVolts(uint8_t); void analogSetPinAttenuation(uint8_t, adc_attenuation_t);
