// Host-side stand-in for the ESP32 Arduino core (core 3.x signatures) used only to
// type-check the sketch with g++ when the Xtensa toolchain is not available.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>     // the real core pulls this in too (catches name clashes such as link())
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
class String { public: String(const char *s = "") {} bool operator==(const char *) const { return false; } };
typedef enum { ADC_0db, ADC_2_5db, ADC_6db, ADC_11db } adc_attenuation_t;
class Print {
public:
  virtual ~Print() {}
  virtual size_t write(uint8_t) = 0;
  virtual size_t write(const uint8_t *b, size_t n) { size_t k = 0; while (n--) k += write(*b++); return k; }
  size_t print(const __FlashStringHelper *) { return 0; } size_t print(const char *) { return 0; } size_t print(char) { return 0; }
  size_t print(unsigned char, int = DEC) { return 0; } size_t print(int, int = DEC) { return 0; } size_t print(unsigned int, int = DEC) { return 0; }
  size_t print(long, int = DEC) { return 0; } size_t print(unsigned long, int = DEC) { return 0; } size_t print(double, int = 2) { return 0; }
  size_t println(const __FlashStringHelper *) { return 0; } size_t println(unsigned int, int = DEC) { return 0; } size_t println(int, int = DEC) { return 0; }
};
class Stream : public Print { public: virtual int available() { return 0; } virtual int read() { return -1; } virtual int peek() { return -1; } };
class HardwareSerial : public Stream {
public:
  HardwareSerial(int) {}
  void begin(unsigned long baud, uint32_t config = SERIAL_8N1, int8_t rxPin = -1, int8_t txPin = -1, bool invert = false, unsigned long timeout_ms = 20000UL, uint8_t rx = 120) {}
  size_t write(uint8_t) override { return 1; }
  size_t write(const uint8_t *, size_t n) override { return n; }
};
extern HardwareSerial Serial;
unsigned long millis(); void delay(uint32_t);
void pinMode(uint8_t, uint8_t); void digitalWrite(uint8_t, uint8_t); int digitalRead(uint8_t);
uint16_t analogRead(uint8_t); uint32_t analogReadMilliVolts(uint8_t); void analogSetPinAttenuation(uint8_t, adc_attenuation_t);
