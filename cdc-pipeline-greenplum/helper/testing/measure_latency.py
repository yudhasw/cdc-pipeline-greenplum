"""Ukur latensi ujung-ke-ujung pipeline CDC: WAL cutidev -> Debezium -> Kafka
-> staging -> job merge -> terlihat di tabel target Greenplum.

Cara kerja: polling tabel target leave_leavedocument, cari baris bertanda
"[GEN-TEST]" (dari testing/generator.py) yang belum pernah terlihat
sebelumnya. Latensi dihitung dari __source_ts_ms (waktu commit WAL di
cutidev, ditangkap Debezium) sampai saat baris itu pertama kali terlihat di
sini - ini sudah mencakup seluruh pipeline, tidak perlu korelasi manual ke
log generator.

Jalankan bersamaan dengan generator.py di terminal terpisah.
"""

import os
import time
from datetime import datetime, timezone

import psycopg2

DSN = dict(
    host=os.environ.get("TARGET_HOST", "localhost"),
    port=int(os.environ.get("TARGET_PORT", "5432")),
    dbname=os.environ.get("TARGET_DATABASE", "cutidev_gp"),
    user=os.environ.get("TARGET_USER", "gpadmin"),
    password=os.environ.get("TARGET_PASSWORD", "WhpgPass123"),
)
TARGET_SCHEMA = os.environ.get("TARGET_SCHEMA", "public")

TAG = "[GEN-TEST]"
POLL_SECONDS = float(os.environ.get("POLL_INTERVAL", "2"))


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S.%f} | [latency] {msg}", flush=True)


def main():
    conn = psycopg2.connect(**DSN, connect_timeout=10)
    conn.autocommit = True
    seen = set()
    samples = []
    log(f"mulai polling tiap {POLL_SECONDS}s, cari baris '{TAG}%' baru di leave_leavedocument")
    try:
        while True:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, __source_ts_ms FROM leave_leavedocument "
                    "WHERE leaving_reason LIKE %s",
                    (f"{TAG}%",),
                )
                rows = cur.fetchall()

            now = time.time()
            new_rows = [(rid, ts) for rid, ts in rows if rid not in seen]
            for rid, ts_ms in new_rows:
                seen.add(rid)
                latency = now - (ts_ms / 1000.0)
                samples.append(latency)
                log(f"BARU id={rid} __source_ts_ms={ts_ms} latensi={latency:.2f}s")

            if samples and len(samples) % 5 == 0 and new_rows:
                avg = sum(samples) / len(samples)
                log(
                    f"ringkasan {len(samples)} sampel: "
                    f"min={min(samples):.2f}s max={max(samples):.2f}s avg={avg:.2f}s"
                )

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        if samples:
            avg = sum(samples) / len(samples)
            log(
                f"dihentikan. total {len(samples)} sampel: "
                f"min={min(samples):.2f}s max={max(samples):.2f}s avg={avg:.2f}s"
            )
        else:
            log("dihentikan, belum ada sampel")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
