"""Deteksi perubahan struktur tabel sumber vs target - backend dipilih via
config.SCHEMA_BACKEND ("clickhouse" | "postgres").

Prinsip: DETEKSI otomatis, PENERAPAN manual - modul ini tidak pernah
menjalankan ALTER/DROP sendiri, kolom baru bisa saja PII yang justru harus
difilter, bukan dipetakan begitu saja.
"""

import json

import config
from checks.common import log


def get_backend():
    if config.SCHEMA_BACKEND == "clickhouse":
        from checks.schema.clickhouse_backend import ClickHouseSchemaBackend

        return ClickHouseSchemaBackend()
    elif config.SCHEMA_BACKEND == "postgres":
        from checks.schema.greenplum_backend import GreenplumSchemaBackend

        return GreenplumSchemaBackend()
    raise ValueError(f"SCHEMA_BACKEND tidak dikenal: {config.SCHEMA_BACKEND!r}")


def load_known_diff():
    """Muat selisih skema yang sudah pernah dilaporkan dari STATE_FILE.

    Mengembalikan dict kosong jika file belum ada atau rusak, sehingga
    siklus pertama selalu melaporkan baseline lengkap.
    """
    try:
        with open(config.STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_known_diff(state):
    """Simpan selisih skema terkini ke STATE_FILE agar tidak dilaporkan ulang."""
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_schema_drift():
    """Bandingkan struktur tabel sumber vs target dan laporkan selisihnya.

    Untuk setiap tabel di config.TABLES: kolom baru di sumber dilaporkan,
    kolom yang cuma ada di target dilaporkan sebagai kemungkinan DROP COLUMN
    di sumber. Selisih yang sama tidak dilaporkan dua kali (disimpan di
    STATE_FILE). Kegagalan jaringan hanya dicatat sebagai warning, tidak
    dianggap perubahan skema.
    """
    try:
        backend = get_backend()
    except Exception as e:
        log("schema", f"gagal siapkan backend ({config.SCHEMA_BACKEND}): {e}")
        return

    known_diff = load_known_diff()
    try:
        for table in config.TABLES:
            try:
                src_cols = backend.source_columns(table)
            except Exception as e:
                log("schema", f"[{table}] gagal baca skema sumber (jaringan?): {e}")
                continue  # jangan anggap kolom hilang cuma karena koneksi putus

            if not src_cols:
                log("schema", f"[{table}] tabel tidak ditemukan di sumber - lewati")
                continue

            try:
                tgt_cols = backend.target_columns(table)
            except Exception as e:
                log("schema", f"[{table}] gagal baca skema target: {e}")
                continue

            if not tgt_cols:
                log("schema", f"[{table}] belum ada tabel di target - lewati")
                continue

            new_in_src = sorted(set(src_cols) - set(tgt_cols))
            extra_in_tgt = sorted(
                set(tgt_cols) - set(src_cols) - set(config.PIPELINE_METADATA_COLUMNS)
            )
            current = {"new": new_in_src, "extra": extra_in_tgt}

            if current == known_diff.get(table):
                continue  # sudah pernah dilaporkan - diam

            if not new_in_src and not extra_in_tgt:
                log("schema", f"[{table}] skema sinkron")
            for col in new_in_src:
                col_type = src_cols[col]
                log(
                    "schema",
                    f"[{table}] KOLOM di sumber: {col} ({col_type}) - tidak ada di target",
                )
            for col in extra_in_tgt:
                log(
                    "schema",
                    f"[{table}] kolom {col} ada di target tapi tidak di sumber - "
                    f"kemungkinan DROP COLUMN di sumber",
                )

            known_diff[table] = current

        save_known_diff(known_diff)
    finally:
        backend.close()


# Alias untuk main.py
def schema_check():
    """Wrapper untuk check_schema_drift()."""
    return check_schema_drift()
