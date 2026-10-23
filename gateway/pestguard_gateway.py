"""
PestGuard gateway: collects the data lines sent by the wearables and writes the files
the dashboard reads.

Each wearable prints one line per second on its serial port (USB cable or the ESP32 Bluetooth serial port):
    PG,worker,unix_time,lat_e6,lon_e6,hdop10,sats,acc_std_mg,pitch_deg,temp_c,rh_pct,mq135,
       level,hazard_index,zone_code,rei_min_left,activity,authorised,vcc_mv[,pos,rssi_dbm]
(pos: 0 GPS, 1 Wi-Fi beacons, 2 scripted walk; the last two fields are absent in older data.)

The link is two-way. The gateway sets the wearable's clock (TIME, on connect and every 30 s) and
forwards the commands that the dashboard appends to logs/outbox.txt, for example
    SPRAY,<zone>,<product bit mask>,<rate kg/ha>,<end of application unix s>
    CLEAR,<zone>
The wearable answers with lines starting "#OK," / "#ERR,", which are written to device_log.csv.

Real devices (one or more ports):
    python pestguard_gateway.py --port COM5                 (Windows)
    python pestguard_gateway.py --port /dev/ttyACM0 --port /dev/rfcomm0
Without hardware, replay recorded / synthetic 1 Hz files (same output):
    python pestguard_gateway.py --replay ../data/week/raw_1hz/W03_2026-10-05.csv.gz --speed 20 --start 09:50

Output folder (default ../logs):
    readings.csv     every line received, with the PC time
    alerts.csv       every change of alert level
    device_log.csv   replies from the wearables (#OK / #ERR) and commands sent
    live_state.json  latest line per worker and recent device replies (read by the dashboard)
"""
import argparse, csv, gzip, json, os, threading, time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
LEVELS = ["SAFE", "ADVISORY", "WARNING", "CRITICAL", "ESCALATED", "ACKED"]
FIELDS = ["worker", "unix_time", "lat_e6", "lon_e6", "hdop10", "sats", "acc_std_mg", "pitch_deg", "temp_c", "rh_pct",
          "mq135", "level", "hazard_index", "zone_code", "rei_min_left", "activity", "authorised", "vcc_mv", "pos", "rssi_dbm"]
N_OLD = 18                                          # lines without pos and rssi_dbm
ACT = {"rest": 0, "walk": 1, "hand": 2}


class Store:
    def __init__(self, out):
        os.makedirs(out, exist_ok=True)
        self.out, self.lock = out, threading.Lock()
        self.state, self.last_level, self.lines = {}, {}, 0
        new_r = not os.path.exists(os.path.join(out, "readings.csv"))
        new_a = not os.path.exists(os.path.join(out, "alerts.csv"))
        self.fr = open(os.path.join(out, "readings.csv"), "a", newline="")
        self.fa = open(os.path.join(out, "alerts.csv"), "a", newline="")
        self.wr, self.wa = csv.writer(self.fr), csv.writer(self.fa)
        if new_r:
            self.wr.writerow(["pc_time", "node_time"] + FIELDS)
        if new_a:
            self.wa.writerow(["pc_time", "node_time", "worker", "from_level", "to_level", "hazard_index", "zone_code", "rei_min_left"])
        self.t_state = 0
        new_d = not os.path.exists(os.path.join(out, "device_log.csv"))
        self.fd = open(os.path.join(out, "device_log.csv"), "a", newline="")
        self.wd = csv.writer(self.fd)
        if new_d:
            self.wd.writerow(["pc_time", "port", "direction", "line"])
        self.msgs = []

    def device(self, port, direction, line):
        now = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S")
        with self.lock:
            self.wd.writerow([now, port, direction, line]); self.fd.flush()
            self.msgs = (self.msgs + [dict(pc_time=now, port=port, direction=direction, line=line)])[-30:]
        print(f"[{now}] {port} {'->' if direction == 'sent' else '<-'} {line}")

    def add(self, vals):
        """vals: the fields after 'PG,' (18, or 20 with pos and rssi_dbm)"""
        if len(vals) == N_OLD:
            vals = vals + ["", ""]
        if len(vals) != len(FIELDS):
            return
        rec = dict(zip(FIELDS, vals))
        now = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            nt = datetime.fromtimestamp(int(rec["unix_time"]), IST).strftime("%Y-%m-%dT%H:%M:%S") if int(rec["unix_time"]) > 1e9 else ""
            lvl = int(rec["level"])
        except ValueError:
            return
        with self.lock:
            self.lines += 1
            self.wr.writerow([now, nt] + vals)
            w = rec["worker"]
            if self.last_level.get(w) != lvl:
                prev = self.last_level.get(w)
                self.wa.writerow([now, nt, w, LEVELS[prev] if prev is not None else "-", LEVELS[lvl], rec["hazard_index"], rec["zone_code"], rec["rei_min_left"]])
                self.fa.flush()
                print(f"[{nt or now}] {w}: {LEVELS[lvl]}  HI={float(rec['hazard_index']):.3f}")
                self.last_level[w] = lvl
            rec["level_name"], rec["node_time"], rec["pc_time"] = LEVELS[lvl], nt, now
            self.state[w] = rec
            if time.time() - self.t_state > 1:
                self.t_state = time.time()
                self.flush()

    def flush(self):
        self.fr.flush()
        tmp = os.path.join(self.out, "live_state.json.tmp")
        with open(tmp, "w") as f:
            json.dump(dict(updated=datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S"), lines=self.lines, workers=self.state,
                           device_msgs=self.msgs, ports=sorted(PORTS)), f)
        os.replace(tmp, os.path.join(self.out, "live_state.json"))


PORTS = {}                                          # open serial ports, for sending commands
PORTS_LOCK = threading.Lock()


def send(port, line, store):
    with PORTS_LOCK:
        s = PORTS.get(port)
    if s is None:
        return False
    try:
        s.write((line + "\n").encode())
        store.device(port, "sent", line)
        return True
    except Exception as e:
        store.device(port, "error", f"{line} ({e})")
        return False


def clock_and_outbox(out, store):
    """Sets the wearables' clocks and forwards dashboard commands from outbox.txt."""
    path = os.path.join(out, "outbox.txt")
    pos = os.path.getsize(path) if os.path.exists(path) else 0      # ignore commands from earlier runs
    t_time = 0
    while True:
        if time.time() - t_time >= 30:
            t_time = time.time()
            for p in list(PORTS):
                send(p, f"TIME,{int(time.time())}", store)
        if os.path.exists(path) and os.path.getsize(path) > pos:
            with open(path) as f:
                f.seek(pos)
                new = f.read()
                pos = f.tell()
            for line in new.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    for p in list(PORTS):
                        send(p, line, store)
        time.sleep(0.5)


def read_serial(port, baud, store):
    import serial                                   # pip install pyserial
    while True:
        try:
            s = serial.Serial(baudrate=baud, timeout=2)
            s.port = port
            s.dtr = False                           # do not reset the ESP32 when the port opens
            s.rts = False                           # (a reset would restart the gas baseline)
            s.open()
            with s:
                print("listening on", port)
                with PORTS_LOCK:
                    PORTS[port] = s
                send(port, f"TIME,{int(time.time())}", store)
                send(port, "PING", store)
                while True:
                    line = s.readline().decode(errors="replace").strip()
                    if line.startswith("PG,"):
                        store.add(line.split(",")[1:])
                    elif line.startswith("#OK") or line.startswith("#ERR"):
                        store.device(port, "received", line)
        except Exception as e:                      # unplugged, Bluetooth dropped: retry
            with PORTS_LOCK:
                PORTS.pop(port, None)
            print(f"{port}: {e}; retrying in 3 s")
            time.sleep(3)


def replay(path, speed, start, store):
    op = gzip.open if path.endswith(".gz") else open
    worker = os.path.basename(path)[:3]
    with op(path, "rt") as f:
        rows = [r for r in csv.DictReader(f) if not start or r["time"][11:16] >= start]
    t0 = time.time()
    for k, r in enumerate(rows):
        t = int(datetime.fromisoformat(r["time"]).replace(tzinfo=IST).timestamp())
        pitch = abs(__import__("math").degrees(__import__("math").asin(max(-1, min(1, int(r["acc_x_mg"]) / 1000)))))
        store.add([worker, str(t), str(round(float(r["lat"]) * 1e6)), str(round(float(r["lon"]) * 1e6)), str(int(float(r["hdop"]) * 10)),
                   r["sats"], r["acc_sd_mg"], f"{pitch:.1f}", r["temp_c"], r["rh_pct"], r["mq135_raw"], str(LEVELS.index(r["alert_level"])),
                   r["hazard_index"], r["zone_code"], r["rei_min_left"], str(ACT[r["activity"]]), r["authorised"], r["vcc_mv"]])
        d = t0 + (k + 1) / speed - time.time()
        if d > 0:
            time.sleep(d)
    print("replay finished:", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", action="append", default=[])
    ap.add_argument("--baud", type=int, default=57600)
    ap.add_argument("--replay", action="append", default=[])
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--start", default="")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs"))
    ap.add_argument("--seconds", type=float, default=0, help="stop after this many seconds (0 = run until Ctrl+C)")
    a = ap.parse_args()
    if not a.port and not a.replay:
        ap.error("give --port and/or --replay")
    store = Store(a.out)
    th = [threading.Thread(target=read_serial, args=(p, a.baud, store), daemon=True) for p in a.port]
    th += [threading.Thread(target=replay, args=(f, a.speed, a.start, store), daemon=True) for f in a.replay]
    if a.port:
        threading.Thread(target=clock_and_outbox, args=(a.out, store), daemon=True).start()
    for t in th:
        t.start()
    t_end = time.time() + a.seconds if a.seconds else None
    try:
        while any(t.is_alive() for t in th) and (t_end is None or time.time() < t_end):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    with store.lock:
        store.flush()
    print(f"gateway stopped; {store.lines} lines received")


if __name__ == "__main__":
    main()
