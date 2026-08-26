"""Merge job: pindahkan data dari tabel staging ke tabel target lewat pola
DELETE lalu INSERT dalam satu transaksi per tabel menangani upsert dan hard
delete tanpa RULE dan tanpa privilege DDL sama sekali (murni SELECT/INSERT/
DELETE).

- Fitur Snapshot Deleted Log (opsional, config.ENABLE_DELETED_LOG)
Sebelum baris dihapus fisik dari tabel target, snapshot terakhirnya disimpan ke
tabel deleted_log (kolom payload berupa jsonb) - hard delete di tabel utama
bikin baris benar-benar hilang tanpa jejak, padahal dashboard butuh tahu apa
saja yang baru dihapus (lihat GreenplumBackend.recent_deleted). deleted_log
menggantikan peran __deleted='true' yang dulu masih tersimpan di tabel utama
waktu masih pakai RULE (soft delete).

Bisa dimatikan lewat ENABLE_DELETED_LOG=false kalau target tidak menyediakan
tabel deleted_log sama sekali (keputusan pemilik database target, bukan
keterbatasan teknis) - hasilnya hard delete murni tanpa jejak apapun. Fitur
"baru dihapus" di dashboard otomatis tidak akan menampilkan apapun dalam
kondisi ini, karena memang tidak ada lagi sumber datanya.

- Fitur Auto-Evolve Table
Daftar kolom diambil dinamis dari information_schema.columns tabel target tiap
kali job jalan, bukan daftar statis - kolom baru yang sudah ter-auto.evolve ke
staging otomatis ikut termuat pada siklus berikutnya, selama kolom itu juga
sudah ada di tabel target. auto.evolve TIDAK diterapkan ke tabel target di
arsitektur ini (cuma ke staging, lewat sink connector) - kolom yang ada di
staging tapi belum ada di target diabaikan dengan log peringatan, bukan
di-ALTER otomatis, karena itu DDL dan modul ini tidak pernah menjalankan DDL.

- Guard __source_ts_ms terhadap target (to_apply)
Sebelum DELETE/INSERT ke target dan sebelum dicatat ke deleted_log, tiap baris
"latest" dari staging dicek dulu terhadap baris yang sudah ada di target: cuma
diterapkan kalau target belum punya baris itu, atau __source_ts_ms di staging
lebih baru dari yang tersimpan di target. Ini mencegah event yang datang
terlambat/redelivered menimpa data yang sudah lebih baru di target - tanpa ini
job tidak benar-benar idempoten terhadap urutan kedatangan event.

- DELETE selektif di staging, bukan TRUNCATE
TRUNCATE menghapus SELURUH isi staging pada saat itu juga, termasuk baris yang
kebetulan baru ditulis sink connector di sela-sela query merge berjalan (celah
antara query terakhir yang baca staging dan TRUNCATE dieksekusi) - baris itu
hilang permanen tanpa pernah ter-proses. Sebagai gantinya, cuma baris yang
id + __source_ts_ms-nya sudah benar-benar tercakup dalam "latest" batch ini
yang dihapus dari staging; baris yang nyelip masuk belakangan (id sama atau
beda) otomatis aman menunggu siklus berikutnya.

- Semua nama tabel ditulis lengkap dengan schema (config.TARGET_SCHEMA)
Sengaja TIDAK mengandalkan search_path. Dua alasan: (1) target bisa berada di
schema non-default (mis. uc_magang di Greenplum prod, bukan public), (2)
koneksi lewat PgBouncer membagi koneksi server antar sesi client, jadi
search_path yang di-set saat connect belum tentu ikut terbawa. Menulis nama
schema secara eksplisit membuat query selalu menunjuk tempat yang sama, tidak
peduli bagaimana koneksi itu didapat.
"""

import psycopg2

import config
from checks.common import log

STAGING_PREFIX = "stg_"


def _connect():
    return psycopg2.connect(
        host=config.TARGET_HOST,
        port=config.TARGET_PORT,
        dbname=config.TARGET_DATABASE,
        user=config.TARGET_USER,
        password=config.TARGET_PASSWORD,
        connect_timeout=config.HTTP_TIMEOUT,
    )


def _table_columns(cur, *tables):
    """Ambil kolom beberapa tabel sekaligus dalam satu round-trip.

    Mengembalikan list of set, urutannya mengikuti argumen `tables`.
    """
    cur.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name::text = ANY(%s)",
        (config.TARGET_SCHEMA, list(tables)),
    )
    found = {t: set() for t in tables}
    for table_name, column_name in cur.fetchall():
        if table_name in found:
            found[table_name].add(column_name)
    return [found[t] for t in tables]


def _merge_table(conn, table):
    schema = config.TARGET_SCHEMA
    staging = f"{STAGING_PREFIX}{table}"
    tgt = f"{schema}.{table}"
    stg = f"{schema}.{staging}"
    audit = f"{schema}.deleted_log"
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (stg,))
        if cur.fetchone()[0] is None:
            log("merge", f"[{table}] tabel staging {stg} belum ada, lewati")
            return

        cur.execute(f"""
            SELECT
                count(*),
                extract(epoch FROM (clock_timestamp() - to_timestamp(min(__source_ts_ms)/1000.0))),
                extract(epoch FROM (clock_timestamp() - to_timestamp(avg(__source_ts_ms)/1000.0))),
                extract(epoch FROM (clock_timestamp() - to_timestamp(max(__source_ts_ms)/1000.0)))
            FROM {stg}
        """)
        pending, lat_max, lat_avg, lat_min = cur.fetchone()
        if pending == 0:
            return

        target_cols, staging_cols = _table_columns(cur, table, staging)
        missing = staging_cols - target_cols - {"id"}
        if missing:
            log(
                "merge",
                f"[{table}] kolom {sorted(missing)} ada di staging tapi belum di "
                f"target - diabaikan sampai ada ALTER TABLE manual",
            )

        cols = sorted((target_cols & staging_cols) - {"id"})
        col_list = ", ".join(["id"] + cols)
        json_pairs = ", ".join(f"'{c}', {c}" for c in ["id"] + cols)

        latest_cte = f"""
            latest AS (
                SELECT DISTINCT ON (id) {col_list}
                FROM {stg}
                ORDER BY id, __source_ts_ms DESC
            )"""
        to_apply_cte = f"""
            to_apply AS (
                SELECT l.* FROM latest l
                LEFT JOIN {tgt} t ON t.id = l.id
                WHERE t.id IS NULL OR t.__source_ts_ms < l.__source_ts_ms
            )"""

        if config.ENABLE_DELETED_LOG:
            cur.execute(
                f"""
                WITH {latest_cte}, {to_apply_cte}
                INSERT INTO {audit} (table_name, id, deleted_at, payload)
                SELECT %s, id, __source_ts_ms, json_build_object({json_pairs})::jsonb
                FROM to_apply WHERE __deleted = 'true'
                """,
                (table,),
            )
            logged = cur.rowcount
        else:
            logged = 0

        cur.execute(f"""
            WITH {latest_cte}, {to_apply_cte}
            DELETE FROM {tgt} WHERE id IN (SELECT id FROM to_apply)
        """)
        deleted = cur.rowcount

        cur.execute(f"""
            WITH {latest_cte}, {to_apply_cte}
            INSERT INTO {tgt} ({col_list})
            SELECT {col_list} FROM to_apply WHERE __deleted = 'false'
        """)
        inserted = cur.rowcount

        cur.execute(f"""
            WITH {latest_cte}
            DELETE FROM {stg} s
            USING latest l
            WHERE s.id = l.id AND s.__source_ts_ms <= l.__source_ts_ms
        """)
        cleaned = cur.rowcount

        conn.commit()

        # lat_* NULL kalau __source_ts_ms kosong semua - jangan cetak "None".
        if lat_min is not None:
            latency_info = (
                f", latensi min={lat_min:.1f}s avg={lat_avg:.1f}s max={lat_max:.1f}s"
            )
        else:
            latency_info = ""

        log(
            "merge",
            f"[{table}] {pending} baris staging diproses, {cleaned} dibersihkan dari "
            f"staging, {deleted} baris lama dihapus, "
            f"{inserted} baris baru/update ditulis{latency_info}",
        )


def run_merge_job():
    conn = _connect()
    try:
        for table in config.TABLES:
            try:
                _merge_table(conn, table)
            except Exception as e:
                conn.rollback()
                log("merge", f"[{table}] gagal: {e}")
        log("merge", "siklus selesai, semua tabel diperiksa")
    finally:
        conn.close()


def run_vacuum():
    """VACUUM berkala untuk tabel target dan staging."""
    conn = _connect()
    conn.autocommit = True
    schema = config.TARGET_SCHEMA
    try:
        with conn.cursor() as cur:
            for table in config.TABLES:
                for t in (table, f"{STAGING_PREFIX}{table}"):
                    qualified = f"{schema}.{t}"
                    try:
                        cur.execute(f"VACUUM {qualified}")
                    except Exception as e:
                        log("vacuum", f"[{qualified}] gagal: {e}")
        log("vacuum", "siklus selesai")
    finally:
        conn.close()
