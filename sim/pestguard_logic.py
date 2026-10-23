"""
PestGuard core logic - Python reference implementation.

This file mirrors the wearable firmware (firmware/pestguard_node/pg_logic.cpp)
line for line, so that results obtained in simulation carry over to the device.
If you change a constant here, change it in config.h as well.

Modules (same names as in the documents):
    GeoFence   - INSIDE / NEAR / OUTSIDE per zone with hysteresis
    REI        - per-zone restricted-entry countdown (longest REI for tank mixes)
    Dose       - per-worker cumulative dose and hazard index (HI)
    VOCProxy   - MQ-135 reading -> bounded weight 1.0..1.5 (proxy only)
    AlertFSM   - SAFE, ADVISORY, WARNING, CRITICAL, ESCALATED, ACKED

All pesticide parameters are ILLUSTRATIVE placeholders, not real values.
"""
import math

# ------------------------------------------------------------------ constants
TICK_S = 1.0
HYST_N = 3                 # consecutive fixes to change INSIDE/OUTSIDE
NEAR_IN_M = 25.0           # enter NEAR band
NEAR_OUT_M = 35.0          # leave NEAR band
NEAR_IN_N, NEAR_OUT_N = 3, 9
HDOP_MAX = 5.0
T_EXIT_S, T_ACK_S, DWELL_S = 120, 60, 10
HI_WARN, HI_CRIT = 0.5, 0.8          # halved for a vulnerable worker
VOC_ALPHA, VOC_SAT = 0.5, 0.5        # +50% relative rise gives the maximum weight 1.5
VOC_SPIKE = 0.6                      # relative rise treated as a spike inside an active zone
RH_K = 0.006                         # MQ-135 humidity compensation (per %RH above 60)
TF_CM2_H = 1500.0                    # transfer coefficient, cm2/h (placeholder)
ACT_FACTOR = {0: 0.5, 1: 1.0, 2: 1.5}   # rest, walk, hand labour
ACT_NAME = {0: "rest", 1: "walk", 2: "hand"}
AUTH_PPE = 0.1                       # PPE penetration during supervisor-authorised early entry
AUTH_MIN = 60

LEVELS = ["SAFE", "ADVISORY", "WARNING", "CRITICAL", "ESCALATED", "ACKED"]
SAFE, ADVISORY, WARNING, CRITICAL, ESCALATED, ACKED = range(6)

M_PER_DEG_LAT = 110574.0


def to_xy(lat, lon, lat0, lon0):
    """Local metres east/north of the farm origin (equirectangular, fine for < 2 km)."""
    return ((lon - lon0) * 111320.0 * math.cos(math.radians(lat0)), (lat - lat0) * M_PER_DEG_LAT)


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def edge_distance(x, y, poly):
    best = 1e9
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def classify_activity(acc_std_g, pitch_deg):
    """Same rule as the firmware: 0 rest, 1 walk, 2 hand labour (bent posture)."""
    if acc_std_g < 0.04:
        return 0
    if pitch_deg > 40.0:
        return 2
    return 1


class Zone:
    """A sprayed plot. products: list of product ids applied in one tank mix."""

    def __init__(self, zid, poly_xy, products, t_app_end, rate, catalogue):
        self.zid = zid
        self.poly = poly_xy
        self.products = products
        self.t_app_end = t_app_end          # seconds (epoch)
        self.rate = rate                    # kg a.i./ha (per product, same rate assumed)
        self.rei_h = max(catalogue[p]["rei_h"] for p in products)
        self.rei_end = t_app_end + self.rei_h * 3600

    def active(self, t):
        return self.t_app_end <= t < self.rei_end


class WorkerNode:
    """State of one wearable node. Call step() once per second."""

    def __init__(self, wid, bw, ppe, vulnerable, zones, catalogue):
        self.wid, self.bw, self.ppe, self.vulnerable = wid, bw, ppe, vulnerable
        self.zones, self.cat = zones, catalogue
        self.geo = {}            # zone -> "IN"/"OUT"
        self.cnt = {}
        self.near = {}
        self.ncnt = {}
        self.dose = {p: 0.0 for p in catalogue}     # mg/kg bw, current day
        self.week_dose = {p: 0.0 for p in catalogue}
        self.day = None
        self.state = SAFE
        self.t_state = 0
        self.voc_base = None
        self.base_buf = []
        self.auth_zone, self.auth_until = None, -1
        self.uncertain = False
        self.prev_ack = False
        self.dose_acked = False      # dose-limit alarm acknowledged today

    # ---- helpers
    def limits(self):
        k = 0.5 if self.vulnerable else 1.0
        return HI_WARN * k, HI_CRIT * k

    def hi(self):
        return sum(self.dose[p] / self.cat[p]["aoel"] for p in self.dose)

    def voc_weight(self, mq_raw, rh):
        comp = mq_raw / (1.0 + RH_K * (rh - 60.0))
        if self.voc_base is None:
            return 1.0, 0.0
        r = (comp - self.voc_base) / self.voc_base
        return 1.0 + VOC_ALPHA * max(0.0, min(r / VOC_SAT, 1.0)), r

    def learn_baseline(self, mq_raw, rh):
        """Baseline = mean of the first 5 minutes of the shift (taken at the shed), as in the firmware."""
        if self.voc_base is None:
            self.base_buf.append(mq_raw / (1.0 + RH_K * (rh - 60.0)))
            if len(self.base_buf) >= 300:
                self.voc_base = sum(self.base_buf) / len(self.base_buf)

    def new_day(self, day):
        self.day = day
        self.dose = {p: 0.0 for p in self.cat}
        self.voc_base, self.base_buf = None, []
        self.state, self.t_state = SAFE, 0
        self.dose_acked = False
        self.geo, self.cnt, self.near, self.ncnt = {}, {}, {}, {}

    # ---- one tick
    def step(self, t, fix, acc_std_g, pitch_deg, mq_raw, rh, ack_pressed=False, auth_press=False):
        """fix = (x, y, hdop) or None.  Returns a dict describing this tick."""
        act = classify_activity(acc_std_g, pitch_deg)
        self.learn_baseline(mq_raw, rh)
        W, r = self.voc_weight(mq_raw, rh)

        # GeoFence (quality gate)
        valid = fix is not None and fix[2] <= HDOP_MAX
        self.uncertain = not valid
        zone_state = {}
        for z in self.zones:
            if t < z.t_app_end:              # not sprayed yet
                continue
            prev = self.geo.get(z.zid, "OUT")
            if valid:
                x, y, _ = fix
                raw_in = point_in_poly(x, y, z.poly)
                c = self.cnt.get(z.zid, 0)
                c = c + 1 if raw_in != (prev == "IN") else 0
                if c >= HYST_N:
                    prev, c = ("IN" if raw_in else "OUT"), 0
                self.cnt[z.zid] = c
                self.geo[z.zid] = prev
                d = 0.0 if raw_in else edge_distance(x, y, z.poly)
                was = self.near.get(z.zid, False)
                cand = (d <= NEAR_IN_M) if not was else (d <= NEAR_OUT_M)
                k = self.ncnt.get(z.zid, 0)
                k = k + 1 if cand != was else 0
                need = NEAR_IN_N if not was else NEAR_OUT_N
                if k >= need:
                    was, k = (not was), 0
                self.ncnt[z.zid] = k
                self.near[z.zid] = was and prev != "IN"
            zone_state[z.zid] = "INSIDE" if self.geo.get(z.zid) == "IN" else ("NEAR" if self.near.get(z.zid) else "OUTSIDE")

        # supervisor-authorised early entry (long press of ACK while inside a zone)
        if auth_press:      # authorise the active zone the worker is in, else the one he is next to
            cand = [z for z in self.zones if z.active(t) and zone_state.get(z.zid) == "INSIDE"] or \
                   [z for z in self.zones if z.active(t) and zone_state.get(z.zid) == "NEAR"]
            if cand:
                self.auth_zone, self.auth_until = cand[0].zid, t + AUTH_MIN * 60

        # Dose
        for z in self.zones:
            if zone_state.get(z.zid) != "INSIDE":
                continue
            tau_d = (t - z.t_app_end) / 86400.0
            P = AUTH_PPE if (self.auth_zone == z.zid and t < self.auth_until) else self.ppe
            for p in z.products:
                c = self.cat[p]
                dfr = c["dfr0"] * z.rate * math.exp(-math.log(2) * tau_d / c["dt50_d"])   # ug/cm2
                dD_ug = dfr * TF_CM2_H * ACT_FACTOR[act] * P * W * c["da"] * (TICK_S / 3600.0)
                inc = dD_ug / 1000.0 / self.bw
                self.dose[p] += inc
                self.week_dose[p] += inc
        HI = self.hi()
        hw, hc = self.limits()

        def auth_ok(z):
            return self.auth_zone == z.zid and t < self.auth_until

        inside_active = any(zone_state.get(z.zid) == "INSIDE" and z.active(t) and not auth_ok(z) for z in self.zones)
        near_active = any(zone_state.get(z.zid) == "NEAR" and z.active(t) for z in self.zones)
        voc_spike = inside_active and r > VOC_SPIKE

        # Alert FSM
        s = self.state
        dt = t - self.t_state
        down_ok = dt >= DWELL_S
        ack = ack_pressed and not self.prev_ack
        self.prev_ack = ack_pressed
        nxt = s
        if s == SAFE:
            if inside_active or HI >= hw:
                nxt = WARNING
            elif near_active or HI >= 0.5 * hw:
                nxt = ADVISORY
        elif s == ADVISORY:
            if inside_active or HI >= hw:
                nxt = WARNING
            elif not near_active and HI < 0.5 * hw and down_ok:
                nxt = SAFE
        elif s == WARNING:
            if (inside_active and dt >= T_EXIT_S) or (HI >= hc and not self.dose_acked) or voc_spike:
                nxt = CRITICAL
            elif not inside_active and HI < hw and down_ok:
                nxt = ADVISORY if (near_active or HI >= 0.5 * hw) else SAFE
        elif s == CRITICAL:
            if ack:
                nxt = ACKED
            elif dt >= T_ACK_S:
                nxt = ESCALATED
        elif s == ESCALATED:
            if ack:
                nxt = ACKED
        elif s == ACKED:
            if not inside_active and down_ok:
                nxt = WARNING if HI >= hw else (ADVISORY if (near_active or HI >= 0.5 * hw) else SAFE)
            elif inside_active and dt >= T_EXIT_S:
                nxt = CRITICAL
        if nxt == ACKED and HI >= hc:
            self.dose_acked = True       # dose limit seen by worker/supervisor: do not re-raise today
        changed = nxt != s
        if changed:
            self.state, self.t_state = nxt, t

        # summary for the virtual sensor
        zi, zs, rei_left = -1, -1, -1
        best = -1          # prefer: inside active > inside expired > near active
        for i, z in enumerate(self.zones):
            st = zone_state.get(z.zid)
            rank = {"INSIDE": 2, "NEAR": 0}.get(st, -1)
            if rank < 0:
                continue
            if rank == 2 and z.active(t):
                rank = 3
            if rank == 0 and not z.active(t):
                continue
            if rank > best:
                best, zi = rank, i
                zs = 2 if st == "INSIDE" else 1
                rei_left = max(0, int((z.rei_end - t) / 60)) if z.active(t) else -1
        return dict(level=self.state, changed=changed, prev=s, hi=HI, act=act, W=W, voc_rel=r,
                    zone_index=zi, zone_code=(zi * 10 + zs) if zi >= 0 else -1, rei_min_left=rei_left,
                    zone_state=zone_state, uncertain=self.uncertain,
                    authorised=self.auth_zone is not None and t < self.auth_until)
