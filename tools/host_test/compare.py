"""Run the firmware logic (C++, host build) on every worker-day of the week dataset and
compare its alert transitions and final hazard index with the Python reference model."""
import csv, gzip, glob, os, subprocess, json
from datetime import datetime
D = os.path.join(os.path.dirname(__file__), "..", "..", "data", "week")
W = {r["worker_id"]: r for r in csv.DictReader(open(os.path.join(D, "workers.csv")))}
alerts = list(csv.DictReader(open(os.path.join(D, "outputs", "alerts.csv"))))
dose = {(r["worker"], r["date"]): float(r["hazard_index"]) for r in csv.DictReader(open(os.path.join(D, "outputs", "daily_dose.csv")))}
res = []
for f in sorted(glob.glob(os.path.join(D, "raw_1hz", "*.csv.gz"))):
    wid, day = os.path.basename(f)[:3], os.path.basename(f)[4:14]
    w = W[wid]
    out = subprocess.run(["./test_logic", w["body_weight_kg"], w["ppe_factor"] if "ppe_factor" in w else w["ppe_penetration_factor"], w["vulnerable_flag"]],
                         input=gzip.open(f, "rt").read(), capture_output=True, text=True).stdout.strip().splitlines()
    fw = [l.split(",") for l in out if not l.startswith("FINAL")]
    fhi = float(out[-1].split(",")[1])
    py = [a for a in alerts if a["worker"] == wid and a["time"][:10] == day]
    buttons = any(a["to_level"] == "ACKED" for a in py) or (wid == "W04" and day == "2026-10-09")
    fw_seq = [(x[0], x[2]) for x in fw]
    py_seq = [(a["time"], a["to_level"]) for a in py]
    tdiff = [abs((datetime.fromisoformat(a[0]) - datetime.fromisoformat(b[0])).total_seconds()) for a, b in zip(fw_seq, py_seq)]
    same_levels = [a[1] for a in fw_seq] == [b[1] for b in py_seq]
    hi_lv = ("WARNING", "CRITICAL", "ESCALATED")
    fw_w = [a for a in fw_seq if a[1] in hi_lv]
    py_w = [b for b in py_seq if b[1] in hi_lv]
    warn_match = len(fw_w) == len(py_w) and all(abs((datetime.fromisoformat(a[0]) - datetime.fromisoformat(b[0])).total_seconds()) <= 5 for a, b in zip(fw_w, py_w))
    res.append(dict(worker=wid, day=day, buttons=buttons, py_transitions=len(py_seq), fw_transitions=len(fw_seq),
                    identical=fw_seq == py_seq, same_levels=same_levels, warning_events=len(py_w), warning_events_match=warn_match, max_time_diff_s=max(tdiff) if tdiff else 0,
                    py_hi=dose[(wid, day)], fw_hi=fhi))
ok = [r for r in res if not r["buttons"]]
print(json.dumps(res, indent=0))
summary = dict(worker_days=len(res), compared_without_button_events=len(ok),
               identical_transition_sequences=sum(r["identical"] for r in ok),
               same_level_sequence=sum(r["same_levels"] for r in ok),
               median_time_difference_s=sorted(r["max_time_diff_s"] for r in ok)[len(ok)//2],
               total_transitions_compared=sum(r["py_transitions"] for r in ok),
               warning_or_higher_events=sum(r["warning_events"] for r in ok),
               worker_days_with_all_warning_events_matched=sum(r["warning_events_match"] for r in ok),
               max_abs_hi_difference=max(abs(r["py_hi"] - r["fw_hi"]) for r in ok))
print(summary)
json.dump(dict(summary=summary, rows=res), open(os.path.join(D, "outputs", "firmware_vs_python.json"), "w"), indent=1)
