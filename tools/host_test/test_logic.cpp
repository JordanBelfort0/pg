// Feeds a 1 Hz CSV (raw_1hz format) through the firmware's PestGuard::step and prints alert changes.
// Build: g++ -I. -I../../firmware/pestguard_node test_logic.cpp ../../firmware/pestguard_node/pg_logic.cpp
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <sstream>
#include <ctime>
#include "config.h"
#include "pg_logic.h"
static const char *LV[] = {"SAFE", "ADVISORY", "WARNING", "CRITICAL", "ESCALATED", "ACKED"};
int main(int argc, char **argv) {
  float bw = atof(argv[1]), ppe = atof(argv[2]); int vul = atoi(argv[3]);
  PestGuard pg; pg.begin(bw, ppe, vul);
  char line[512]; fgets(line, sizeof line, stdin);
  TickOutput o{};
  while (fgets(line, sizeof line, stdin)) {
    std::vector<std::string> f; std::stringstream ss(line); std::string c;
    while (std::getline(ss, c, ',')) f.push_back(c);
    struct tm tm{}; strptime(f[0].c_str(), "%Y-%m-%dT%H:%M:%S", &tm);
    time_t t = timegm(&tm) - 19800;                                        // IST -> UTC
    double lat = atof(f[1].c_str()), lon = atof(f[2].c_str()), hdop = atof(f[3].c_str());
    long latE6 = lround(lat * 1e6), lonE6 = lround(lon * 1e6);
    TickInput in{};
    in.fixValid = hdop <= HDOP_MAX;
    in.x = (int32_t)((lonE6 - ORIGIN_LON_E6) * (1.1132f * COS_LAT0));
    in.y = (int32_t)((latE6 - ORIGIN_LAT_E6) * 1.10574f);
    in.now = (uint32_t)t;
    in.accStdG = atof(f[8].c_str()) / 1000.0f;
    in.pitchDeg = fabs(asin(fmax(-1.0, fmin(1.0, atof(f[5].c_str()) / 1000.0))) * 57.2958);
    in.mqRaw = atoi(f[11].c_str()); in.rh = atof(f[10].c_str());
    o = pg.step(in);
    if (o.changed) printf("%s,%s,%s,%.4f,%d,%d\n", f[0].c_str(), LV[o.prev], LV[o.level], o.hi, o.zoneCode, o.reiMinLeft);
  }
  printf("FINAL_HI,%.4f\n", o.hi);
}
