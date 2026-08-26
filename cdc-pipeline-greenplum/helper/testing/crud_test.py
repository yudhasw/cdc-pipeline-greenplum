"""Demonstrasi CRUD end-to-end: cutidev (source) -> CDC -> Greenplum (target).

Melakukan CREATE, UPDATE, DELETE satu baris test di cutidev, lalu polling
tabel target Greenplum untuk lihat kapan tiap perubahan itu benar-benar
sampai - jadi ada bukti nyata + angka latensi per jenis operasi.

Jalankan di dalam container cdc-service (butuh config.py, psycopg2):
    docker cp helper/testing/crud_test.py cdc-service:/app/crud_test.py
    docker exec cdc-service python3 /app/crud_test.py
"""

import time
import psycopg2
import config

TAG = "[CRUD-TEST]"
POLL_INTERVAL = 0.5  # detik
POLL_TIMEOUT = 60  # detik


def src_conn():
    return psycopg2.connect(
        host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DATABASE,
        user=config.PG_USER, password=config.PG_PASSWORD, connect_timeout=10,
    )


def tgt_conn():
    return psycopg2.connect(
        host=config.TARGET_HOST, port=config.TARGET_PORT, dbname=config.TARGET_DATABASE,
        user=config.TARGET_USER, password=config.TARGET_PASSWORD, connect_timeout=10,
    )


def wait_until(check_fn, label):
    """Polling sampai check_fn() True atau timeout, kembalikan waktu tunggu (detik)."""
    start = time.time()
    while time.time() - start < POLL_TIMEOUT:
        if check_fn():
            elapsed = time.time() - start
            print(f"  -> {label}: TERLIHAT di target setelah {elapsed:.2f}s")
            return elapsed
        time.sleep(POLL_INTERVAL)
    print(f"  -> {label}: TIMEOUT setelah {POLL_TIMEOUT}s, belum terlihat di target")
    return None


def main():
    schema = config.TARGET_SCHEMA
    src = src_conn()
    src.autocommit = True

    print("=" * 70)
    print("CRUD TEST: cutidev -> Debezium -> Kafka -> staging -> merge -> Greenplum")
    print("=" * 70)

    # ---- CREATE ----
    print("\n[CREATE] Insert baris baru di cutidev.leave_leavedocument...")
    with src.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leave_leavedocument
                (created, document_type, need_trip_period, leaving_reason, status,
                 max_step, cur_step, is_admin_approve_to_cancel, user_id, role_id)
            VALUES (now(), 'TEST_CDC', 1, %s, 'Draft', 1, 1, false, %s, %s)
            RETURNING id
            """,
            (f"{TAG} {time.time()}", 2065, 1),
        )
        row_id = cur.fetchone()[0]
    print(f"  id={row_id} dibuat di source")

    def check_created():
        tgt = tgt_conn()
        try:
            with tgt.cursor() as cur:
                cur.execute(
                    f"SELECT status FROM {schema}.leave_leavedocument WHERE id = %s",
                    (row_id,),
                )
                r = cur.fetchone()
                return r is not None
        finally:
            tgt.close()

    wait_until(check_created, "CREATE")

    # ---- UPDATE ----
    print(f"\n[UPDATE] Ubah status id={row_id} jadi 'Approved' di cutidev...")
    with src.cursor() as cur:
        cur.execute(
            "UPDATE leave_leavedocument SET status = %s WHERE id = %s",
            ("Approved", row_id),
        )

    def check_updated():
        tgt = tgt_conn()
        try:
            with tgt.cursor() as cur:
                cur.execute(
                    f"SELECT status FROM {schema}.leave_leavedocument WHERE id = %s",
                    (row_id,),
                )
                r = cur.fetchone()
                return r is not None and r[0] == "Approved"
        finally:
            tgt.close()

    wait_until(check_updated, "UPDATE")

    # ---- DELETE ----
    print(f"\n[DELETE] Hapus id={row_id} dari cutidev (hard delete)...")
    with src.cursor() as cur:
        cur.execute("DELETE FROM leave_leavedocument WHERE id = %s", (row_id,))

    def check_deleted():
        tgt = tgt_conn()
        try:
            with tgt.cursor() as cur:
                cur.execute(
                    f"SELECT 1 FROM {schema}.leave_leavedocument WHERE id = %s",
                    (row_id,),
                )
                r = cur.fetchone()
                return r is None
        finally:
            tgt.close()

    wait_until(check_deleted, "DELETE")

    src.close()
    print("\n" + "=" * 70)
    print(f"Selesai. id={row_id} sudah melalui siklus CREATE -> UPDATE -> DELETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
