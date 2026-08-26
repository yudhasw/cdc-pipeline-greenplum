"""Pre-flight check sebelum mengarahkan pipeline ke database target baru
(misal Greenplum prod) - murni baca + tes lewat transaksi yang SELALU
di-ROLLBACK, tidak pernah menulis apapun secara permanen ke target.

Uji yang dilakukan:
1. Konektivitas TCP dasar ke host:port.
2. Autentikasi (user/password benar).
3. SELECT version() - konfirmasi memang nyambung ke database yang benar.
4. Cek tabel target (leave_leavedocument, leave_historyleave, account_user)
   sudah ada atau belum, dan kalau sudah ada, berapa isinya - PENTING supaya
   tahu apakah bakal tabrakan dengan data yang sudah ada.
5. Tes privilege DDL: coba CREATE TABLE di dalam transaksi, lalu ROLLBACK -
   kalau berhasil sampai titik itu berarti DDL diizinkan, kalau error berarti
   DML-only (auto.create/auto.evolve tidak akan jalan, tabel harus dibuat
   manual oleh DBA).
6. Tes privilege DML: coba INSERT ke tabel target (kalau sudah ada) di dalam
   transaksi, lalu ROLLBACK - konfirmasi INSERT/kolom-kolomnya valid tanpa
   pernah benar-benar menyimpan apapun.

Jalankan dengan env var TARGET_HOST/TARGET_PORT/TARGET_DATABASE/TARGET_USER/
TARGET_PASSWORD diisi kredensial yang mau dites (bisa disalin dari
sink-connector.json / docker-compose.yml yang direncanakan).
"""

import os
import socket

import psycopg2

HOST = os.environ.get("TARGET_HOST", "")
PORT = int(os.environ.get("TARGET_PORT", "5432"))
DATABASE = os.environ.get("TARGET_DATABASE", "")
USER = os.environ.get("TARGET_USER", "")
PASSWORD = os.environ.get("TARGET_PASSWORD", "")

TABLES = ["leave_leavedocument", "leave_historyleave", "account_user"]


def ok(msg):
    print(f"  [OK] {msg}")


def fail(msg):
    print(f"  [GAGAL] {msg}")


def warn(msg):
    print(f"  [PERHATIAN] {msg}")


def check_tcp():
    print(f"1. Cek konektivitas TCP ke {HOST}:{PORT}")
    try:
        with socket.create_connection((HOST, PORT), timeout=8):
            ok("port terbuka, bisa dijangkau")
            return True
    except Exception as e:
        fail(f"tidak bisa konek: {e}")
        return False


def connect():
    print(f"2. Cek autentikasi & koneksi database '{DATABASE}'")
    try:
        conn = psycopg2.connect(
            host=HOST, port=PORT, dbname=DATABASE, user=USER, password=PASSWORD,
            connect_timeout=10,
        )
        ok("berhasil login")
        return conn
    except Exception as e:
        fail(f"gagal login/konek: {e}")
        return None


def check_version(conn):
    print("3. Cek versi database")
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        ok(cur.fetchone()[0])


def check_schema(conn):
    """Pastikan schema mana yang sebenarnya dipakai.

    Penting karena sink connector menulis tanpa prefix schema (jatuh ke
    search_path), sementara merge-job/merge.py hardcode 'public'. Kalau
    keduanya tidak resolve ke schema yang sama, sink akan menulis ke satu
    tempat dan merge job mencari di tempat lain - pipeline diam-diam tidak
    jalan tanpa error yang jelas.
    """
    print("4. Cek schema yang dipakai")
    with conn.cursor() as cur:
        cur.execute("SELECT current_schema(), current_user")
        current_schema, current_user = cur.fetchone()
        cur.execute("SHOW search_path")
        search_path = cur.fetchone()[0]
        cur.execute(
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema' "
            "ORDER BY nspname"
        )
        schemas = [r[0] for r in cur.fetchall()]

    print(f"     user        : {current_user}")
    print(f"     search_path : {search_path}")
    print(f"     schema aktif: {current_schema}")
    print(f"     schema ada  : {', '.join(schemas) if schemas else '(tidak ada)'}")

    if current_schema is None:
        fail("search_path tidak resolve ke schema manapun - sink connector tidak akan tahu harus menulis ke mana")
    elif current_schema == "public":
        ok("schema aktif 'public' - cocok dengan asumsi merge job, tidak perlu penyesuaian")
    else:
        warn(
            f"schema aktif '{current_schema}', BUKAN 'public' - merge job hardcode 'public', "
            f"perlu disamakan (pin schema di sink connector, atau ubah merge job ikut '{current_schema}')"
        )


def check_existing_tables(conn):
    print("5. Cek tabel target - sudah ada isinya atau belum")
    with conn.cursor() as cur:
        for t in TABLES:
            # Sengaja tanpa prefix schema: resolve lewat search_path, persis
            # cara sink connector nanti mencari/membuat tabelnya. Kalau di-hardcode
            # 'public' padahal search_path menunjuk schema lain, hasilnya bisa
            # "aman" palsu - tabel bentrok di schema sebenarnya jadi tidak terlihat.
            cur.execute("SELECT to_regclass(%s)", (t,))
            exists = cur.fetchone()[0] is not None
            if not exists:
                warn(f"{t}: BELUM ADA (auto.create yang akan membuatnya nanti, kalau DDL diizinkan)")
                continue
            cur.execute(f"SELECT count(*) FROM {t}")
            count = cur.fetchone()[0]
            if count > 0:
                warn(f"{t}: SUDAH ADA dan berisi {count} baris - CEK DULU apakah ini data yang perlu dipertahankan, jangan sampai tertimpa/tabrakan")
            else:
                ok(f"{t}: sudah ada tapi kosong (0 baris), aman")


def check_ddl_privilege(conn):
    print("6. Cek privilege DDL (CREATE TABLE) - dites lewat transaksi yang di-ROLLBACK")
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE __pipeline_preflight_probe (id int)")
        conn.rollback()
        ok("CREATE TABLE diizinkan - auto.create/auto.evolve bisa dipakai untuk staging")
    except Exception as e:
        conn.rollback()
        fail(f"CREATE TABLE ditolak ({e}) - DDL-only, tabel staging/target HARUS dibuat manual oleh DBA")


def check_dml_privilege(conn):
    print("7. Cek privilege DML (INSERT) ke leave_leavedocument - dites lewat transaksi yang di-ROLLBACK")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('leave_leavedocument')")
        if cur.fetchone()[0] is None:
            warn("tabel belum ada, lewati tes INSERT (akan dites otomatis setelah auto.create jalan)")
            return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO leave_leavedocument (id, created, document_type, "
                "need_trip_period, leaving_reason, status, max_step, cur_step, "
                "is_admin_approve_to_cancel, user_id, role_id) "
                "VALUES (-999999, now(), 'PREFLIGHT_TEST', 1, 'tes', 'Draft', 1, 1, false, 1, 1)"
            )
        conn.rollback()
        ok("INSERT diizinkan, kolom-kolom cocok")
    except Exception as e:
        conn.rollback()
        fail(f"INSERT gagal: {e}")


def main():
    print(f"=== Pre-flight check target: {USER}@{HOST}:{PORT}/{DATABASE} ===\n")
    if not check_tcp():
        return
    conn = connect()
    if conn is None:
        return
    try:
        check_version(conn)
        check_schema(conn)
        check_existing_tables(conn)
        check_ddl_privilege(conn)
        check_dml_privilege(conn)
    finally:
        conn.close()
    print("\nSelesai - tidak ada perubahan permanen yang ditulis ke database target.")


if __name__ == "__main__":
    main()
