#pragma once
#include "Arduino.h"
#define DHT11 11
#define DHT22 22
class DHT { public: DHT(uint8_t, uint8_t) {} void begin() {} float readTemperature() { return 28; } float readHumidity() { return 60; } };
