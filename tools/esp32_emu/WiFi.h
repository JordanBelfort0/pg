#pragma once
#include "Arduino.h"
typedef enum { WIFI_OFF, WIFI_STA, WIFI_AP, WIFI_AP_STA } wifi_mode_t;
#define WIFI_SCAN_RUNNING (-1)
#define WIFI_SCAN_FAILED (-2)
class WiFiClass { public:
  static bool mode(wifi_mode_t) { return true; }
  bool disconnect(bool wifioff = false, bool eraseap = false, unsigned long timeoutLength = 100) { return true; }
  int16_t scanNetworks(bool async = false, bool show_hidden = false, bool passive = false, uint32_t max_ms_per_chan = 300, uint8_t channel = 0, const char *ssid = nullptr, const uint8_t *bssid = nullptr);
  int16_t scanComplete(); void scanDelete() {}
  String SSID(uint8_t); int32_t RSSI(uint8_t); };
extern WiFiClass WiFi;
