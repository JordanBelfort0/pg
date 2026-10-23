#pragma once
#include "Arduino.h"
struct RawDegrees { uint16_t deg; uint32_t billionths; bool negative; };
struct TGL { bool isValid() { return false; } uint32_t age() { return 0; } RawDegrees r; const RawDegrees &rawLat() { return r; } const RawDegrees &rawLng() { return r; } };
struct TGD { bool isValid() { return false; } uint16_t year() { return 0; } uint8_t month() { return 0; } uint8_t day() { return 0; } };
struct TGT { bool isValid() { return false; } uint32_t age() { return 0; } uint8_t hour() { return 0; } uint8_t minute() { return 0; } uint8_t second() { return 0; } };
struct TGI { bool isValid() { return false; } int32_t value() { return 0; } };
class TinyGPSPlus { public: bool encode(char) { return false; } TGL location; TGD date; TGT time; TGI hdop; TGI satellites; };
