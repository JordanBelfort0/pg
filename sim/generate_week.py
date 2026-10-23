"""
Generate one week (Mon 5 Oct - Sun 11 Oct 2026) of SYNTHETIC wearable data for
5 farm workers on a 6-plot farm, and run the PestGuard logic on it exactly as
the wearable would (1 Hz), with workers reacting to the alerts.

Usage:  python generate_week.py  [output_folder]      (default ../data/week)

Everything is synthetic. Coordinates are a made-up farm in Vellore district,
Tamil Nadu. Pesticide parameters are ILLUSTRATIVE placeholders.
Random seed is fixed, so the dataset is reproducible.
"""
import csv, gzip, json, math, os, random, sys
from datetime import datetime, timedelta, timezone

import pestguard_logic as PG

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "week")
IST = timezone(timedelta(hours=5, minutes=30))
LAT0, LON0 = 12.9200, 79.1300          # farm origin (south-west corner), synthetic
rng = random.Random(20261005)

# ------------------------------------------------------------------ farm
PLOTS = {   # metres east, north of origin
    "P1": ("Paddy",     [(0, 0), (120, 0), (120, 80), (0, 80)]),
    "P2": ("Tomato",    [(140, 0), (230, 0), (230, 70), (140, 70)]),
    "P3": ("Groundnut", [(250, 0), (350, 0), (350, 90), (250, 90)]),
    "P4": ("Brinjal",   [(0, 110), (95, 110), (100, 170), (60, 195), (0, 190)]),
    "P5": ("Banana",    [(120, 110), (220, 110), (220, 200), (120, 200)]),
    "P6": ("Chilli",    [(250, 120), (330, 120), (330, 190), (250, 190)]),
}
SHED = (185.0, 100.0)
PUMP = (240.0, 100.0)
PUMP_ON = [(7 * 3600, 9 * 3600), (14 * 3600, 15 * 3600)]
CANOPY = {"P5": 2.6}         # banana canopy degrades GNSS (HDOP multiplier)

CATALOGUE = {  # ILLUSTRATIVE values only
    "INS-A": dict(name="Insecticide A (illustrative)", rei_h=48, aoel=0.060, da=0.10, dt50_d=4, dfr0=3.0),
    "INS-B": dict(name="Insecticide B (illustrative)", rei_h=12, aoel=0.020, da=0.10, dt50_d=3, dfr0=3.0),
    "FUN-C": dict(name="Fungicide C (illustrative)", rei_h=12, aoel=0.300, da=0.10, dt50_d=5, dfr0=3.0),
    "FUN-D": dict(name="Fungicide D (illustrative)", rei_h=24, aoel=0.100, da=0.10, dt50_d=6, dfr0=3.0),
    "HER-E": dict(name="Herbicide E (illustrative)", rei_h=24, aoel=0.300, da=0.10, dt50_d=8, dfr0=3.0),
}
D0 = datetime(2026, 10, 5, tzinfo=IST)      # Monday


def T(day, hh, mm=0):
    return int((D0 + timedelta(days=day, hours=hh, minutes=mm)).timestamp())


SPRAYS = [  # id, plot, products, application end, rate kg a.i./ha, applicator
    ("S1", "P2", ["INS-A"], T(0, 6, 30), 0.5, "AP1"),
    ("S2", "P5", ["FUN-C"], T(0, 17, 0), 1.0, "AP1"),
    ("S3", "P3", ["FUN-D", "HER-E"], T(1, 6, 45), 0.8, "AP1"),
    ("S4", "P1", ["INS-B"], T(2, 17, 30), 0.3, "AP2"),
    ("S5", "P4", ["INS-A"], T(3, 6, 30), 0.5, "AP1"),
    ("S6", "P6", ["FUN-C", "INS-B"], T(4, 6, 40), 0.6, "AP2"),
    ("S7", "P2", ["FUN-D"], T(5, 6, 30), 1.0, "AP1"),
]
ZONES = [PG.Zone(sid, PLOTS[pl][1], prods, t_end, rate, CATALOGUE) for sid, pl, prods, t_end, rate, _ in SPRAYS]
ZONE_PLOT = {sid: pl for sid, pl, *_ in SPRAYS}

WORKERS = {  # id, role, body weight, PPE penetration (1 = none), vulnerable, MQ-135 unit baseline
    "W01": dict(role="Harvester", bw=52, ppe=1.0, vulnerable=False, mq=165),
    "W02": dict(role="Weeding", bw=64, ppe=0.5, vulnerable=False, mq=172),
    "W03": dict(role="Field helper", bw=68, ppe=1.0, vulnerable=False, mq=158),
    "W04": dict(role="Irrigation", bw=60, ppe=0.5, vulnerable=False, mq=168),
    "W05": dict(role="Weeding", bw=50, ppe=1.0, vulnerable=True, mq=161),
}

# ------------------------------------------------------------------ plans
# Each day: worker -> list of (start "HH:MM", end, task, plot or place, behaviour)
# behaviour: "work" normal; "comply" = walks into a plot, leaves when warned;
# "ignore" = keeps working, acknowledges only when supervisor arrives;
# "auth" = supervisor-authorised early entry (long press) with PPE.
PLANS = {
    0: {"W01": [("07:05", "12:00", "hand", "P5", "work"), ("13:00", "16:00", "hand", "P5", "work")],
        "W02": [("07:05", "12:00", "hand", "P3", "work"), ("13:00", "16:00", "hand", "P3", "work")],
        "W03": [("07:05", "10:00", "hand", "P1", "work"), ("10:00", "10:40", "hand", "P2", "ignore"),
                ("10:40", "12:00", "hand", "P1", "work"), ("13:00", "16:00", "hand", "P1", "work")],
        "W04": [("07:05", "09:00", "walk", "PUMP", "work"), ("09:00", "12:00", "walk", "P1", "work"),
                ("13:00", "16:00", "walk", "P4", "work")],
        "W05": [("07:05", "12:00", "hand", "P4", "work"), ("13:00", "16:00", "hand", "P4", "work")]},
    1: {"W01": [("07:05", "12:00", "hand", "P5", "work"), ("13:00", "16:00", "hand", "P5", "work")],
        "W02": [("07:15", "07:30", "hand", "P3", "comply"), ("07:30", "12:00", "hand", "P6", "work"),
                ("13:00", "16:00", "hand", "P6", "work")],
        "W03": [("07:05", "12:00", "hand", "P1", "work"), ("13:00", "16:00", "hand", "P1", "work")],
        "W04": [("07:05", "09:00", "walk", "PUMP", "work"), ("09:00", "12:00", "walk", "P6", "work"),
                ("13:00", "16:00", "walk", "P4", "work")],
        "W05": [("07:05", "12:00", "hand", "P4", "work"), ("13:00", "14:05", "hand", "P4", "work"),
                ("14:05", "14:12", "walk", "P2", "comply"), ("14:12", "16:00", "hand", "P4", "work")]},
    2: {"W01": [("07:05", "12:00", "hand", "P2", "work"), ("13:00", "16:00", "hand", "P2", "work")],
        "W02": [("07:05", "12:00", "hand", "P3", "work"), ("13:00", "16:00", "hand", "P3", "work")],
        "W03": [("07:05", "12:00", "hand", "P5", "work"), ("13:00", "16:00", "hand", "P5", "work")],
        "W04": [("07:05", "11:00", "walk", "P1", "work"), ("11:00", "11:30", "rest", "SHED", "work"),
                ("11:30", "12:00", "walk", "P1", "work"), ("13:00", "16:00", "walk", "P1", "work")],
        "W05": [("07:05", "12:00", "hand", "P6", "work"), ("13:00", "16:00", "hand", "P6", "work")]},
    3: {"W01": [("07:05", "12:00", "hand", "P5", "work"), ("13:00", "14:00", "hand", "P5", "work"),
                ("14:00", "15:00", "rest", "SHED", "work"), ("15:00", "16:00", "hand", "P5", "work")],
        "W02": [("07:05", "12:00", "hand", "P1", "work")],          # device not worn after lunch
        "W03": [("07:05", "12:00", "hand", "P3", "work"), ("13:00", "14:00", "hand", "P3", "work"),
                ("14:00", "15:00", "rest", "SHED", "work"), ("15:00", "16:00", "hand", "P3", "work")],
        "W04": [("07:05", "09:10", "walk", "P6", "work"), ("09:10", "09:20", "hand", "P4", "comply"),
                ("09:20", "12:00", "walk", "P6", "work"), ("13:00", "14:00", "walk", "PUMP", "work"),
                ("14:00", "15:00", "rest", "SHED", "work"), ("15:00", "16:00", "walk", "P6", "work")],
        "W05": [("07:05", "12:00", "hand", "P6", "work"), ("13:00", "14:00", "hand", "P6", "work"),
                ("14:00", "15:00", "rest", "SHED", "work"), ("15:00", "16:00", "hand", "P6", "work")]},
    4: {"W01": [("07:05", "12:00", "hand", "P2", "work"), ("13:00", "16:00", "hand", "P2", "work")],
        "W02": [("07:05", "12:00", "hand", "P3", "work"), ("13:00", "16:00", "hand", "P3", "work")],
        "W03": [("07:05", "12:00", "hand", "P1", "work"), ("13:00", "16:00", "hand", "P1", "work")],
        "W04": [("07:05", "09:00", "walk", "PUMP", "work"), ("09:00", "09:45", "hand", "P6", "auth"),
                ("09:45", "12:00", "walk", "P1", "work"), ("13:00", "16:00", "walk", "P1", "work")],
        "W05": [("07:05", "12:00", "hand", "P5", "work"), ("13:00", "16:00", "hand", "P5", "work")]},
    5: {"W01": [("07:05", "12:00", "hand", "P4", "work")],
        "W02": [("07:05", "12:00", "hand", "P6", "work")],
        "W03": [("07:05", "10:58", "hand", "P5", "work"), ("10:58", "11:05", "walk", "P2", "comply"),
                ("11:05", "12:00", "hand", "P5", "work")],
        "W04": [("07:05", "12:00", "walk", "P1", "work")],
        "W05": [("07:05", "12:00", "hand", "P3", "work")]},
}
SHIFT = {d: (T(d, 7, 0), T(d, 16, 0) if d < 5 else T(d, 12, 0)) for d in range(6)}


def hm(day, s):
    h, m = s.split(":")
    return T(day, int(h), int(m))


def centroid(poly):
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


def random_point_in(poly, margin=6.0):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    for _ in range(200):
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if PG.point_in_poly(x, y, poly) and PG.edge_distance(x, y, poly) > margin:
            return x, y
    return centroid(poly)


def place_point(place):
    if place == "SHED":
        return SHED[0] + rng.uniform(-4, 4), SHED[1] + rng.uniform(-3, 3)
    if place == "PUMP":
        return PUMP[0] + rng.uniform(-5, 5), PUMP[1] + rng.uniform(-3, 3)
    return random_point_in(PLOTS[place][1])


def road_route(a, b):
    """Walk via the farm road (y = 100) unless a and b are close."""
    if math.hypot(a[0] - b[0], a[1] - b[1]) < 40:
        return [b]
    return [(a[0], 100.0), (b[0], 100.0), b]


def weather(t):
    """Synthetic Vellore October weather: hourly-smooth temperature (C) and RH (%)."""
    d = datetime.fromtimestamp(t, IST)
    hod = d.hour + d.minute / 60
    day = (d.date() - D0.date()).days
    temp = 28.5 - 4.5 * math.cos((hod - 4.5) / 24 * 2 * math.pi) + [0, 0.6, 1.0, -0.4, 0.3, 0.8, 0.2][day % 7]
    rh = 72 + 16 * math.cos((hod - 4.5) / 24 * 2 * math.pi) + [0, -3, -5, 2, 0, -2, 0][day % 7]
    if day == 3:                                  # Thursday afternoon rain, 13:48-15:36, with 15-min ramps
        f = max(0.0, min(1.0, (hod - 13.8) / 0.25, (15.6 - hod) / 0.25))
        temp -= 5.0 * f
        rh = rh + (95.0 - rh) * f
    return temp, max(35.0, min(98.0, rh))


# ------------------------------------------------------------------ simulate
def simulate_worker(wid, days_out):
    w = WORKERS[wid]
    node = PG.WorkerNode(wid, w["bw"], w["ppe"], w["vulnerable"], ZONES, CATALOGUE)
    gnss_e = [0.0, 0.0]
    a = math.exp(-1 / 30.0)
    for day in range(6):
        plan = PLANS[day].get(wid, [])
        if not plan:
            continue
        node.new_day(day)
        t0, t1 = SHIFT[day]
        # first 5 minutes at the shed (baseline learning), then the plan
        segs = [(t0, hm(day, plan[0][0]), "rest", "SHED", "work")]
        prev_end = segs[0][1]
        for (s, e, act, place, beh) in plan:
            s_, e_ = hm(day, s), hm(day, e)
            if s_ > prev_end:      # lunch or gap -> shed
                segs.append((prev_end, s_, "rest", "SHED", "work"))
            segs.append((s_, e_, act, place, beh))
            prev_end = e_
        worn_until = plan[-1][1]
        worn_end = hm(day, worn_until)
        pos = SHED
        route, target, speed = [], None, 1.1
        seg_i = 0
        leaving = False        # worker is leaving a plot after an alert
        ignore_ack_at = None
        auth_done = False
        last_out = None
        dose_ack_at = None
        reassigned = False
        rows, truth, raw = [], [], []
        win = []
        rows_alerts = days_out["alerts"]
        for t in range(t0, worn_end):
            while seg_i < len(segs) - 1 and t >= segs[seg_i][1]:
                seg_i += 1
                route, leaving, ignore_ack_at, auth_done = [], False, None, False
            s_, e_, act, place, beh = segs[seg_i]
            if reassigned and place in PLOTS:            # supervisor moved the worker to packing at the shed
                act, place, beh = "hand", "SHED", "work"
            # ---- movement (true position)
            if not route and not leaving:
                if place in PLOTS or place in ("SHED", "PUMP"):
                    inside_target_plot = place in PLOTS and PG.point_in_poly(pos[0], pos[1], PLOTS[place][1])
                    if place in PLOTS and not inside_target_plot:
                        route = road_route(pos, place_point(place))
                        speed = 1.1
                    elif place in ("SHED", "PUMP") and math.hypot(pos[0] - (SHED if place == "SHED" else PUMP)[0], pos[1] - (SHED if place == "SHED" else PUMP)[1]) > 8:
                        route = road_route(pos, place_point(place))
                        speed = 1.1
                    else:
                        route = [place_point(place)]
                        speed = 0.25 if act == "hand" else (0.6 if act == "walk" else 0.05)
            moving_fast = False
            if route:
                tx, ty = route[0]
                dx, dy = tx - pos[0], ty - pos[1]
                d = math.hypot(dx, dy)
                step = speed
                if d <= step:
                    pos = (tx, ty)
                    route.pop(0)
                else:
                    pos = (pos[0] + dx / d * step, pos[1] + dy / d * step)
                moving_fast = speed >= 1.0
            true_act = 1 if moving_fast else {"hand": 2, "walk": 1, "rest": 0}[act]
            # ---- GNSS
            true_plot = next((p for p, (_, poly) in PLOTS.items() if PG.point_in_poly(pos[0], pos[1], poly)), "")
            hdop = 0.9 + rng.random() * 0.4
            if true_plot in CANOPY:
                hdop *= CANOPY[true_plot]
            if day == 2 and wid == "W04" and T(2, 11, 0) <= t < T(2, 11, 30):
                hdop = 6.0 + rng.random() * 3      # shed roof / poor sky view
            sig = 2.2 * hdop
            for k in (0, 1):
                gnss_e[k] = a * gnss_e[k] + math.sqrt(1 - a * a) * sig * rng.gauss(0, 1)
            fx, fy = pos[0] + gnss_e[0], pos[1] + gnss_e[1]
            sats = max(4, int(11 - 2.5 * (hdop - 1) + rng.randint(-1, 1)))
            fix = (fx, fy, hdop)
            # ---- IMU (1 s statistics of 10 samples at 10 Hz)
            if true_act == 0:
                std, pitch = abs(rng.gauss(0.015, 0.006)), rng.gauss(12, 6)
            elif true_act == 1:
                std, pitch = abs(rng.gauss(0.22, 0.06)), rng.gauss(15, 8)
            else:
                std, pitch = abs(rng.gauss(0.12, 0.05)), rng.gauss(55, 12)
            pr = math.radians(pitch)
            ax, ay, az = math.sin(pr), rng.gauss(0, 0.05), math.cos(pr)
            # ---- environment and gas
            temp, rh = weather(t)
            temp += rng.gauss(0, 0.2)
            rh += rng.gauss(0, 0.8)
            mq = w["mq"] * (1 + PG.RH_K * (rh - 60)) * (1 - 0.004 * (temp - 25))
            for z in ZONES:
                if t >= z.t_app_end and PG.point_in_poly(pos[0], pos[1], z.poly):
                    mq += w["mq"] * 0.9 * math.exp(-(t - z.t_app_end) / (3 * 3600))
            hod_s = t - T(day, 0, 0)
            if any(a_ <= hod_s < b_ for a_, b_ in PUMP_ON) and math.hypot(pos[0] - PUMP[0], pos[1] - PUMP[1]) < 15:
                mq += w["mq"] * 0.5 * (0.6 + 0.4 * rng.random())          # diesel pump exhaust
            mq = max(0, min(1023, int(round(mq + rng.gauss(0, 3)))))
            vcc = int(4990 + rng.gauss(0, 12) - (15 if node.state >= PG.WARNING else 0))
            # ---- buttons (behaviour model, decided from the previous second's alert)
            plvl = last_out["level"] if last_out else PG.SAFE
            ack, auth = False, False
            if beh == "auth" and not auth_done and last_out and last_out["zone_state"].get("S6") in ("NEAR", "INSIDE"):
                auth, auth_done = True, True          # supervisor checks PPE, long-presses ACK at the plot edge
            if beh == "comply" and plvl == PG.CRITICAL:
                ack = rng.random() < 0.3
            if beh in ("work", "auth") and plvl == PG.CRITICAL and last_out["hi"] >= node.limits()[1]:
                if dose_ack_at is None:
                    dose_ack_at = t + rng.randint(15, 40)
                if t >= dose_ack_at:
                    ack = True
                    dose_ack_at = None
                    reassigned = True
                    route, leaving = [], False
            if beh == "ignore" and plvl == PG.ESCALATED and ignore_ack_at is None:
                ignore_ack_at = t + 600                         # supervisor arrives 10 min later
            if beh == "ignore" and ignore_ack_at is not None and t >= ignore_ack_at and not leaving:
                ack, leaving = True, True
                route = [(pos[0], 100.0)]
                speed = 1.1
            out = node.step(t, fix, std, pitch, mq, rh, ack_pressed=ack, auth_press=auth)
            last_out = out
            lvl = out["level"]
            if beh == "comply" and lvl >= PG.WARNING and not leaving:
                leaving = True
                route = [(pos[0], 100.0)]                       # back to the road
                speed = 1.1
            if leaving and not route:
                leaving = False
                # after leaving, the remainder of this segment is spent on the road / next task
                segs[seg_i] = (s_, e_, "walk", "SHED", "work") if beh in ("comply", "ignore") else segs[seg_i]
            if out["changed"]:
                rows_alerts.append(dict(time=iso(t), worker=wid, from_level=PG.LEVELS[out["prev"]], to_level=PG.LEVELS[lvl],
                                        hazard_index=round(out["hi"], 4), zone=zone_name(out["zone_index"]),
                                        zone_state=out["zone_code"], rei_min_left=out["rei_min_left"]))
            lat, lon = from_xy(fx, fy)
            tlat, tlon = from_xy(*pos)
            raw.append([iso(t), round(lat, 7), round(lon, 7), round(hdop, 1), sats,
                        int(ax * 1000), int(ay * 1000), int(az * 1000), int(std * 1000), round(temp, 1), round(rh, 1), mq, vcc,
                        PG.ACT_NAME[out["act"]], PG.LEVELS[lvl], round(out["hi"], 5), out["zone_code"], out["rei_min_left"],
                        int(out["authorised"])])
            truth.append([iso(t), round(tlat, 7), round(tlon, 7), true_plot, PG.ACT_NAME[true_act], place, beh,
                          ",".join(z.zid for z in ZONES if z.active(t) and PG.point_in_poly(pos[0], pos[1], z.poly))])
            win.append((lat, lon, hdop, sats, ax, ay, az, std, temp, rh, mq, vcc, out))
            if len(win) == 5:
                rows.append(window_row(t, win))
                win = []
        days_out["raw"][(wid, day)] = raw
        days_out["truth"][(wid, day)] = truth
        days_out["win"].setdefault(wid, []).extend(rows)
        days_out["dose"].append(dict(date=str((D0 + timedelta(days=day)).date()), worker=wid,
                                     **{p: round(v, 6) for p, v in node.dose.items()},
                                     hazard_index=round(node.hi(), 4)))


def window_row(t, win):
    """One 5-second summary window (what the dashboard and analysis use)."""
    last = win[-1]
    mean = lambda i: sum(r[i] for r in win) / len(win)
    std_acc = math.sqrt(mean(7) ** 2)  # mean of per-second std
    levels = [r[12]["level"] for r in win]
    o = last[12]
    return [iso(t), round(last[0], 7), round(last[1], 7), round(last[2], 1), last[3],
            int(mean(4) * 1000), int(mean(5) * 1000), int(mean(6) * 1000), int(std_acc * 1000),
            round(mean(8), 1), round(mean(9), 1), round(mean(10), 1), max(r[10] for r in win), int(mean(11)),
            PG.ACT_NAME[o["act"]], PG.LEVELS[max(levels)], PG.LEVELS[o["level"]], round(o["hi"], 5), o["zone_code"],
            o["rei_min_left"], int(o["authorised"]), int(o["uncertain"])]


def iso(t):
    return datetime.fromtimestamp(t, IST).strftime("%Y-%m-%dT%H:%M:%S")


def from_xy(x, y):
    return LAT0 + y / PG.M_PER_DEG_LAT, LON0 + x / (111320.0 * math.cos(math.radians(LAT0)))


def zone_name(i):
    return ZONES[i].zid if i >= 0 else ""


# ------------------------------------------------------------------ write
def main():
    out = dict(raw={}, truth={}, win={}, alerts=[], dose=[])
    for wid in WORKERS:
        simulate_worker(wid, out)
        print("simulated", wid)
    for sub in ("farm", "sensor_windows_5s", "raw_1hz", "ground_truth", "outputs"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)

    def wcsv(path, header, rows):
        with open(os.path.join(OUT, path), "w", newline="") as f:
            cw = csv.writer(f)
            cw.writerow(header)
            cw.writerows(rows)

    # farm
    feats = []
    prow = []
    for pid, (crop, poly) in PLOTS.items():
        ll = [from_xy(x, y) for x, y in poly]
        feats.append({"type": "Feature", "properties": {"plot_id": pid, "crop": crop},
                      "geometry": {"type": "Polygon", "coordinates": [[[round(lo, 7), round(la, 7)] for la, lo in ll + [ll[0]]]]}})
        prow.append([pid, crop, ";".join(f"{la:.7f} {lo:.7f}" for la, lo in ll)])
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(OUT, "farm", "plots.geojson"), "w"), indent=1)
    wcsv("farm/plots.csv", ["plot_id", "crop", "polygon_lat_lon"], prow)
    wcsv("farm/landmarks.csv", ["name", "lat", "lon"], [["shed", *map(lambda v: round(v, 7), from_xy(*SHED))],
                                                       ["diesel_pump", *map(lambda v: round(v, 7), from_xy(*PUMP))]])
    wcsv("pesticides.csv", ["product_id", "name", "rei_h", "aoel_mg_per_kg_day", "dermal_absorption", "dt50_days", "dfr0_ug_cm2_per_kg_ha", "note"],
         [[p, c["name"], c["rei_h"], c["aoel"], c["da"], c["dt50_d"], c["dfr0"], "ILLUSTRATIVE - replace with label/CIB&RC/EFSA values"] for p, c in CATALOGUE.items()])
    wcsv("spray_records.csv", ["spray_id", "plot_id", "products", "application_end", "rate_kg_ai_ha", "applicator", "zone_rei_h", "rei_ends"],
         [[s, pl, "+".join(pr), iso(te), r, ap, z.rei_h, iso(z.rei_end)] for (s, pl, pr, te, r, ap), z in zip(SPRAYS, ZONES)])
    wcsv("workers.csv", ["worker_id", "role", "body_weight_kg", "ppe_penetration_factor", "vulnerable_flag", "device_id"],
         [[k, v["role"], v["bw"], v["ppe"], int(v["vulnerable"]), f"PG-{i + 1:02d}"] for i, (k, v) in enumerate(WORKERS.items())])
    wcsv("early_entry_authorisations.csv", ["date", "worker_id", "spray_id", "reason", "ppe_confirmed", "duration_min"],
         [["2026-10-09", "W04", "S6", "Irrigation pipe burst", "coverall, nitrile gloves, boots", 60]])
    wcsv("weather_hourly.csv", ["time", "temp_c", "rh_pct"],
         [[iso(T(d, h)), *[round(v, 1) for v in weather(T(d, h))]] for d in range(7) for h in range(24)])

    winh = ["time", "lat", "lon", "hdop", "sats", "acc_x_mg", "acc_y_mg", "acc_z_mg", "acc_sd_mg", "temp_c", "rh_pct",
            "mq135_mean", "mq135_max", "vcc_mv", "activity", "alert_max", "alert_last", "hazard_index", "zone_code",
            "rei_min_left", "authorised", "gnss_uncertain"]
    for wid, rows in out["win"].items():
        wcsv(f"sensor_windows_5s/{wid}.csv", winh, rows)
    rawh = ["time", "lat", "lon", "hdop", "sats", "acc_x_mg", "acc_y_mg", "acc_z_mg", "acc_sd_mg", "temp_c", "rh_pct",
            "mq135_raw", "vcc_mv", "activity", "alert_level", "hazard_index", "zone_code", "rei_min_left", "authorised"]
    for (wid, day), rows in out["raw"].items():
        name = f"raw_1hz/{wid}_{(D0 + timedelta(days=day)).date()}.csv.gz"
        with gzip.open(os.path.join(OUT, name), "wt", newline="") as f:
            cw = csv.writer(f)
            cw.writerow(rawh)
            cw.writerows(rows)
    for (wid, day), rows in out["truth"].items():
        name = f"ground_truth/{wid}_{(D0 + timedelta(days=day)).date()}.csv.gz"
        with gzip.open(os.path.join(OUT, name), "wt", newline="") as f:
            cw = csv.writer(f)
            cw.writerow(["time", "true_lat", "true_lon", "true_plot", "true_activity", "task_place", "behaviour", "inside_active_spray"])
            cw.writerows(rows)
    keys = ["time", "worker", "from_level", "to_level", "hazard_index", "zone", "zone_state", "rei_min_left"]
    wcsv("outputs/alerts.csv", keys, [[r[k] for k in keys] for r in sorted(out["alerts"], key=lambda r: (r["time"], r["worker"]))])
    dk = ["date", "worker"] + list(CATALOGUE) + ["hazard_index"]
    wcsv("outputs/daily_dose.csv", dk, [[r[k] for k in dk] for r in out["dose"]])
    print("written to", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
