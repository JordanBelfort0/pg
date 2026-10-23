// ===================================================================
//  PestGuard wearable node - configuration
//  Board: ESP32 DevKit V1 / DevKitC (ESP32-WROOM-32), Arduino core 3.x.
//  The same sketch still builds for an Arduino Uno (fallback pin map below).
//  Change the values in this file only; the .cpp files read them.
// ===================================================================
#pragma once

// ---------------- identity of this wearable (one per worker) --------
#define WORKER_ID        "W01"     // printed in every data line; one wearable per worker
#define BODY_WEIGHT_KG   60.0f
#define PPE_FACTOR       1.0f     // fraction of residue that reaches skin: 1.0 none, 0.5 gloves ...
#define VULNERABLE       0        // 1 = flagged vulnerable by supervisor -> thresholds halved

// ---------------- operating mode -------------------------------------
#ifndef USE_SIM_PATH
#define USE_SIM_PATH     0        // 1 = ignore GPS and walk the scripted path in zones.h
                                  //     (for indoor demos where GPS has no fix)
#endif
#ifndef USE_BEACON
#define USE_BEACON       1        // ESP32: find zones from Wi-Fi beacons (phone hotspots) instead of GPS.
                                  //     0 = NEO-6M GPS and polygon zones (zones_gps.h).
#endif                            //     USE_SIM_PATH 1 overrides both (zones_week.h).
#define USE_LCD          1        // 1 = 16x2 I2C LCD fitted
#define USE_DHT          1        // 1 = DHT22/DHT11 fitted
#define USE_MPU          1        // 1 = MPU6050 fitted

// ---------------- Wi-Fi beacon zones (USE_BEACON 1) ------------------
//  Zone i (1, 2, ...) is the phone hotspot named BEACON_PREFIX + i, placed at the centre of the
//  "plot". Distance is estimated from the signal strength:  d = 10 ^ ((RSSI_1M - rssi) / (10 x PATH_N))
//  Calibrate RSSI_1M: hold the wearable 1 m from the phone and read rssi_dbm in the data line.
#define BEACON_PREFIX    "PG-ZONE-"
#define BEACON_RSSI_1M   -54.0f   // dBm at 1 m (calibrate)
#define BEACON_PATH_N    2.5f     // path-loss exponent: about 2 in open space, 2.5-3.5 indoors
#define BEACON_IN_M      2.0f     // inside the zone: estimated distance up to this
#define BEACON_NEAR_IN_M 5.0f     // near band (enter / leave), the same hysteresis as the 25/35 m GPS band
#define BEACON_NEAR_OUT_M 7.0f
#define BEACON_SMOOTH    0.5f     // exponential smoothing of RSSI between scans (0 = none)
#define BEACON_CHANNEL   0        // 0 = scan all channels (about 2 s); set the hotspots' channel to scan faster
#define BEACON_AUTOSPRAY 0        // >0: with no laptop, after 20 s mark zone 1 as sprayed with product bit mask
                                  //     BEACON_AUTOSPRAY, 30 minutes ago (stand-alone demo). 0 = off.

// ---------------- links to the laptop ---------------------------------
#define SERIAL_BAUD      57600    // USB cable (the gateway uses the same value)
#ifndef USE_BT
#define USE_BT           0        // ESP32 only: also send every line over built-in Bluetooth
                                  // (classic SPP, device name "PestGuard-" WORKER_ID). Set 0 in Wokwi.
#endif
#define GPS_BAUD         9600     // NEO-6M default

#if defined(ARDUINO_ARCH_ESP32)
// ---------------- pins (ESP32 DevKit V1 / DevKitC, ESP32-WROOM-32) ----
//  Logic is 3.3 V. Never connect a 5 V signal straight to a GPIO.
#define PIN_GPS_RX       16       // ESP32 receives here (UART2 RX)  <- GPS TX
#define PIN_GPS_TX       17       // ESP32 sends here    (UART2 TX)  -> GPS RX (optional)
#define PIN_SDA          21       // I2C: MPU6050 directly, LCD through the level shifter
#define PIN_SCL          22
#define PIN_DHT          4
#define DHT_TYPE         DHT22    // or DHT11
#define PIN_MQ           34       // MQ-135 AO through a 10k (top) / 20k (bottom) divider; ADC1, input only
#define MQ_DIV           1.5f     // (10k + 20k) / 20k : sensor volts = pin volts x 1.5
#define PIN_VSENSE       35       // 5 V (VIN) through a 100k / 100k divider; ADC1, input only
#define VSENSE_DIV       2.0f
#define PIN_BUZZER       25       // base of BC547 #2 via 1k ; buzzer between 5V and collector
#define PIN_VIB          26       // base of BC547 #1 via 1k ; motor between 5V and collector, 1N4148 across motor
#define PIN_ACK          32       // push button to GND (short press = ACK, hold 3 s = supervisor early entry)
#define PIN_SOS          33       // push button to GND
#define PIN_LED          13       // LED + 220R to GND
#else
// ---------------- pins (Arduino Uno, kept as a fallback build) -------
//  D0/D1 hardware Serial -> USB, or an HC-05 module (TX->D0, RX<-D1 through a 1k/2k divider)
#define PIN_GPS_RX       4
#define PIN_GPS_TX       3
#define PIN_DHT          2
#define DHT_TYPE         DHT22
#define PIN_MQ           A0
#define PIN_BUZZER       5
#define PIN_VIB          6
#define PIN_ACK          7
#define PIN_SOS          8
#define PIN_LED          9
// A4 = SDA, A5 = SCL
#endif
#define LCD_ADDR         0x27     // try 0x3F if the screen stays blank
#define MPU_ADDR         0x68

// ---------------- PestGuard logic (same values as sim/pestguard_logic.py) --
#define HYST_N           3        // consecutive fixes to change INSIDE/OUTSIDE
#define NEAR_IN_M        25.0f
#define NEAR_OUT_M       35.0f
#define NEAR_IN_N        3
#define NEAR_OUT_N       9
#define HDOP_MAX         5.0f
#define T_EXIT_S         120
#define T_ACK_S          60
#define DWELL_S          10
#define HI_WARN          0.5f
#define HI_CRIT          0.8f
#define VOC_ALPHA        0.5f
#define VOC_SAT          0.5f
#define VOC_SPIKE        0.6f
#define RH_K             0.006f
#define TF_CM2_H         1500.0f
#define AUTH_PPE         0.1f
#define AUTH_MIN         60
#define BASELINE_S       300      // gas baseline learnt during the first 5 minutes after power-on
#define LONG_PRESS_MS    3000

// Wi-Fi beacons and the built-in Bluetooth need an ESP32
#if defined(ARDUINO) && !defined(ARDUINO_ARCH_ESP32)
#undef USE_BEACON
#define USE_BEACON 0
#undef USE_BT
#define USE_BT 0
#endif
