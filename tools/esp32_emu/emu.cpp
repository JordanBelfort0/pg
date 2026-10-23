// Virtual wearable: runs the unchanged PestGuard sketch on a PC.
//   ./pestguard_emu scenario.csv [speed]
// It opens a pseudo-terminal and prints its name; give that name to the gateway (--port).
// scenario.csv: t_s,rssi1,rssi2,gas_mv,act,ack,sos   (rows apply from t_s until the next row)
//   rssi = dBm of hotspot PG-ZONE-1 / -2 (-127 = not heard), gas_mv at GPIO34, act = rest|walk|hand,
//   ack / sos = 1 while the button is held.
#include "Arduino.h"
#include "Wire.h"
#include "WiFi.h"
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <chrono>
#include <random>
#include <vector>
#include <fstream>
#include <sstream>

HardwareSerial Serial(0);
TwoWire Wire;
WiFiClass WiFi;
void setup();
void loop();

struct Row { double t; int r1, r2, gas; int act; int ack, sos; };
static std::vector<Row> rows;
static double speed = 1.0;
static auto t0 = std::chrono::steady_clock::now();
static std::mt19937 rng(7);
static double nowS() { return std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count() * speed; }
static const Row &cur() { size_t k = 0; double t = nowS(); while (k + 1 < rows.size() && rows[k + 1].t <= t) k++; return rows[k]; }

unsigned long millis() { return (unsigned long)(nowS() * 1000.0); }
void delay(uint32_t ms) { usleep((useconds_t)(ms * 1000 / speed)); }
void pinMode(uint8_t, uint8_t) {}
static int lastOut[40];
void digitalWrite(uint8_t p, uint8_t v) { if (p < 40) lastOut[p] = v; }
int digitalRead(uint8_t p) { const Row &r = cur(); if (p == 32) return r.ack ? LOW : HIGH; if (p == 33) return r.sos ? LOW : HIGH; return HIGH; }
uint16_t analogRead(uint8_t) { return 0; }
uint32_t analogReadMilliVolts(uint8_t p) {
  std::normal_distribution<double> nz(0, 8);
  if (p == 34) return (uint32_t)std::max(0.0, cur().gas + nz(rng));
  if (p == 35) return 2480;                                  // 4.96 V through the 1:2 divider
  return 0;
}
void analogSetPinAttenuation(uint8_t, adc_attenuation_t) {}

size_t HardwareSerial::write(uint8_t c) { if (fd >= 0) { ssize_t r = ::write(fd, &c, 1); (void)r; } return 1; }
size_t HardwareSerial::write(const uint8_t *b, size_t n) { if (fd >= 0) { ssize_t r = ::write(fd, b, n); (void)r; } return n; }
static int peeked = -1;
int HardwareSerial::available() {
  if (peeked >= 0) return 1;
  unsigned char c; if (fd >= 0 && ::read(fd, &c, 1) == 1) { peeked = c; return 1; } return 0;
}
int HardwareSerial::read() { if (!available()) return -1; int c = peeked; peeked = -1; return c; }

// accelerometer: gravity plus movement noise, tilted forward for hand labour
size_t TwoWire::requestFrom(uint8_t, size_t len) {
  const Row &r = cur(); std::normal_distribution<double> nz(0, r.act == 0 ? 0.01 : (r.act == 1 ? 0.25 : 0.12));
  double pitch = r.act == 2 ? 55 : 10, ax = sin(pitch / 57.2958) + nz(rng), ay = nz(rng), az = cos(pitch / 57.2958) + nz(rng);
  int16_t v[3] = {(int16_t)(ax * 16384), (int16_t)(ay * 16384), (int16_t)(az * 16384)};
  for (int i = 0; i < 3; i++) { buf[2 * i] = (uint8_t)(v[i] >> 8); buf[2 * i + 1] = (uint8_t)(v[i] & 0xff); }
  n = 6; pos = 0; return len;
}

// Wi-Fi scan: finishes 1.6 s after it was started, results from the scenario
static double scanStart = -1; static int scanN = 0; static std::vector<std::pair<std::string, int>> found;
int16_t WiFiClass::scanNetworks(bool, bool, bool, uint32_t, uint8_t, const char *, const uint8_t *) { scanStart = nowS(); return WIFI_SCAN_RUNNING; }
int16_t WiFiClass::scanComplete() {
  if (scanStart < 0) return WIFI_SCAN_FAILED;
  if (nowS() - scanStart < 1.6) return WIFI_SCAN_RUNNING;
  scanStart = -1; found.clear(); const Row &r = cur(); std::normal_distribution<double> nz(0, 2.5);
  found.push_back({"campus-wifi", -70});
  if (r.r1 > -127) found.push_back({"PG-ZONE-1", (int)(r.r1 + nz(rng))});
  if (r.r2 > -127) found.push_back({"PG-ZONE-2", (int)(r.r2 + nz(rng))});
  return (int16_t)found.size();
}
String WiFiClass::SSID(uint8_t i) { return String(found[i].first); }
int32_t WiFiClass::RSSI(uint8_t i) { return found[i].second; }

int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: %s scenario.csv [speed]\n", argv[0]); return 1; }
  if (argc > 2) speed = atof(argv[2]);
  std::ifstream f(argv[1]); std::string line; std::getline(f, line);
  while (std::getline(f, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::stringstream ss(line); std::string c; std::vector<std::string> v; while (std::getline(ss, c, ',')) v.push_back(c);
    if (v.size() < 7) continue;
    rows.push_back({atof(v[0].c_str()), atoi(v[1].c_str()), atoi(v[2].c_str()), atoi(v[3].c_str()),
                    v[4] == "hand" ? 2 : (v[4] == "walk" ? 1 : 0), atoi(v[5].c_str()), atoi(v[6].c_str())});
  }
  if (rows.empty()) { fprintf(stderr, "empty scenario\n"); return 1; }
  int m = posix_openpt(O_RDWR | O_NOCTTY); grantpt(m); unlockpt(m);
  int s = open(ptsname(m), O_RDWR | O_NOCTTY);              // keep the slave open so writes never fail
  struct termios tio; tcgetattr(s, &tio); cfmakeraw(&tio); tcsetattr(s, TCSANOW, &tio);
  fcntl(m, F_SETFL, O_NONBLOCK);
  Serial.fd = m;
  printf("%s\n", ptsname(m)); fflush(stdout);
  setup();
  for (;;) { loop(); usleep(2000); }
}
