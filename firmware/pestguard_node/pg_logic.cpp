#include "config.h"
#include "pg_logic.h"

#if PG_ZONES_IN_RAM
static ZoneDef zoneRam[N_ZONES];
static bool zoneRamReady = false;
static void zoneRamInit() { if (!zoneRamReady) { memcpy_P(zoneRam, ZONES, sizeof zoneRam); zoneRamReady = true; } }
static void loadZone(uint8_t i, ZoneDef &z) { zoneRamInit(); z = zoneRam[i]; }
#else
static void loadZone(uint8_t i, ZoneDef &z) { memcpy_P(&z, &ZONES[i], sizeof(ZoneDef)); }
#endif
static void loadProduct(uint8_t i, ProductDef &p) { memcpy_P(&p, &PRODUCTS[i], sizeof(ProductDef)); }
static bool zoneActive(const ZoneDef &z, uint32_t t) { return z.tAppEnd != NOT_SPRAYED && t >= z.tAppEnd && t < z.tAppEnd + (uint32_t)z.reiH * 3600UL; }

#if PG_ZONES_IN_RAM
uint16_t PestGuard::setSpray(uint8_t i, uint8_t mask, float rate, uint32_t tEnd) {
  if (i >= N_ZONES || mask == 0 || mask >= (1u << N_PRODUCTS) || rate <= 0) return 0;
  zoneRamInit();
  uint16_t rei = 0; ProductDef p;                          // REI_Manager: longest REI of the tank mix
  for (uint8_t k = 0; k < N_PRODUCTS; k++) if (mask & (1 << k)) { loadProduct(k, p); if (p.rei_h > rei) rei = p.rei_h; }
  zoneRam[i].prodMask = mask; zoneRam[i].rate = rate; zoneRam[i].tAppEnd = tEnd; zoneRam[i].reiH = rei;
  rt[i].inside = 0; rt[i].nearF = 0; rt[i].cnt = 0; rt[i].ncnt = 0;
  return rei;
}
bool PestGuard::clearZone(uint8_t i) {
  if (i >= N_ZONES) return false;
  zoneRamInit(); zoneRam[i].tAppEnd = NOT_SPRAYED; zoneRam[i].prodMask = 0;
  if (authZone == (int8_t)i) authZone = -1;
  return true;
}
#endif
bool PestGuard::zoneInfo(uint8_t i, uint32_t &tEnd, uint16_t &reiH, uint8_t &mask) const {
  if (i >= N_ZONES) return false;
  ZoneDef z; loadZone(i, z); tEnd = z.tAppEnd; reiH = z.reiH; mask = z.prodMask; return true;
}

uint8_t classifyActivity(float accStdG, float pitchDeg) {
  if (accStdG < 0.04f) return 0;      // rest
  if (pitchDeg > 40.0f) return 2;     // bent posture: hand labour
  return 1;                           // walking
}

void PestGuard::begin(float bw_, float ppe_, bool vuln) {
  bw = bw_; ppe = ppe_; vulnerable = vuln;
  newDay();
  vocBase = -1; baseSum = 0; baseN = 0;
}

void PestGuard::newDay() {
  for (uint8_t i = 0; i < N_PRODUCTS; i++) dose[i] = 0;
  memset(rt, 0, sizeof(rt));
  state = SAFE; doseAcked = false;
}

float PestGuard::hazardIndex() const {
  float hi = 0; ProductDef p;
  for (uint8_t i = 0; i < N_PRODUCTS; i++) { loadProduct(i, p); hi += dose[i] / p.aoel; }
  return hi;
}

// ray casting in integer decimetres (no division)
bool __attribute__((noinline)) PestGuard::pointInPoly(const ZoneDef &z, int32_t x, int32_t y) {
  bool in = false;
  for (uint8_t i = 0, j = z.nv - 1; i < z.nv; j = i++) {
    int32_t xi = z.vx[i], yi = z.vy[i], xj = z.vx[j], yj = z.vy[j];
    if ((yi > y) != (yj > y)) {
      int32_t lhs = (x - xi) * (yj - yi), rhs = (xj - xi) * (y - yi);
      if ((yj > yi) ? (lhs < rhs) : (lhs > rhs)) in = !in;
    }
  }
  return in;
}

// shortest distance from the point to the polygon outline, metres
float __attribute__((noinline)) PestGuard::edgeDistance(const ZoneDef &z, int32_t x, int32_t y) {
  float best = 1e12f;
  for (uint8_t i = 0; i < z.nv; i++) {
    uint8_t k = (i + 1 == z.nv) ? 0 : i + 1;
    float x1 = z.vx[i], y1 = z.vy[i];
    float dx = z.vx[k] - x1, dy = z.vy[k] - y1, px = x - x1, py = y - y1;
    float L = dx * dx + dy * dy, t = (L > 0) ? (px * dx + py * dy) / L : 0;
    if (t < 0) t = 0; else if (t > 1) t = 1;
    px -= t * dx; py -= t * dy;
    float d2 = px * px + py * py;
    if (d2 < best) best = d2;
  }
  return sqrt(best) * 0.1f;
}

TickOutput PestGuard::step(const TickInput &in) {
  TickOutput o; ZoneDef z; ProductDef p;
  o.act = classifyActivity(in.accStdG, in.pitchDeg);
  const uint32_t t = in.now;

  // ---- VOC proxy (baseline = mean of the first BASELINE_S seconds)
  float comp = in.mqRaw / (1.0f + RH_K * (in.rh - 60.0f));
  if (vocBase < 0) { baseSum += comp; if (++baseN >= BASELINE_S) vocBase = baseSum / baseN; }
  o.vocRel = (vocBase > 0) ? (comp - vocBase) / vocBase : 0;
  float r = o.vocRel / VOC_SAT; if (r < 0) r = 0; if (r > 1) r = 1;
  o.vocW = 1.0f + VOC_ALPHA * r;

  // ---- one pass over zones: GeoFence_Engine, REI_Manager, Dose_Engine
  const float actF = (o.act == 0) ? 0.5f : (o.act == 1 ? 1.0f : 1.5f);
  uint8_t zstate[N_ZONES]; uint16_t activeBits = 0;
  bool insideActive = false, nearActive = false;
  if (in.authPressed) authZone = -2;                        // resolve below
  for (uint8_t i = 0; i < N_ZONES; i++) {
    zstate[i] = G_OUT;
    loadZone(i, z);
    if (z.tAppEnd == NOT_SPRAYED || t < z.tAppEnd) continue;  // not sprayed (yet)
    bool act = zoneActive(z, t);
    if (act) activeBits |= (1 << i);
    if (in.geo ? in.geo[i].valid : in.fixValid) {
      bool rawIn = in.geo ? in.geo[i].in : pointInPoly(z, in.x, in.y);
      if (rawIn != (bool)rt[i].inside) { if (++rt[i].cnt >= HYST_N) { rt[i].inside = rawIn; rt[i].cnt = 0; } }
      else rt[i].cnt = 0;
      float d = rawIn ? 0 : (in.geo ? in.geo[i].d : edgeDistance(z, in.x, in.y));
      bool was = rt[i].nearF;
      bool cand = was ? (d <= nearOut) : (d <= nearIn);
      if (cand != was) { if (++rt[i].ncnt >= (was ? NEAR_OUT_N : NEAR_IN_N)) { was = !was; rt[i].ncnt = 0; } }
      else rt[i].ncnt = 0;
      rt[i].nearF = was && !rt[i].inside;
    }
    zstate[i] = rt[i].inside ? G_IN : (rt[i].nearF ? G_NEAR : G_OUT);
  }
  // supervisor-authorised early entry (ACK held 3 s): the active zone the worker is in, else next to
  if (authZone == -2) {
    authZone = -1;
    for (uint8_t pass = 0; pass < 2 && authZone < 0; pass++)
      for (uint8_t i = 0; i < N_ZONES; i++)
        if ((activeBits & (1 << i)) && zstate[i] == (pass ? G_NEAR : G_IN)) { authZone = i; authUntil = t + AUTH_MIN * 60UL; break; }
  }
  o.authorised = authZone >= 0 && t < authUntil;
  for (uint8_t i = 0; i < N_ZONES; i++) {
    bool act = activeBits & (1 << i);
    bool authOk = (authZone == (int8_t)i) && t < authUntil;
    if (zstate[i] == G_IN && act && !authOk) insideActive = true;
    if (zstate[i] == G_NEAR && act) nearActive = true;
    if (zstate[i] != G_IN) continue;
    loadZone(i, z);
    float tauD = (t - z.tAppEnd) / 86400.0f;
    float common = z.rate * TF_CM2_H * actF * (authOk ? AUTH_PPE : ppe) * o.vocW / (3600.0f * 1000.0f * bw);
    for (uint8_t k = 0; k < N_PRODUCTS; k++) {
      if (!(z.prodMask & (1 << k))) continue;
      loadProduct(k, p);
      dose[k] += p.dfr0 * exp(-0.693147f * tauD / p.dt50_d) * p.da * common;     // mg/kg in this second
    }
  }
  o.hi = hazardIndex();
  const float kv = vulnerable ? 0.5f : 1.0f, hw = HI_WARN * kv, hc = HI_CRIT * kv;
  const bool vocSpike = insideActive && o.vocRel > VOC_SPIKE;

  // ---- Alert_FSM
  const uint32_t dt = (t >= tState) ? t - tState : 0;      // guard against a clock set backwards
  const bool downOk = dt >= DWELL_S;
  const bool ack = in.ackPressed && !prevAck;
  prevAck = in.ackPressed;
  const Level lowState = (nearActive || o.hi >= 0.5f * hw) ? ADVISORY : SAFE;
  Level s = state, nxt = s;
  switch (s) {
    case SAFE:      if (insideActive || o.hi >= hw) nxt = WARNING; else if (lowState == ADVISORY) nxt = ADVISORY; break;
    case ADVISORY:  if (insideActive || o.hi >= hw) nxt = WARNING; else if (lowState == SAFE && downOk) nxt = SAFE; break;
    case WARNING:
      if ((insideActive && dt >= T_EXIT_S) || (o.hi >= hc && !doseAcked) || vocSpike) nxt = CRITICAL;
      else if (!insideActive && o.hi < hw && downOk) nxt = lowState;
      break;
    case CRITICAL:  if (ack) nxt = ACKED; else if (dt >= T_ACK_S) nxt = ESCALATED; break;
    case ESCALATED: if (ack) nxt = ACKED; break;
    case ACKED:
      if (!insideActive && downOk) nxt = (o.hi >= hw) ? WARNING : lowState;
      else if (insideActive && dt >= T_EXIT_S) nxt = CRITICAL;
      break;
  }
  if (nxt == ACKED && o.hi >= hc) doseAcked = true;
  o.prev = s; o.changed = (nxt != s);
  if (o.changed) { state = nxt; tState = t; }
  o.level = state;

  // ---- summary: inside active > inside expired > near active
  o.zoneIndex = -1; o.zoneCode = -1; o.reiMinLeft = -1;
  int8_t best = -1;
  for (uint8_t i = 0; i < N_ZONES; i++) {
    bool act = activeBits & (1 << i);
    int8_t rank = (zstate[i] == G_IN) ? (act ? 3 : 2) : ((zstate[i] == G_NEAR && act) ? 0 : -1);
    if (rank > best) { best = rank; o.zoneIndex = i; o.zoneCode = i * 10 + (zstate[i] == G_IN ? 2 : 1); }
  }
  if (o.zoneIndex >= 0 && (activeBits & (1 << o.zoneIndex))) {
    loadZone(o.zoneIndex, z);
    o.reiMinLeft = (z.tAppEnd + (uint32_t)z.reiH * 3600UL - t) / 60UL;
  }
  return o;
}
