"""Skenario 1: CDC AKTIF. Generator menulis ke cutidev selama 5 menit, data
mengalir terus-menerus lewat Debezium -> Kafka -> staging -> merge -> Greenplum.
Rekam pg_stat_* di cutidev sepanjang waktu.

Jalankan di dalam container cdc-service:
    docker cp helper/testing/perf_common.py cdc-service:/app/perf_common.py
    docker cp helper/testing/poll_cdc_scenario.py cdc-service:/app/poll_cdc_scenario.py
    docker exec cdc-service python3 /app/poll_cdc_scenario.py
"""

import csv
import time

import requests

from perf_common import connect, snapshot

DASHBOARD_URL = "http://dashboard:8080"
SAMPLE_INTERVAL = 3  # detik
DURATION = 300  # 5 menit
OUT_FILE = "/app/run_cdc.csv"


def main():
    conn = connect()
    conn.autocommit = True

    print("Menyalakan generator (interval 0.2s, ~5 event/detik)...")
    r = requests.post(f"{DASHBOARD_URL}/api/generator/start", params={"interval": 0.2}, timeout=10)
    print(f"  start response: {r.status_code}")

    t0 = time.time()
    prev = snapshot(conn)
    prev_time = t0

    with open(OUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["t", "tps", "blks_read_rate", "seq_scan", "numbackends"])
        writer.writeheader()

        print(f"Merekam {DURATION}s sambil CDC mengalirkan data real-time...")
        while time.time() - t0 < DURATION:
            time.sleep(SAMPLE_INTERVAL)
            now = time.time()
            cur = snapshot(conn)
            elapsed = now - prev_time
            tps = (cur["xact"] - prev["xact"]) / elapsed if elapsed > 0 else 0
            blks_rate = (cur["blks_read"] - prev["blks_read"]) / elapsed if elapsed > 0 else 0
            writer.writerow({
                "t": round(now - t0, 1),
                "tps": round(tps, 3),
                "blks_read_rate": round(blks_rate, 2),
                "seq_scan": cur["seq_scan"],
                "numbackends": cur["numbackends"],
            })
            print(f"  t={now - t0:6.1f}s | TPS={tps:5.2f} | blks_read/s={blks_rate:7.1f} | "
                  f"seq_scan={cur['seq_scan']} | conns={cur['numbackends']}")
            prev, prev_time = cur, now
            f.flush()

    print("Mematikan generator...")
    r = requests.post(f"{DASHBOARD_URL}/api/generator/stop", timeout=10)
    print(f"  stop response: {r.status_code}")

    conn.close()
    print(f"\nSelesai. Data tersimpan di {OUT_FILE}")


if __name__ == "__main__":
    main()
