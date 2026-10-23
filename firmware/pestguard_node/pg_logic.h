// ===================================================================
//  PestGuard core logic for the wearable (mirrors sim/pestguard_logic.py)
//  GeoFence_Engine, REI_Manager, Dose_Engine, VOC proxy, Alert_FSM
// ===================================================================
#pragma once
#include <Arduino.h>
#if defined(ARDUINO_ARCH_AVR)
#include <avr/pgmspace.h>   // ESP32: PROGMEM and memcpy_P come with Arduino.h
#endif

#define MAX_V 6
struct ProductDef { float aoel, da, dt50_d, dfr0; uint16_t rei_h; };
struct ZoneDef {
  uint8_t nv; int16_t vx[MAX_V]; int16_t vy[MAX_V];   // decimetres from origin
  uint8_t prodMask; uint32_t tAppEnd; float rate; uint16_t reiH;
};
struct SimPoint { int16_t x, y; uint16_t dwell; uint8_t act; };

// Zone tables: zones_beacon.h (Wi-Fi beacon zones), zones_week.h (synthetic farm + scripted walk)
// or zones_gps.h (polygons), chosen by the settings in config.h. PG_ZONES_FILE overrides the choice.
#if defined(PG_ZONES_FILE)
#include PG_ZONES_FILE
#elif USE_SIM_PATH
#include "zones_week.h"
#elif USE_BEACON
#include "zones_beacon.h"
#else
#include "zones_gps.h"
#endif

// ESP32: zones are copied to RAM so that the supervisor can record sprays at run time
#if defined(ARDUINO_ARCH_ESP32) || defined(PG_RAM_ZONES)
#define PG_ZONES_IN_RAM 1
#endif
#define NOT_SPRAYED 0xFFFFFFFFUL       // tAppEnd of a zone with no spray recorded

// Per-zone position measurement from a source other than satellite positioning
// (Wi-Fi beacons): valid = new measurement this second, in = raw inside, d = distance estimate (m)
struct GeoMeas { bool valid; bool in; float d; };

enum Level : uint8_t { SAFE = 0, ADVISORY, WARNING, CRITICAL, ESCALATED, ACKED };
enum Geo : uint8_t { G_OUT = 0, G_NEAR = 1, G_IN = 2 };

struct ZoneRt { uint8_t inside : 1, nearF : 1, cnt : 3; uint8_t ncnt; };

struct TickInput {
  bool fixValid; int32_t x, y;   // decimetres from origin
  uint32_t now;                  // unix seconds (UTC)
  float accStdG, pitchDeg;       // from the IMU over the last second
  uint16_t mqRaw; float rh;
  bool ackPressed, authPressed;
  const GeoMeas *geo;            // optional, one entry per zone; nullptr = use x, y and the polygons
};

struct TickOutput {
  Level level, prev; bool changed;
  float hi; uint8_t act; float vocW, vocRel;
  int8_t zoneIndex; int16_t zoneCode; int16_t reiMinLeft; bool authorised;
};

class PestGuard {
public:
  void begin(float bw, float ppe, bool vulnerable);
  void newDay();
  TickOutput step(const TickInput &in);
  float hazardIndex() const;
  void sos(uint32_t t) { state = ESCALATED; tState = t; }   // SOS button: straight to supervisor
  Level level() const { return state; }
  void setNearBand(float inM, float outM) { nearIn = inM; nearOut = outM; }
#if PG_ZONES_IN_RAM
  // supervisor records a spray: zone i, product bit mask, rate kg/ha, end of application (unix s).
  // Returns the REI the device applies (longest REI among the products), or 0 if rejected.
  uint16_t setSpray(uint8_t i, uint8_t mask, float rate, uint32_t tEnd);
  bool clearZone(uint8_t i);
#endif
  bool zoneInfo(uint8_t i, uint32_t &tEnd, uint16_t &reiH, uint8_t &mask) const;
  float dose[N_PRODUCTS];        // mg per kg body weight, today

private:
  ZoneRt rt[N_ZONES];
  float bw, ppe; bool vulnerable;
  Level state = SAFE; uint32_t tState = 0;
  bool doseAcked = false, prevAck = false;
  float vocBase = -1; float baseSum = 0; uint16_t baseN = 0;
  int8_t authZone = -1; uint32_t authUntil = 0;
  float nearIn = NEAR_IN_M, nearOut = NEAR_OUT_M;
  static bool pointInPoly(const ZoneDef &z, int32_t x, int32_t y);
  static float edgeDistance(const ZoneDef &z, int32_t x, int32_t y);
};

uint8_t classifyActivity(float accStdG, float pitchDeg);
