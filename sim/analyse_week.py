"""
Analyse the one-week dataset and produce the results and black-and-white
figures used in IDF-B Section 8.

Usage:  python analyse_week.py [data_folder] [figure_folder]
        (defaults: ../data/week  and  ../data/week/figures)

When real hardware data is available, put it in the same folder layout
(sensor_windows_5s/, raw_1hz/, outputs/alerts.csv) and run this script again;
the ground-truth based metrics need a ground_truth/ folder (from a marked
walk test) and are skipped when it is missing.
"""
import csv, glob, gzip, json, math, os, sys
from collections import Counter, defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data", "week")
FIG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DATA, "figures")
os.makedirs(FIG, exist_ok=True)

plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 9, "axes.edgecolor": "black",
                     "axes.labelcolor": "black", "xtick.color": "black", "ytick.color": "black",
                     "axes.prop_cycle": plt.cycler(color=["black"]), "savefig.dpi": 200})
GREYS = ["#000000", "#555555", "#888888", "#aaaaaa", "#cccccc"]
STYLES = ["-", "--", "-.", ":", (0, (5, 1, 1, 1))]
MARKERS = ["o", "s", "^", "D", "v"]
HATCH = ["", "///", "...", "xxx", "\\\\\\"]
WORKERS = ["W01", "W02", "W03", "W04", "W05"]
LEVEL_NUM = {"SAFE": 0, "ADVISORY": 1, "WARNING": 2, "ACKED": 2.5, "CRITICAL": 3, "ESCALATED": 4}

R = {}


def rcsv(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt") as f:
        return list(csv.DictReader(f))


def ts(s):
    return datetime.fromisoformat(s).timestamp()


workers = {r["worker_id"]: r for r in rcsv(os.path.join(DATA, "workers.csv"))}
sprays = rcsv(os.path.join(DATA, "spray_records.csv"))
alerts = rcsv(os.path.join(DATA, "outputs", "alerts.csv"))
dose = rcsv(os.path.join(DATA, "outputs", "daily_dose.csv"))
win = {w: rcsv(os.path.join(DATA, "sensor_windows_5s", f"{w}.csv")) for w in WORKERS}
dates = sorted({r["date"] for r in dose})

# ------------------------------------------------------------ 1. data volume
R["dataset"] = dict(workers=len(workers), days_worked=len(dates), spray_events=len(sprays),
                    windows_5s=sum(len(v) for v in win.values()),
                    raw_1hz_rows=sum(len(rcsv(p)) for p in glob.glob(os.path.join(DATA, "raw_1hz", "*.csv.gz"))),
                    alert_transitions=len(alerts))
shift_s = {d: (9 * 3600 if datetime.fromisoformat(d).weekday() < 5 else 5 * 3600) for d in dates}
expected = len(workers) * sum(shift_s.values()) / 5
R["dataset"]["window_completeness_pct"] = round(100 * R["dataset"]["windows_5s"] / expected, 1)

# ------------------------------------------------------------ 2. ground truth metrics
gt_files = sorted(glob.glob(os.path.join(DATA, "ground_truth", "*.csv.gz")))
if gt_files:
    entries, detected, latencies, missed = [], 0, [], []
    false_warn = 0
    act_conf = defaultdict(Counter)
    pos_err = []
    rejected = total_fix = 0
    near_s = Counter()
    for gf in gt_files:
        wid, day = os.path.basename(gf)[:3], os.path.basename(gf)[4:14]
        truth = rcsv(gf)
        raw = rcsv(os.path.join(DATA, "raw_1hz", f"{wid}_{day}.csv.gz"))
        auth = [t for t, r in zip(truth, raw) if r["authorised"] == "1"]
        prev_in = ""
        lvl_prev = "SAFE"
        day_entries = []
        warn_times = []
        for t, r in zip(truth, raw):
            tt = ts(t["time"])
            if r["alert_level"] in ("WARNING", "CRITICAL", "ESCALATED") and lvl_prev in ("SAFE", "ADVISORY") and int(r["zone_code"]) % 10 == 2 and int(r["rei_min_left"]) >= 0:
                warn_times.append(tt)
            lvl_prev = r["alert_level"]
            if t["inside_active_spray"] and not prev_in and r["authorised"] != "1":
                day_entries.append((wid, tt))
            prev_in = t["inside_active_spray"]
            act_conf[t["true_activity"]][r["activity"]] += 1
            # position error in metres
            dy = (float(r["lat"]) - float(t["true_lat"])) * 110574
            dx = (float(r["lon"]) - float(t["true_lon"])) * 111320 * math.cos(math.radians(12.92))
            pos_err.append(math.hypot(dx, dy))
            total_fix += 1
            rejected += float(r["hdop"]) > 5
            if int(r["zone_code"]) >= 0 and int(r["zone_code"]) % 10 == 1:
                near_s[wid] += 1
        entries.extend(day_entries)
        for (w, te) in day_entries:
            hits = [x for x in warn_times if te - 10 <= x <= te + 60]
            if hits:
                detected += 1
                latencies.append(hits[0] - te)
            else:
                missed.append((w, datetime.fromtimestamp(te).isoformat()))
        for x in warn_times:
            if not any(x - 60 <= e[1] <= x + 10 for e in day_entries):
                false_warn += 1
    pos_err.sort()
    R["geofence"] = dict(true_entries=len(entries), detected=detected, missed=missed,
                         latency_s=sorted(latencies), median_latency_s=sorted(latencies)[len(latencies) // 2] if latencies else None,
                         false_entry_warnings=false_warn,
                         gnss_error_median_m=round(pos_err[len(pos_err) // 2], 2),
                         gnss_error_p95_m=round(pos_err[int(0.95 * len(pos_err))], 2),
                         fixes_rejected_pct=round(100 * rejected / total_fix, 2),
                         near_minutes={w: round(near_s[w] / 60, 1) for w in WORKERS})
    labels = ["rest", "walk", "hand"]
    conf = [[act_conf[a][b] for b in labels] for a in labels]
    acc = sum(conf[i][i] for i in range(3)) / sum(map(sum, conf))
    R["activity"] = dict(labels=labels, confusion_rows_true_cols_pred=conf, accuracy_pct=round(100 * acc, 1))

# ------------------------------------------------------------ 3. alerts
cnt = Counter((a["worker"], a["to_level"]) for a in alerts)
R["alerts"] = {w: {lvl: cnt[(w, lvl)] for lvl in ["ADVISORY", "WARNING", "CRITICAL", "ESCALATED", "ACKED"]} for w in WORKERS}
R["alert_list"] = [a for a in alerts if a["to_level"] in ("WARNING", "CRITICAL", "ESCALATED", "ACKED")]
adv_per_day = Counter(a["time"][:10] for a in alerts if a["to_level"] == "ADVISORY")
R["advisories_per_day"] = dict(sorted(adv_per_day.items()))

# ------------------------------------------------------------ 4. dose
R["daily_hi"] = {w: {r["date"]: float(r["hazard_index"]) for r in dose if r["worker"] == w} for w in WORKERS}
R["max_daily_hi"] = {w: max(v.values()) for w, v in R["daily_hi"].items()}
R["days_hi_over_warn"] = {w: sum(1 for d, v in R["daily_hi"][w].items() if v >= (0.25 if workers[w]["vulnerable_flag"] == "1" else 0.5)) for w in WORKERS}
# time inside treated plots: expired vs active
inside = defaultdict(lambda: [0, 0, 0])
for w in WORKERS:
    for r in win[w]:
        zc = int(r["zone_code"])
        if zc >= 0 and zc % 10 == 2:
            k = 0 if int(r["rei_min_left"]) < 0 else (2 if r["authorised"] == "1" else 1)
            inside[w][k] += 5
R["minutes_in_treated_plots"] = {w: dict(rei_expired=round(inside[w][0] / 60), rei_active_unauthorised=round(inside[w][1] / 60, 1),
                                         rei_active_authorised=round(inside[w][2] / 60, 1)) for w in WORKERS}

# ------------------------------------------------------------ 5. gas sensor
rain = [r for r in rcsv(os.path.join(DATA, "raw_1hz", "W03_2026-10-08.csv.gz")) if "13:30" <= r["time"][11:16] <= "15:45"]
if rain:
    pre = [r for r in rain if r["time"][11:16] < "13:48"]
    dur = [r for r in rain if "14:10" <= r["time"][11:16] <= "15:00"]
    m = lambda rows, k: sum(float(x[k]) for x in rows) / len(rows)
    comp = lambda rows: sum(float(x["mq135_raw"]) / (1 + 0.006 * (float(x["rh_pct"]) - 60)) for x in rows) / len(rows)
    R["gas_humidity"] = dict(rh_before=round(m(pre, "rh_pct"), 1), rh_rain=round(m(dur, "rh_pct"), 1),
                             raw_before=round(m(pre, "mq135_raw"), 1), raw_rain=round(m(dur, "mq135_raw"), 1),
                             raw_change_pct=round(100 * (m(dur, "mq135_raw") / m(pre, "mq135_raw") - 1), 1),
                             compensated_change_pct=round(100 * (comp(dur) / comp(pre) - 1), 1))

# ------------------------------------------------------------ figures (black and white)
# Fig A: farm map with plots, worker W03 track on Monday
plots = rcsv(os.path.join(DATA, "farm", "plots.csv"))
fig, ax = plt.subplots(figsize=(6.4, 4.2))
lat0, lon0 = 12.92, 79.13
toxy = lambda la, lo: ((lo - lon0) * 111320 * math.cos(math.radians(lat0)), (la - lat0) * 110574)
for i, p in enumerate(plots):
    pts = [toxy(*map(float, q.split())) for q in p["polygon_lat_lon"].split(";")]
    xs, ys = [a for a, _ in pts] + [pts[0][0]], [b for _, b in pts] + [pts[0][1]]
    ax.fill(xs, ys, facecolor="white", edgecolor="black", hatch=HATCH[i % 5], linewidth=1)
    cx, cy = sum(xs[:-1]) / len(pts), sum(ys[:-1]) / len(pts)
    ax.text(cx, cy, f"{p['plot_id']}\n{p['crop']}", ha="center", va="center", fontsize=8,
            bbox=dict(facecolor="white", edgecolor="none", pad=1))
tr = rcsv(os.path.join(DATA, "raw_1hz", "W03_2026-10-05.csv.gz"))
gt = rcsv(os.path.join(DATA, "ground_truth", "W03_2026-10-05.csv.gz")) if gt_files else []
xy = [toxy(float(r["lat"]), float(r["lon"])) for r in tr[::5]]
ax.plot([a for a, _ in xy], [b for _, b in xy], color="#555555", lw=0.6, label="W03 GNSS track, Mon 5 Oct")
ax.plot(185, 100, marker="s", color="black", ms=6, ls="none", label="Shed")
ax.plot(240, 100, marker="^", color="black", ms=6, ls="none", label="Diesel pump")
ax.set_aspect("equal")
ax.set_xlabel("East of farm origin (m)")
ax.set_ylabel("North of farm origin (m)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, fontsize=7, frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig01_farm_map.png"))
plt.close(fig)

# Fig B: daily hazard index per worker
fig, ax = plt.subplots(figsize=(6.4, 3.0))
for i, w in enumerate(WORKERS):
    ys = [R["daily_hi"][w].get(d, 0) for d in dates]
    ax.plot(range(len(dates)), ys, color="black", ls=STYLES[i], marker=MARKERS[i], ms=4, lw=1,
            label=w + (" (vulnerable)" if workers[w]["vulnerable_flag"] == "1" else ""))
ax.axhline(0.5, color="black", lw=0.8, ls=(0, (1, 2)))
ax.text(len(dates) - 0.9, 0.51, "HI warn 0.5", fontsize=7)
ax.axhline(0.25, color="#888888", lw=0.8, ls=(0, (1, 2)))
ax.text(len(dates) - 0.9, 0.26, "warn, vulnerable", fontsize=7, color="#555555")
ax.set_xticks(range(len(dates)))
ax.set_xticklabels([datetime.fromisoformat(d).strftime("%a %d") for d in dates])
ax.set_ylabel("Daily hazard index")
ax.legend(fontsize=7, ncol=3, loc="upper left")
ax.set_ylim(0, max(0.8, max(R["max_daily_hi"].values()) + 0.1))
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig02_daily_hi.png"))
plt.close(fig)

# Fig C: alert timeline for Monday W03 (ignored alerts) from 1 Hz data
fig, axs = plt.subplots(2, 1, figsize=(6.4, 3.6), sharex=True)
seg = [r for r in tr if "09:55" <= r["time"][11:16] <= "10:30"]
tt = [(ts(r["time"]) - ts(seg[0]["time"])) / 60 for r in seg]
axs[0].step(tt, [LEVEL_NUM[r["alert_level"]] for r in seg], where="post", color="black", lw=1.2)
axs[0].set_yticks([0, 1, 2, 2.5, 3, 4])
axs[0].set_yticklabels(["SAFE", "ADVISORY", "WARNING", "ACKED", "CRITICAL", "ESCALATED"], fontsize=7)
axs[0].set_title("W03, Monday 5 Oct, 09:55-10:30: entry into P2 during REI (alerts ignored)", fontsize=8)
if gt:
    gseg = [g for g in gt if "09:55" <= g["time"][11:16] <= "10:30"]
    axs[1].fill_between(tt, [1 if g["inside_active_spray"] else 0 for g in gseg], step="post", color="#cccccc", label="truly inside active zone")
axs[1].step(tt, [1 if int(r["zone_code"]) % 10 == 2 and int(r["zone_code"]) >= 0 else 0 for r in seg], where="post", color="black", lw=1, label="device: INSIDE")
axs[1].set_yticks([0, 1])
axs[1].set_yticklabels(["out", "in"])
axs[1].set_xlabel("Minutes from 09:55")
axs[1].legend(fontsize=7, loc="upper right")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig03_alert_timeline.png"))
plt.close(fig)

# Fig D: alerts per worker (stacked grey bars)
fig, ax = plt.subplots(figsize=(6.4, 2.8))
lv = ["ADVISORY", "WARNING", "CRITICAL", "ESCALATED"]
bottom = [0] * 5
for i, l in enumerate(lv):
    vals = [R["alerts"][w][l] for w in WORKERS]
    ax.bar(WORKERS, vals, bottom=bottom, color=["white", "#cccccc", "#888888", "black"][i], edgecolor="black", hatch=["//", "", "", ""][i], label=l)
    bottom = [b + v for b, v in zip(bottom, vals)]
ax.set_ylabel("Alerts raised in the week")
ax.legend(fontsize=7, ncol=4)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig04_alerts_per_worker.png"))
plt.close(fig)

# Fig E: GNSS error CDF and activity confusion
if gt_files:
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.8))
    n = len(pos_err)
    axs[0].plot(pos_err[::50], [i / n for i in range(0, n, 50)], color="black")
    axs[0].set_xlim(0, 20)
    axs[0].set_xlabel("GNSS position error (m)")
    axs[0].set_ylabel("Cumulative fraction")
    axs[0].grid(color="#dddddd", lw=0.5)
    c = R["activity"]["confusion_rows_true_cols_pred"]
    tot = [sum(r) for r in c]
    axs[1].imshow([[v / t for v in r] for r, t in zip(c, tot)], cmap="Greys", vmin=0, vmax=1)
    for i in range(3):
        for j in range(3):
            v = c[i][j] / tot[i]
            axs[1].text(j, i, f"{100 * v:.1f}%", ha="center", va="center", color="white" if v > 0.5 else "black", fontsize=8)
    axs[1].set_xticks(range(3))
    axs[1].set_xticklabels(labels)
    axs[1].set_yticks(range(3))
    axs[1].set_yticklabels(labels)
    axs[1].set_xlabel("Classified")
    axs[1].set_ylabel("True")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig05_gnss_activity.png"))
    plt.close(fig)

# Fig F: gas sensor on the rain day (raw vs humidity-compensated) for W03
if rain:
    fig, ax1 = plt.subplots(figsize=(6.4, 2.8))
    tt = [(ts(r["time"]) - ts(rain[0]["time"])) / 60 for r in rain][::10]
    ax1.plot(tt, [float(r["mq135_raw"]) for r in rain][::10], color="black", lw=0.8, label="MQ-135 raw")
    ax1.plot(tt, [float(r["mq135_raw"]) / (1 + 0.006 * (float(r["rh_pct"]) - 60)) for r in rain][::10], color="#777777", lw=0.8, ls="--", label="humidity-compensated")
    ax1.set_ylabel("ADC counts")
    ax1.set_xlabel("Minutes from 13:30, Thursday 8 Oct (rain 13:48-15:36)")
    ax2 = ax1.twinx()
    ax2.plot(tt, [float(r["rh_pct"]) for r in rain][::10], color="black", lw=0.6, ls=":", label="RH %")
    ax2.set_ylabel("Relative humidity (%)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=7, loc="lower center", ncol=3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig06_gas_humidity.png"))
    plt.close(fig)

# Fig G: minutes in treated plots, REI expired vs active
fig, ax = plt.subplots(figsize=(6.4, 2.6))
ex = [R["minutes_in_treated_plots"][w]["rei_expired"] for w in WORKERS]
ac = [R["minutes_in_treated_plots"][w]["rei_active_unauthorised"] for w in WORKERS]
au = [R["minutes_in_treated_plots"][w]["rei_active_authorised"] for w in WORKERS]
x = range(5)
ax.bar([i - 0.27 for i in x], ex, width=0.27, color="white", edgecolor="black", hatch="///", label="REI expired (allowed)")
ax.bar(list(x), ac, width=0.27, color="black", label="REI active, not authorised")
ax.bar([i + 0.27 for i in x], au, width=0.27, color="#999999", edgecolor="black", label="REI active, authorised early entry")
ax.set_yscale("symlog", linthresh=10)
for i in x:
    ax.text(i, ac[i] + 1, f"{ac[i]:g}", ha="center", fontsize=7)
ax.set_xticks(list(x))
ax.set_xticklabels(WORKERS)
ax.set_ylabel("Minutes in the week")
ax.legend(fontsize=7)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig07_time_in_treated_plots.png"))
plt.close(fig)

json.dump(R, open(os.path.join(DATA, "outputs", "week_results.json"), "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in R.items() if k not in ("alert_list",)}, indent=1, default=str))
