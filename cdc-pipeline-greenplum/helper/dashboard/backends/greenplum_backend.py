import psycopg2
import psycopg2.extras
import config
from backends.base import DashboardBackend


class GreenplumBackend(DashboardBackend):
    """Backend dashboard untuk target Greenplum.

    Tidak perlu FINAL - JDBC sink upsert (INSERT ... ON CONFLICT) langsung
    konsisten, tidak ada duplikat sementara seperti ReplacingMergeTree.
    Kolom metadata Debezium apa adanya (tidak ada MV yang me-rename):
      - __deleted tersimpan sebagai TEKS 'true'/'false', bukan boolean.
      - __source_ts_ms dipakai sebagai pengganti "source_ts_ms".
      - "created" tersimpan sebagai TEKS ISO-8601 (bukan tipe timestamp asli) -
        Debezium mengirim timestamptz sumber sebagai logical type ZonedTimestamp
        berskema STRING, dan auto.create JDBC sink mengikuti skema itu apa
        adanya. Karena sudah string, JANGAN panggil .isoformat() di sini, dan
        query yang butuh perbandingan tanggal harus cast eksplisit ::timestamptz.
    """

    def _conn(self):
        return psycopg2.connect(
            host=config.PG_HOST,
            port=config.PG_PORT,
            user=config.PG_USER,
            password=config.PG_PASSWORD,
            dbname=config.PG_DATABASE,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )

    def _table(self, name):
        return f"{config.PG_SCHEMA}.{name}"

    def employees_count(self) -> dict:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT count(*) AS jumlah FROM {self._table('account_user')}
                    WHERE __deleted = 'false' AND is_active = true
                    """)
                return {"total": cur.fetchone()["jumlah"]}
        finally:
            conn.close()

    def latest_documents(self, limit=10):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        d.id, d.user_id,
                        coalesce(nullif(u.fullname, ''), concat('User #', d.user_id::text)) AS fullname,
                        d.document_type, d.status, d.start_leave, d.end_leave, d.created,
                        d.__source_ts_ms AS source_ts_ms, d.leaving_reason
                    FROM {self._table('leave_leavedocument')} d
                    LEFT JOIN {self._table('account_user')} u ON u.id = d.user_id
                    WHERE d.__deleted = 'false'
                    ORDER BY d.__source_ts_ms DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "fullname": r["fullname"],
                        "document_type": r["document_type"],
                        "status": r["status"],
                        "start_leave": str(r["start_leave"]),
                        "end_leave": str(r["end_leave"]),
                        "created": r["created"],
                        "updated_at": r["source_ts_ms"],
                        "leaving_reason": r["leaving_reason"],
                    }
                    for r in rows
                ]
        finally:
            conn.close()

    def recent_deleted(self, limit: int = 5) -> list[dict]:
        if not config.ENABLE_DELETED_LOG:
            return []
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        (l.payload->>'id')::int AS id,
                        (l.payload->>'user_id')::int AS user_id,
                        coalesce(nullif(u.fullname, ''), concat('User #', l.payload->>'user_id')) AS fullname,
                        l.payload->>'document_type' AS document_type,
                        l.payload->>'status' AS status,
                        l.deleted_at AS source_ts_ms
                    FROM {self._table('deleted_log')} l
                    LEFT JOIN {self._table('account_user')} u ON u.id = (l.payload->>'user_id')::int
                    WHERE l.table_name = 'leave_leavedocument'
                    ORDER BY l.deleted_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "fullname": r["fullname"],
                        "document_type": r["document_type"],
                        "status": r["status"],
                        "deleted_at": r["source_ts_ms"],
                    }
                    for r in rows
                ]
        finally:
            conn.close()

    def week_count(self) -> dict:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT count(*) AS jumlah FROM {self._table('leave_leavedocument')}
                    WHERE __deleted = 'false'
                      AND date_trunc('week', created::timestamptz) = date_trunc('week', now())
                    """)
                return {"total": cur.fetchone()["jumlah"]}
        finally:
            conn.close()

    def week_status(self) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT status, count(*) AS jumlah FROM {self._table('leave_leavedocument')}
                    WHERE __deleted = 'false'
                      AND date_trunc('week', created::timestamptz) = date_trunc('week', now())
                    GROUP BY status ORDER BY jumlah DESC
                    """)
                return [
                    {"status": r["status"], "count": r["jumlah"]}
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()

    def latest_accounts(self, limit: int = 10) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, fullname, level, working_unit FROM {self._table('account_user')}
                    ORDER BY id DESC LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": r["id"],
                        "fullname": r["fullname"],
                        "level": r["level"],
                        "working_unit": r["working_unit"],
                    }
                    for r in rows
                ]
        finally:
            conn.close()
