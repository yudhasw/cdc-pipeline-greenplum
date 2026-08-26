"""Helper snapshot pg_stat_* untuk cutidev - dipakai poll_cdc_scenario.py dan
poll_batch_scenario.py supaya query metrik konsisten di kedua skenario.
"""

import psycopg2
import config

PG_DSN = dict(
    host=config.PG_HOST,
    port=config.PG_PORT,
    dbname=config.PG_DATABASE,
    user=config.PG_USER,
    password=config.PG_PASSWORD,
)


def connect():
    return psycopg2.connect(**PG_DSN, connect_timeout=10)


def snapshot(conn):
    """4 metrik: xact (buat hitung TPS), blks_read (buat hitung I/O rate),
    seq_scan (kumulatif, nunjukkin full table scan), numbackends (koneksi aktif)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT xact_commit, xact_rollback, blks_read, numbackends "
        "FROM pg_stat_database WHERE datname = %s",
        (PG_DSN["dbname"],),
    )
    xact_commit, xact_rollback, blks_read, numbackends = cur.fetchone()
    cur.execute(
        "SELECT seq_scan FROM pg_stat_user_tables WHERE relname = 'leave_leavedocument'"
    )
    row = cur.fetchone()
    return {
        "xact": xact_commit + xact_rollback,
        "blks_read": blks_read,
        "numbackends": numbackends,
        "seq_scan": row[0] if row else 0,
    }
