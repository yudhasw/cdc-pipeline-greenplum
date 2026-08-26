import clickhouse_connect
import config
from backends.base import DashboardBackend


class ClickHouseBackend(DashboardBackend):
    """Backend dashboard untuk target ClickHouse (dipakai cdc-pipeline).

    Tabel ReplacingMergeTree - semua query WAJIB pakai FINAL untuk hindari
    duplikat sementara sebelum background merge selesai.
    """

    def _client(self):
        return clickhouse_connect.get_client(
            host=config.CLICKHOUSE_HOST,
            port=config.CLICKHOUSE_PORT,
            username=config.CLICKHOUSE_USER,
            password=config.CLICKHOUSE_PASSWORD,
            database=config.CLICKHOUSE_DATABASE,
        )

    def employees_count(self) -> dict:
        client = self._client()
        result = client.query("""
            SELECT count() AS jumlah FROM account_user FINAL
            WHERE is_deleted = 0 AND is_active = 1
            """)
        return {"total": result.result_rows[0][0]}

    def latest_documents(self, limit=10):
        client = self._client()
        result = client.query(f"""
            SELECT d.id, d.user_id,
                   coalesce(nullif(u.fullname, ''), concat('User #', toString(d.user_id))) AS fullname,
                   d.document_type, d.status, d.start_leave, d.end_leave,
                   d.created, d.source_ts_ms, d.leaving_reason
            FROM leave_leavedocument AS d FINAL
            LEFT JOIN account_user AS u FINAL ON u.id = d.user_id
            WHERE d.is_deleted = 0
            ORDER BY d.source_ts_ms DESC LIMIT {limit}
            """)
        return [
            {
                "id": r[0],
                "user_id": r[1],
                "fullname": r[2],
                "document_type": r[3],
                "status": r[4],
                "start_leave": str(r[5]),
                "end_leave": str(r[6]),
                "created": r[7].isoformat(),
                "updated_at": r[8],
                "leaving_reason": r[9],
            }
            for r in result.result_rows
        ]

    def recent_deleted(self, limit: int = 5) -> list[dict]:
        client = self._client()
        result = client.query(f"""
            SELECT d.id, d.user_id,
                   coalesce(nullif(u.fullname, ''), concat('User #', toString(d.user_id))) AS fullname,
                   d.document_type, d.status, d.source_ts_ms
            FROM leave_leavedocument AS d FINAL
            LEFT JOIN account_user AS u FINAL ON u.id = d.user_id
            WHERE d.is_deleted = 1
            ORDER BY d.source_ts_ms DESC LIMIT {limit}
            """)
        return [
            {
                "id": r[0],
                "user_id": r[1],
                "fullname": r[2],
                "document_type": r[3],
                "status": r[4],
                "deleted_at": r[5],
            }
            for r in result.result_rows
        ]

    def week_count(self) -> dict:
        client = self._client()
        result = client.query("""
            SELECT count() AS jumlah FROM leave_leavedocument FINAL
            WHERE is_deleted = 0 AND toMonday(created) = toMonday(today())
            """)
        return {"total": result.result_rows[0][0]}

    def week_status(self) -> list[dict]:
        client = self._client()
        result = client.query("""
            SELECT status, count() AS jumlah FROM leave_leavedocument FINAL
            WHERE is_deleted = 0 AND toMonday(created) = toMonday(today())
            GROUP BY status ORDER BY jumlah DESC
            """)
        return [{"status": r[0], "count": r[1]} for r in result.result_rows]

    def latest_accounts(self, limit: int = 10) -> list[dict]:
        client = self._client()
        result = client.query(f"""
            SELECT id, fullname, level, working_unit FROM account_user FINAL
            ORDER BY id DESC LIMIT {limit}
            """)
        return [
            {"id": r[0], "fullname": r[1], "level": r[2], "working_unit": r[3]}
            for r in result.result_rows
        ]
