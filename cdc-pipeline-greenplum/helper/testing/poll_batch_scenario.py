"""Skenario 2: BATCH ETL HARIAN. CDC dipause (simulasi "tidak ada CDC").
Generator menulis ke cutidev dengan rate SAMA seperti skenario CDC selama
5 menit, tapi data cuma numpuk di cutidev - baru di akhir, sekali saja,
dijalankan batch job: full SELECT dari cutidev lalu full reload ke Greenplum
(pola ETL harian klasik: kumpul sepanjang hari, load sekali malam hari).

Jalankan di dalam container cdc-service:
    docker cp helper/testing/perf_common.py cdc-service:/app/perf_common.py
    docker cp helper/testing/poll_batch_scenario.py cdc-service:/app/poll_batch_scenario.py
    docker exec cdc-service python3 /app/poll_batch_scenario.py
"""

import csv
import time

import psycopg2
import psycopg2.extras
import requests

import config
from perf_common import connect, snapshot

DASHBOARD_URL = "http://dashboard:8080"
DEBEZIUM_URL = "http://debezium-connect:8083"
SOURCE_CONNECTOR = "cutidev-gp-poc-source"
SAMPLE_INTERVAL = 3  # detik
COLLECT_DURATION = 300  # 5 menit akumulasi (CDC mati)
SETTLE_DURATION = 60  # amati sesudah batch dieksekusi
OUT_FILE = "/app/run_batch.csv"

TARGET_DSN = dict(
    host=config.TARGET_HOST, port=config.TARGET_PORT, dbname=config.TARGET_DATABASE,
    user=config.TARGET_USER, password=config.TARGET_PASSWORD,
)


def run_batch_etl(src_conn, sample_fn):
    """Simulasi batch ETL harian: full read source, full reload ke target.

    sample_fn sengaja hanya membungkus SELECT-nya - insert ke Greenplum tidak
    menyentuh source, kalau ikut terukur lonjakannya jadi terdilusi.
    """
    sample_fn("before_select")
    print("  [BATCH] Membaca seluruh leave_leavedocument dari cutidev...")
    with src_conn.cursor() as cur:
        cur.execute("SELECT * FROM leave_leavedocument")
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
    sample_fn("after_select")
    print(f"  [BATCH] {len(rows)} baris x {len(colnames)} kolom terbaca, reload ke Greenplum...")

    tgt = psycopg2.connect(**TARGET_DSN, connect_timeout=10)
    tgt.autocommit = False
    with tgt.cursor() as cur:
        col_defs = ", ".join(f'"{c}" text' for c in colnames)
        cur.execute(f"CREATE TABLE IF NOT EXISTS uc_magang.leave_leavedocument_batch_test ({col_defs})")
        cur.execute("TRUNCATE uc_magang.leave_leavedocument_batch_test")
        col_list = ", ".join(f'"{c}"' for c in colnames)
        str_rows = [[None if v is None else str(v) for v in row] for row in rows]
        print(f"  [BATCH] Bulk insert {len(str_rows)} baris (execute_values, batch 1000/round-trip)...")
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO uc_magang.leave_leavedocument_batch_test ({col_list}) VALUES %s",
            str_rows,
            page_size=1000,
        )
    tgt.commit()
    tgt.close()
    print(f"  [BATCH] Selesai, {len(rows)} baris di-reload ke target.")


def main():
    conn = connect()
    conn.autocommit = True

    print("Mem-pause CDC (Debezium) - simulasikan 'tidak ada CDC'...")
    r = requests.put(f"{DEBEZIUM_URL}/connectors/{SOURCE_CONNECTOR}/pause", timeout=10)
    print(f"  pause response: {r.status_code}")
    time.sleep(3)

    print("Menyalakan generator (interval 0.2s, sama seperti skenario CDC)...")
    r = requests.post(f"{DASHBOARD_URL}/api/generator/start", params={"interval": 0.2}, timeout=10)
    print(f"  start response: {r.status_code}")

    t0 = time.time()
    prev = snapshot(conn)
    prev_time = t0

    with open(OUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["t", "phase", "tps", "blks_read_rate", "seq_scan", "numbackends"]
        )
        writer.writeheader()

        def sample(phase):
            nonlocal prev, prev_time
            now = time.time()
            cur = snapshot(conn)
            elapsed = now - prev_time
            tps = (cur["xact"] - prev["xact"]) / elapsed if elapsed > 0 else 0
            blks_rate = (cur["blks_read"] - prev["blks_read"]) / elapsed if elapsed > 0 else 0
            writer.writerow({
                "t": round(now - t0, 1), "phase": phase,
                "tps": round(tps, 3), "blks_read_rate": round(blks_rate, 2),
                "seq_scan": cur["seq_scan"], "numbackends": cur["numbackends"],
            })
            print(f"  t={now - t0:6.1f}s | {phase:16} | TPS={tps:5.2f} | blks_read/s={blks_rate:7.1f} | "
                  f"seq_scan={cur['seq_scan']} | conns={cur['numbackends']}")
            prev, prev_time = cur, now
            f.flush()

        print(f"Mengumpulkan traffic {COLLECT_DURATION}s (data numpuk di cutidev, belum ada yang ke Greenplum)...")
        while time.time() - t0 < COLLECT_DURATION:
            time.sleep(SAMPLE_INTERVAL)
            sample("accumulating")

        print("Mematikan generator, menjalankan batch ETL...")
        requests.post(f"{DASHBOARD_URL}/api/generator/stop", timeout=10)
        run_batch_etl(conn, sample)

        print(f"Mengamati {SETTLE_DURATION}s setelah batch selesai...")
        settle_end = time.time() + SETTLE_DURATION
        while time.time() < settle_end:
            time.sleep(SAMPLE_INTERVAL)
            sample("settle")

    print("Resume CDC (Debezium) kembali ke kondisi normal...")
    r = requests.put(f"{DEBEZIUM_URL}/connectors/{SOURCE_CONNECTOR}/resume", timeout=10)
    print(f"  resume response: {r.status_code}")

    conn.close()
    print(f"\nSelesai. Data tersimpan di {OUT_FILE}")


if __name__ == "__main__":
    main()
