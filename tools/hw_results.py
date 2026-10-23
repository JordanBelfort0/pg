"""
Bench / field test results from the gateway logs (real hardware, not the synthetic week).

    python tools/hw_results.py [--logs logs] [--worker W01]

Reads logs/readings.csv, alerts.csv, markers.csv (test markers pressed on the dashboard:
"entered zone N", "left zone N") and writes logs/results/:
    hw_results.json   all numbers
    hw_results.md     a one-page summary for the IDF-B (Section 8.8) and the presentation
    fig_hw_timeline.png, fig_hw_rssi.png   black-and-white figures

Definitions
    entry delay   time from an "entered zone N" marker to the first WARNING-or-higher line that
                  shows the worker inside zone N (missed if none within 60 s). Negative = the device
                  reported the zone before the marker was pressed (beacon zones are not sharp-edged).
    exit delay    time from a "left zone N" marker to the first line not inside zone N
    false entry   a line that shows the worker inside an active zone while the markers say the
                  worker was outside it (10 s grace after each marker)
    line loss     1 - lines received / seconds covered
"""
import argparse, json, os
import pandas as pd

LEVELS = ["SAFE", "ADVISORY", "WARNING", "CRITICAL", "ESCALATED", "ACKED"]


def load(logs, worker):
    r = pd.read_csv(os.path.join(logs, "readings.csv"))
    r = r[r["worker"] == worker].copy()
    r["t"] = pd.to_datetime(r["pc_time"])
    r = r.sort_values("t").reset_index(drop=True)
    for c in ["level", "zone_code", "hazard_index", "rssi_dbm", "mq135", "vcc_mv", "activity", "rh_pct"]:
        if c in r:
            r[c] = pd.to_numeric(r[c], errors="coerce")
    mp = os.path.join(logs, "markers.csv")
    m = pd.read_csv(mp) if os.path.exists(mp) else pd.DataFrame(columns=["pc_time", "worker", "event", "zone", "note"])
    m = m[m["worker"] == worker].copy()
    m["t"] = pd.to_datetime(m["pc_time"])
    return r, m.sort_values("t").reset_index(drop=True)


def inside(r, zone):
    return r["zone_code"] == (zone - 1) * 10 + 2


def analyse(r, m):
    res = dict(lines=int(len(r)))
    if len(r) < 2:
        return res
    span = (r["t"].iloc[-1] - r["t"].iloc[0]).total_seconds() + 1
    res["seconds_covered"] = round(span)
    res["line_loss_pct"] = round(max(0.0, 100 * (1 - len(r) / span)), 2)
    entries, exits = [], []
    intervals = {}                                           # zone -> list of (t_in, t_out)
    for _, e in m.iterrows():
        z = int(e["zone"]) if pd.notna(e["zone"]) else 1
        if e["event"] == "entered":
            # from 15 s before the marker: the device may detect the zone before the person presses the marker
            after = r[(r["t"] >= e["t"] - pd.Timedelta(seconds=15)) & (r["t"] <= e["t"] + pd.Timedelta(seconds=60))]
            hit = after[inside(after, z) & (after["level"] >= 2)]
            entries.append(dict(time=str(e["t"]), zone=z, delay_s=None if hit.empty else round((hit["t"].iloc[0] - e["t"]).total_seconds(), 1)))
            intervals.setdefault(z, []).append([e["t"], None])
        elif e["event"] == "left":
            after = r[(r["t"] >= e["t"]) & (r["t"] <= e["t"] + pd.Timedelta(seconds=120))]
            hit = after[~inside(after, z)]
            exits.append(dict(time=str(e["t"]), zone=z, delay_s=None if hit.empty else round((hit["t"].iloc[0] - e["t"]).total_seconds(), 1)))
            if intervals.get(z) and intervals[z][-1][1] is None:
                intervals[z][-1][1] = e["t"]
    res["entries"], res["exits"] = entries, exits
    d = [x["delay_s"] for x in entries if x["delay_s"] is not None]
    res["entries_detected"] = f"{len(d)} of {len(entries)}"
    if d:
        res["entry_delay_s"] = dict(median=float(pd.Series(d).median()), max=float(max(d)), min=float(min(d)))
    dx = [x["delay_s"] for x in exits if x["delay_s"] is not None]
    if dx:
        res["exit_delay_s"] = dict(median=float(pd.Series(dx).median()), max=float(max(dx)))
    # false entries: inside lines outside every marked interval (10 s grace)
    false_s = 0
    if len(m):
        grace = pd.Timedelta(seconds=10)
        for z in sorted(set(int(x) for x in m["zone"].dropna())):
            ok = pd.Series(False, index=r.index)
            for a, b in intervals.get(z, []):
                b = b if b is not None else r["t"].iloc[-1]
                ok |= (r["t"] >= a - grace) & (r["t"] <= b + grace)
            false_s += int((inside(r, z) & ~ok).sum())
        res["false_inside_seconds"] = false_s
    tr = r[r["level"].diff().fillna(0) != 0]
    res["alert_changes"] = [dict(time=str(x["t"]), to=LEVELS[int(x["level"])], hi=float(x["hazard_index"])) for _, x in tr.iterrows()]
    if "rssi_dbm" in r and r["rssi_dbm"].notna().any():
        rr = r[r["rssi_dbm"] > -127]
        res["rssi_dbm"] = dict(inside_median=float(rr[rr["zone_code"] % 10 == 2]["rssi_dbm"].median()) if (rr["zone_code"] % 10 == 2).any() else None,
                               outside_median=float(rr[rr["zone_code"] < 0]["rssi_dbm"].median()) if (rr["zone_code"] < 0).any() else None)
    v = r["vcc_mv"].dropna()
    if len(v):
        res["supply_mv"] = dict(first=int(v.iloc[0]), last=int(v.iloc[-1]), min=int(v.min()))
    res["hazard_index_end"] = float(r["hazard_index"].iloc[-1])
    res["gas_counts"] = dict(median=float(r["mq135"].median()), max=float(r["mq135"].max()))
    return res


def figures(r, m, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    t = (r["t"] - r["t"].iloc[0]).dt.total_seconds() / 60
    fig, ax = plt.subplots(3, 1, figsize=(7, 5.2), sharex=True)
    ax[0].step(t, r["level"], where="post", color="black", lw=1.2)
    ax[0].set_yticks(range(6)); ax[0].set_yticklabels(LEVELS, fontsize=7); ax[0].set_ylabel("Alert")
    ax[1].plot(t, r["hazard_index"], color="black", lw=1.2); ax[1].set_ylabel("Hazard index")
    a2 = ax[2]; a2.plot(t, r["mq135"], color="black", lw=0.8, label="gas (counts)"); a2.set_ylabel("Gas")
    if "rssi_dbm" in r and r["rssi_dbm"].notna().any():
        a3 = a2.twinx(); a3.plot(t, r["rssi_dbm"].where(r["rssi_dbm"] > -127), color="gray", ls="--", lw=0.9); a3.set_ylabel("RSSI (dBm)", color="gray")
    for _, e in m.iterrows():
        x = (e["t"] - r["t"].iloc[0]).total_seconds() / 60
        for a in ax:
            a.axvline(x, color="black", ls=":", lw=0.8)
        ax[0].text(x, 5.3, f"{e['event']} {int(e['zone']) if pd.notna(e['zone']) else ''}", rotation=90, fontsize=6, va="top")
    ax[2].set_xlabel("Minutes from start of the log")
    fig.tight_layout(); fig.savefig(os.path.join(out, "fig_hw_timeline.png"), dpi=200); plt.close(fig)
    if "rssi_dbm" in r and r["rssi_dbm"].notna().any():
        fig, a = plt.subplots(figsize=(5, 3))
        rr = r[r["rssi_dbm"] > -127]
        groups = [rr[rr["zone_code"] % 10 == 2]["rssi_dbm"], rr[rr["zone_code"] % 10 == 1]["rssi_dbm"], rr[rr["zone_code"] < 0]["rssi_dbm"]]
        a.boxplot([g.dropna() for g in groups], medianprops=dict(color="black"))
        a.set_xticks([1, 2, 3]); a.set_xticklabels(["inside", "near", "outside"])
        a.set_ylabel("Strongest beacon RSSI (dBm)"); fig.tight_layout(); fig.savefig(os.path.join(out, "fig_hw_rssi.png"), dpi=200); plt.close(fig)


def summary_md(res, worker):
    L = [f"# PestGuard bench test results ({worker})", "",
         "Measured on the real wearable through the gateway logs. Not synthetic data.", "",
         "| Measure | Result |", "|---|---|",
         f"| Lines received / seconds covered | {res.get('lines')} / {res.get('seconds_covered', '-')} |",
         f"| Line loss | {res.get('line_loss_pct', '-')} % |",
         f"| Zone entries detected | {res.get('entries_detected', '-')} |"]
    if "entry_delay_s" in res:
        e = res["entry_delay_s"]; L.append(f"| Entry delay (median / max) | {e['median']} s / {e['max']} s |")
    if "exit_delay_s" in res:
        e = res["exit_delay_s"]; L.append(f"| Exit delay (median / max) | {e['median']} s / {e['max']} s |")
    L.append(f"| Seconds wrongly shown inside | {res.get('false_inside_seconds', '-')} |")
    if res.get("rssi_dbm"):
        L.append(f"| RSSI inside / outside (median) | {res['rssi_dbm']['inside_median']} / {res['rssi_dbm']['outside_median']} dBm |")
    if res.get("supply_mv"):
        L.append(f"| Supply voltage first / last / min | {res['supply_mv']['first']} / {res['supply_mv']['last']} / {res['supply_mv']['min']} mV |")
    L.append(f"| Hazard index at end | {res.get('hazard_index_end', 0):.3f} |")
    L += ["", "Alert changes:", ""] + [f"- {a['time'][11:19]}  {a['to']}  (HI {a['hi']:.3f})" for a in res.get("alert_changes", [])]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs"))
    ap.add_argument("--worker", default="W01")
    a = ap.parse_args()
    r, m = load(a.logs, a.worker)
    out = os.path.join(a.logs, "results"); os.makedirs(out, exist_ok=True)
    res = analyse(r, m)
    json.dump(res, open(os.path.join(out, "hw_results.json"), "w"), indent=1, default=str)
    open(os.path.join(out, "hw_results.md"), "w").write(summary_md(res, a.worker))
    if len(r) > 1:
        figures(r, m, out)
    print(summary_md(res, a.worker))
    print("written to", os.path.abspath(out))


if __name__ == "__main__":
    main()
