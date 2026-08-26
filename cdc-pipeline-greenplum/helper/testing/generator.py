"""Generator trafik uji untuk mengukur latensi pipeline CDC ujung-ke-ujung.

Menulis langsung ke cutidev (source asli, database dev bersama) - BUKAN
sandbox pribadi. Dibatasi sengaja:
- Cuma INSERT dan UPDATE, tidak ada DELETE (baris nyata bisa saja
  direferensikan tabel lain seperti leave_commentdocument, sudah pernah
  ketemu error itu; menghindari sepenuhnya lebih aman daripada validasi rumit
  per baris).
- Cuma menyentuh baris yang dia buat sendiri untuk UPDATE (tidak pernah
  menyentuh data asli tim lain).
- user_id=2065, role_id=1 - kombinasi yang sudah terbukti valid dan dipakai
  berulang untuk testing CDC sebelumnya (lihat riwayat leaving_reason
  "Testing greenplum" dkk pada baris-baris lama).
- Semua baris ditandai jelas lewat prefix "[GEN-TEST]" di leaving_reason,
  gampang dibedakan dari data asli dan gampang dibersihkan lewat
  DELETE FROM leave_leavedocument WHERE leaving_reason LIKE '[GEN-TEST]%'
- Rate rendah (default 5 detik/siklus) - tidak membebani database dev bersama.

Tiap aksi dicatat ke stdout dengan timestamp wall-clock, dipakai
measure_latency.py untuk menghitung jeda sampai baris itu terlihat di
Greenplum target.
"""

import os
import random
import time
from datetime import datetime, timezone

import psycopg2

# Kredensial sengaja tanpa nilai bawaan agar tidak ikut ter-commit.
DSN = dict(
    host=os.environ["PG_HOST"],
    port=int(os.environ.get("PG_PORT", "5432")),
    dbname=os.environ["PG_DATABASE"],
    user=os.environ["PG_USER"],
    password=os.environ["PG_PASSWORD"],
)

USER_ID = 2065
ROLE_ID = 1
TAG = "[GEN-TEST]"
INTERVAL_SECONDS = float(os.environ.get("GEN_INTERVAL", "5"))
STATUSES = ["On Progress", "Approved", "Rejected"]


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S.%f} | [gen] {msg}", flush=True)


def insert_row(cur):
    cur.execute(
        """
        INSERT INTO leave_leavedocument
            (created, document_type, need_trip_period, leaving_reason, status,
             max_step, cur_step, is_admin_approve_to_cancel, user_id, role_id)
        VALUES (now(), 'TEST_CDC', 1, %s, 'Draft', 1, 1, false, %s, %s)
        RETURNING id
        """,
        (f"{TAG} generator {datetime.now(timezone.utc).isoformat()}", USER_ID, ROLE_ID),
    )
    return cur.fetchone()[0]


def update_random_row(cur):
    cur.execute(
        "SELECT id FROM leave_leavedocument WHERE leaving_reason LIKE %s ORDER BY random() LIMIT 1",
        (f"{TAG}%",),
    )
    row = cur.fetchone()
    if row is None:
        return None
    row_id = row[0]
    new_status = random.choice(STATUSES)
    cur.execute(
        "UPDATE leave_leavedocument SET status = %s WHERE id = %s",
        (new_status, row_id),
    )
    return row_id, new_status


def main():
    conn = psycopg2.connect(**DSN, connect_timeout=10)
    conn.autocommit = True
    log(f"generator aktif, interval {INTERVAL_SECONDS}s, user_id={USER_ID} role_id={ROLE_ID}")
    tick = 0
    try:
        while True:
            tick += 1
            try:
                with conn.cursor() as cur:
                    new_id = insert_row(cur)
                    t_insert = time.time()
                    log(f"INSERT id={new_id} t={t_insert:.3f}")

                    if tick % 3 == 0:
                        result = update_random_row(cur)
                        if result:
                            upd_id, new_status = result
                            t_update = time.time()
                            log(f"UPDATE id={upd_id} status={new_status} t={t_update:.3f}")
            except Exception as e:
                log(f"gagal siklus: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log("dihentikan manual")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
