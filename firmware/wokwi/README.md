# Running the firmware in the Wokwi simulator (no hardware)

1. Open https://wokwi.com, choose **New project -> ESP32** (Arduino template).
2. Replace `diagram.json` with the one in this folder and add a file `libraries.txt` with the same content as here.
3. Add the firmware files as new tabs: `pestguard_node.ino` (replace sketch.ino), `config.h`, `zones_week.h`,
   `pg_logic.h`, `pg_logic.cpp`.
4. In `config.h` set `USE_SIM_PATH 1` (Wokwi has no GPS module; the scripted walk in zones.h is used)
   `USE_BT 0` (Wokwi does not simulate Bluetooth) and `USE_BEACON 0` (Wokwi cannot create the zone hotspots). The Serial Monitor shows one data line per
   second starting with "PG,". The first build in Wokwi takes a minute or two.
5. Press Start. The LCD shows the alert level, zone and REI countdown. The worker walks from the shed into
   plot P2 (sprayed 3.5 h earlier, REI 48 h): ADVISORY, then WARNING, CRITICAL after 2 minutes and
   ESCALATED one minute later. Press **ACK** to acknowledge. Hold **ACK** for 3 s to simulate the
   supervisor's early-entry authorisation. The potentiometer stands in for the MQ-135 gas sensor and the
   yellow LED for the vibration motor.

In the simulator the buzzer and LEDs hang directly on the pins and the LCD has no level shifter; on the real
board the buzzer and motor go through transistors and the LCD through a level shifter (see the Build Guide).
Keep the potentiometer still during the first 5 minutes (the gas baseline is learnt then); turning it up by
more than half afterwards, inside the plot, makes a gas spike.

The MPU6050 in Wokwi has sliders: tilt it forward (> 40 degrees) to simulate bending (hand labour), which
raises the dose rate.
