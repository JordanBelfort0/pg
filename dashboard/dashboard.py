"""
PestGuard supervisor dashboard (Streamlit).

    pip install -r requirements.txt
    streamlit run dashboard/dashboard.py

Views
  * Live                 status of every wearable, trends of the last minutes, alert log
  * Supervisor console   record a spray (sent to the wearables), end a restriction, REI countdowns,
                         test markers for bench tests, replies from the devices
  * Bench test results   numbers and figures from the real-hardware logs (tools/hw_results.py)
  * Week review          the one-week synthetic dataset (data/week)
The console writes commands to logs/outbox.txt; the gateway forwards them to the wearables.
"""
import csv, json, os, re, sys, time
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
IST = timezone(timedelta(hours=5, minutes=30))
LEVELS = ["SAFE", "ADVISORY", "WARNING", "CRITICAL", "ESCALATED", "ACKED"]
LEVEL_NOTE = {"SAFE": "No action", "ADVISORY": "Near a treated zone", "WARNING": "Inside a zone under REI, or dose high",
              "CRITICAL": "Still inside / dose limit - worker must leave", "ESCALATED": "No acknowledgement - go to the worker now",
              "ACKED": "Acknowledged"}
POS = {"0": "GPS", "1": "Wi-Fi beacons", "2": "scripted walk (simulated)", "": "-"}
ACT = ["rest", "walk", "hand"]

st.set_page_config(page_title="PestGuard dashboard", layout="wide")
st.sidebar.title("PestGuard")
VIEWS = ["Live", "Supervisor console", "Bench test results", "Week review"]
view = st.sidebar.radio("View", VIEWS, index=int(os.environ.get("PG_VIEW", "0")))
log_dir = st.sidebar.text_input("Gateway log folder", os.path.join(ROOT, "logs"))
data_dir = st.sidebar.text_input("Dataset folder", os.path.join(ROOT, "data", "week"))
os.makedirs(log_dir, exist_ok=True)


def now_ist():
    return datetime.now(IST)


def read_state():
    p = os.path.join(log_dir, "live_state.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p))
    except json.JSONDecodeError:
        return None


def products():
    return pd.read_csv(os.path.join(data_dir, "pesticides.csv"))


def n_zones():
    p = os.path.join(ROOT, "firmware", "pestguard_node", "zones_beacon.h")
    m = re.search(r"#define N_ZONES (\d+)", open(p).read()) if os.path.exists(p) else None
    return int(m.group(1)) if m else 2


def append_csv(name, header, row):
    p = os.path.join(log_dir, name)
    new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


def send_command(line):
    with open(os.path.join(log_dir, "outbox.txt"), "a") as f:
        f.write(line + "\n")


def recent_readings(worker, minutes):
    p = os.path.join(log_dir, "readings.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    size = os.path.getsize(p)
    with open(p) as f:                                   # read only the tail of a long file
        header = f.readline()
        if size > 3_000_000:
            f.seek(size - 3_000_000); f.readline()
        body = f.read()
    from io import StringIO
    d = pd.read_csv(StringIO(header + body))
    d = d[d["worker"] == worker]
    if d.empty:
        return d
    d["t"] = pd.to_datetime(d["pc_time"])
    return d[d["t"] >= d["t"].max() - pd.Timedelta(minutes=minutes)]


# ---------------------------------------------------------------- Live
if view == "Live":
    st.title("Live view")
    refresh = st.sidebar.slider("Refresh every (s)", 2, 30, 3)
    minutes = st.sidebar.slider("Trend window (minutes)", 2, 60, 10)

    @st.fragment(run_every=refresh)
    def live_panel():
        s = read_state()
        if not s:
            st.info("No live_state.json yet. Start the gateway with --port (real wearable) or --replay.")
            return
        st.caption(f"Last update {s['updated']}  ·  {s['lines']} data lines received  ·  ports: {', '.join(s.get('ports', [])) or 'replay'}")
        rows, pts = [], []
        for w, v in s["workers"].items():
            lvl = v["level_name"]
            zc, rei = int(v["zone_code"]), int(v["rei_min_left"])
            zone = "-" if zc < 0 else f"zone {zc // 10 + 1} ({'inside' if zc % 10 == 2 else 'near'})"
            rssi = v.get("rssi_dbm", "")
            rows.append(dict(worker=w, alert=lvl, action=LEVEL_NOTE.get(lvl, ""), hazard_index=float(v["hazard_index"]), zone=zone,
                             rei_left=("-" if rei < 0 else f"{rei // 60} h {rei % 60:02d} min"), activity=ACT[int(v["activity"])],
                             authorised="yes" if v["authorised"] == "1" else "", position=POS.get(str(v.get("pos", "")), "-"),
                             beacon_rssi=(f"{rssi} dBm" if rssi not in ("", "-127") else "-"), gas=int(v["mq135"]),
                             temp_c=float(v["temp_c"]), rh_pct=float(v["rh_pct"]), device_time=v["node_time"][11:] or "-",
                             supply_v=int(v["vcc_mv"]) / 1000))
            if int(v["lat_e6"]):
                pts.append(dict(lat=int(v["lat_e6"]) / 1e6, lon=int(v["lon_e6"]) / 1e6, worker=w))
        df = pd.DataFrame(rows).sort_values("worker")
        for _, r in df[df["alert"].isin(["CRITICAL", "ESCALATED"])].iterrows():
            st.error(f"{r['worker']}: {r['alert']} - {r['action']}")
        cols = st.columns(max(1, len(df)))
        for col, (_, r) in zip(cols, df.iterrows()):
            col.metric(r["worker"], r["alert"], f"HI {r['hazard_index']:.2f}", delta_color="off")
        st.dataframe(df, hide_index=True, width="stretch")
        if pts:
            st.map(pd.DataFrame(pts), latitude="lat", longitude="lon", size=6)
        w = st.selectbox("Trends for worker", sorted(s["workers"]), key="trend_w")
        d = recent_readings(w, minutes)
        if len(d):
            c1, c2 = st.columns(2)
            c1.caption("Alert level (0 SAFE ... 4 ESCALATED, 5 ACKED)"); c1.line_chart(d.set_index("t")[["level"]], height=180)
            c2.caption("Hazard index today"); c2.line_chart(d.set_index("t")[["hazard_index"]], height=180)
            c3, c4 = st.columns(2)
            c3.caption("Gas reading (counts) and humidity (%)"); c3.line_chart(d.set_index("t")[["mq135", "rh_pct"]], height=180)
            if "rssi_dbm" in d and pd.to_numeric(d["rssi_dbm"], errors="coerce").gt(-127).any():
                c4.caption("Strongest zone beacon (dBm)"); c4.line_chart(d.set_index("t")[["rssi_dbm"]].replace(-127, None), height=180)
            else:
                c4.caption("Movement (milli-g) and lean (degrees)"); c4.line_chart(d.set_index("t")[["acc_std_mg", "pitch_deg"]], height=180)
        ap = os.path.join(log_dir, "alerts.csv")
        if os.path.exists(ap):
            st.subheader("Alert log")
            st.dataframe(pd.read_csv(ap).iloc[::-1].head(200), hide_index=True, width="stretch")

    live_panel()

# ---------------------------------------------------------------- Console
elif view == "Supervisor console":
    st.title("Supervisor console")
    P = products()
    nz = n_zones()
    st.subheader("Record a spray")
    st.caption("The record is sent to every connected wearable. Each device works out the REI itself "
               "(the longest REI of the products in the tank mix) and starts the countdown.")
    with st.form("spray"):
        c1, c2, c3, c4 = st.columns([1, 3, 1, 2])
        zone = c1.selectbox("Zone", list(range(1, nz + 1)))
        labels = [f"{r.product_id} (REI {r.rei_h} h)" for r in P.itertuples()]
        chosen = c2.multiselect("Products in the tank", labels, default=labels[:1])
        rate = c3.number_input("Rate (kg/ha)", 0.05, 5.0, 0.5, 0.05)
        ago = c4.number_input("Application ended ... minutes ago", 0, 72 * 60, 0, 5)
        ok = st.form_submit_button("Record spray and send")
    if ok and chosen:
        idx = [labels.index(c) for c in chosen]
        mask = sum(1 << i for i in idx)
        t_end = int(time.time()) - int(ago) * 60
        rei = int(max(P.iloc[i]["rei_h"] for i in idx))
        send_command(f"SPRAY,{zone},{mask},{rate},{t_end}")
        append_csv("sprays.csv", ["pc_time", "zone", "products", "mask", "rate_kg_ha", "application_end", "rei_h_expected", "rei_ends"],
                   [now_ist().strftime("%Y-%m-%dT%H:%M:%S"), zone, "+".join(P.iloc[i]["product_id"] for i in idx), mask, rate,
                    datetime.fromtimestamp(t_end, IST).strftime("%Y-%m-%dT%H:%M:%S"), rei,
                    datetime.fromtimestamp(t_end + rei * 3600, IST).strftime("%Y-%m-%dT%H:%M:%S")])
        st.success(f"Sent: zone {zone}, {' + '.join(P.iloc[i]['product_id'] for i in idx)}; the device should reply with REI {rei} h.")
    c1, c2 = st.columns([1, 3])
    cz = c1.selectbox("End the restriction of zone", list(range(1, nz + 1)), key="clr")
    if c2.button("End restriction (CLEAR)"):
        send_command(f"CLEAR,{cz}")
        append_csv("sprays.csv", ["pc_time", "zone", "products", "mask", "rate_kg_ha", "application_end", "rei_h_expected", "rei_ends"],
                   [now_ist().strftime("%Y-%m-%dT%H:%M:%S"), cz, "CLEARED", 0, 0, "", 0, now_ist().strftime("%Y-%m-%dT%H:%M:%S")])
        st.info(f"Sent CLEAR for zone {cz}.")

    @st.fragment(run_every=3)
    def zones_and_replies():
        st.subheader("Zones")
        sp = os.path.join(log_dir, "sprays.csv")
        s = read_state() or {}
        msgs = s.get("device_msgs", [])
        if os.path.exists(sp):
            sr = pd.read_csv(sp)
            last = sr.groupby("zone").tail(1)
            rows = []
            for r in last.itertuples():
                if r.products == "CLEARED":
                    rows.append(dict(zone=r.zone, products="-", status="no restriction", rei_left="-", confirmed="-"))
                    continue
                left = (datetime.fromisoformat(r.rei_ends).replace(tzinfo=IST) - now_ist()).total_seconds()
                conf = [m for m in msgs if m["direction"] == "received" and m["line"].startswith(f"#OK,SPRAY,{r.zone},") and m["pc_time"] >= r.pc_time]
                rows.append(dict(zone=r.zone, products=r.products, status="REI running" if left > 0 else "REI over (residue still counted)",
                                 rei_left=(f"{int(left // 3600)} h {int(left % 3600 // 60):02d} min" if left > 0 else "-"),
                                 confirmed=(conf[-1]["line"].split(",")[-1] + f" ({conf[-1]['port']})") if conf else "waiting for device"))
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.caption("No spray recorded yet.")
        st.subheader("Messages to and from the wearables")
        if msgs:
            st.dataframe(pd.DataFrame(msgs[::-1]), hide_index=True, width="stretch")
        else:
            st.caption("No messages yet (the gateway must be running with --port).")

    zones_and_replies()

    st.subheader("Test markers (bench tests)")
    st.caption("Press a marker at the moment you cross into or out of a zone. tools/hw_results.py measures the delays against these.")
    s = read_state() or {"workers": {}}
    c = st.columns(4)
    wk = c[0].selectbox("Worker", sorted(s["workers"]) or ["W01"])
    mz = c[1].selectbox("Zone ", list(range(1, nz + 1)), key="mz")
    hdr = ["pc_time", "worker", "event", "zone", "note"]
    if c[2].button("Entered zone"):
        append_csv("markers.csv", hdr, [now_ist().strftime("%Y-%m-%dT%H:%M:%S"), wk, "entered", mz, ""]); st.toast("marked: entered")
    if c[3].button("Left zone"):
        append_csv("markers.csv", hdr, [now_ist().strftime("%Y-%m-%dT%H:%M:%S"), wk, "left", mz, ""]); st.toast("marked: left")
    note = st.text_input("Note (e.g. 'gas swab start', 'volunteer noticed alert')")
    if st.button("Add note") and note:
        append_csv("markers.csv", hdr, [now_ist().strftime("%Y-%m-%dT%H:%M:%S"), wk, "note", "", note]); st.toast("note added")

# ---------------------------------------------------------------- Results
elif view == "Bench test results":
    st.title("Bench test results (real hardware)")
    st.caption("Computed from the gateway logs and the test markers. These are measurements, not the synthetic week.")
    s = read_state() or {"workers": {}}
    wk = st.selectbox("Worker", sorted(s["workers"]) or ["W01"])
    if st.button("Compute results"):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import hw_results
        r, m = hw_results.load(log_dir, wk)
        res = hw_results.analyse(r, m)
        out = os.path.join(log_dir, "results"); os.makedirs(out, exist_ok=True)
        json.dump(res, open(os.path.join(out, "hw_results.json"), "w"), indent=1, default=str)
        open(os.path.join(out, "hw_results.md"), "w").write(hw_results.summary_md(res, wk))
        if len(r) > 1:
            hw_results.figures(r, m, out)
        st.markdown(hw_results.summary_md(res, wk))
        for f in ["fig_hw_timeline.png", "fig_hw_rssi.png"]:
            if os.path.exists(os.path.join(out, f)):
                st.image(os.path.join(out, f))
        st.caption(f"Saved in {os.path.abspath(out)}")

# ---------------------------------------------------------------- Week review
else:
    st.title("Week review - one week of synthetic wearable data")
    wpath = os.path.join(data_dir, "workers.csv")
    if not os.path.exists(wpath):
        st.warning("Dataset folder not found.")
        st.stop()
    workers = pd.read_csv(wpath)
    sprays = pd.read_csv(os.path.join(data_dir, "spray_records.csv"))
    dose = pd.read_csv(os.path.join(data_dir, "outputs", "daily_dose.csv"))
    alerts = pd.read_csv(os.path.join(data_dir, "outputs", "alerts.csv"))
    st.subheader("Spray records")
    st.dataframe(sprays, hide_index=True, width="stretch")
    st.subheader("Daily hazard index (sum over products of dose / AOEL)")
    st.line_chart(dose.pivot(index="date", columns="worker", values="hazard_index"))
    st.caption("Warning threshold 0.5 (0.25 for a worker flagged vulnerable). Parameters are illustrative.")
    st.subheader("Alerts raised (warning level and above)")
    st.dataframe(alerts[alerts["to_level"].isin(["WARNING", "CRITICAL", "ESCALATED", "ACKED"])], hide_index=True, width="stretch")
    st.subheader("Advisories per worker")
    st.bar_chart(alerts[alerts["to_level"] == "ADVISORY"].groupby("worker").size())
    st.subheader("Track of one worker-day")
    w = st.selectbox("Worker", workers["worker_id"])
    day = st.selectbox("Day", sorted(dose["date"].unique()))
    win = pd.read_csv(os.path.join(data_dir, "sensor_windows_5s", f"{w}.csv"))
    d = win[win["time"].str.startswith(day)]
    if len(d):
        st.map(d.iloc[::6], latitude="lat", longitude="lon", size=2)
        st.line_chart(d.set_index("time")[["hazard_index"]])
        st.line_chart(d.set_index("time")[["mq135_mean", "rh_pct"]])
    else:
        st.info("No data for this worker on this day (device not worn or day off).")
