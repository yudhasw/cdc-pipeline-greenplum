import time
import csv
import requests
import psycopg2
import config

DASHBOARD_URL = "http://dashboard:8080"
DEBEZIUM_URL = "http://debezium-connect:8083"
SOURCE_CONNECTOR = "cutidev-gp-poc-source"
PG_DSN = dict(
    host=config.PG_HOST,
    port=config.PG_PORT,
    dbname=config.PG_DATABASE,
    user=config.PG_USER,
    password=config.PG_PASSWORD,
)
SAMPLE_INTERVAL = 3  # detik
OUT_FILE = "/app/perf_samples.csv"


def snapshot(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT xact_commit, xact_rollback, blks_read, blks_hit "
        "FROM pg_stat_database WHERE datname=%s",
        (PG_DSN["dbname"],),
    )
    commit, rollback, blks_read, blks_hit = cur.fetchone()
    cur.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND application_name LIKE 'Debezium%%'",
        (PG_DSN["dbname"],),
    )
    debezium_conns = cur.fetchone()[0]
    return {
        "xact": commit + rollback,
        "blks_read": blks_read,
        "blks_hit": blks_hit,
        "debezium_conns": debezium_conns,
    }


def run_phase(conn, writer, phase_name, duration, t0):
    end_time = time.time() + duration
    prev = snapshot(conn)
    prev_time = time.time()
    while time.time() < end_time:
        time.sleep(SAMPLE_INTERVAL)
        now = time.time()
        cur = snapshot(conn)
        elapsed = now - prev_time
        tps = (cur["xact"] - prev["xact"]) / elapsed if elapsed > 0 else 0
        writer.writerow({
            "t": round(now - t0, 1),
            "phase": phase_name,
            "tps": round(tps, 3),
            "debezium_conns": cur["debezium_conns"],
            "blks_read": cur["blks_read"],
            "blks_hit": cur["blks_hit"],
        })
        print(f"  t={now - t0:6.1f}s | {phase_name:16} | TPS={tps:5.2f} | debezium_conns={cur['debezium_conns']}")
        prev = cur
        prev_time = now


def main():
    conn = psycopg2.connect(**PG_DSN, connect_timeout=10)
    conn.autocommit = True
    t0 = time.time()

    with open(OUT_FILE, "w", newline="") as f:
        fieldnames = ["t", "phase", "tps", "debezium_conns", "blks_read", "blks_hit"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        print("[Fase 1] Baseline (generator OFF), 60s...")
        run_phase(conn, writer, "baseline", 60, t0)
        f.flush()

        print("[Fase 2] Generator ON + CDC AKTIF (interval 0.2s, ~5 event/detik), 180s...")
        r = requests.post(f"{DASHBOARD_URL}/api/generator/start", params={"interval": 0.2}, timeout=10)
        print(f"  generator start response: {r.status_code}")
        run_phase(conn, writer, "generator_cdc_on", 180, t0)
        f.flush()

        print("[Fase 3] Generator ON + CDC DIPAUSE (rate sama), 180s...")
        r = requests.put(f"{DEBEZIUM_URL}/connectors/{SOURCE_CONNECTOR}/pause", timeout=10)
        print(f"  pause connector response: {r.status_code}")
        time.sleep(3)  # beri jeda connector benar-benar berhenti
        run_phase(conn, writer, "generator_cdc_off", 180, t0)
        f.flush()

        print("[Fase 4] Resume CDC, generator tetap ON, 60s (verifikasi catch-up)...")
        r = requests.put(f"{DEBEZIUM_URL}/connectors/{SOURCE_CONNECTOR}/resume", timeout=10)
        print(f"  resume connector response: {r.status_code}")
        run_phase(conn, writer, "generator_cdc_resumed", 60, t0)
        f.flush()

        print("[Fase 5] Generator OFF, 60s...")
        r = requests.post(f"{DASHBOARD_URL}/api/generator/stop", timeout=10)
        print(f"  generator stop response: {r.status_code}")
        run_phase(conn, writer, "generator_off", 60, t0)
        f.flush()

    conn.close()
    print(f"\nSelesai. Data tersimpan di {OUT_FILE}")


if __name__ == "__main__":
    main()
