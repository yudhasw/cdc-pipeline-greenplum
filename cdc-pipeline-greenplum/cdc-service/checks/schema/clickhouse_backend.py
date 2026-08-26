"""Backend deteksi skema untuk target ClickHouse (dipakai cdc-pipeline).

Source dibaca lewat table function postgresql() DARI DALAM ClickHouse - jadi
cukup satu koneksi (ke ClickHouse), tidak perlu psycopg2/koneksi Postgres
terpisah untuk membaca skema sumber.
"""

import clickhouse_connect

import config
from checks.schema.base import SchemaBackend


class ClickHouseSchemaBackend(SchemaBackend):
    def __init__(self):
        self.client = clickhouse_connect.get_client(
            host=config.CLICKHOUSE_HOST,
            port=config.CLICKHOUSE_PORT,
            username=config.CLICKHOUSE_USER,
            password=config.CLICKHOUSE_PASSWORD,
        )

    def source_columns(self, table):
        result = self.client.query(
            "DESCRIBE postgresql(%(hostport)s, %(db)s, %(table)s, %(user)s, %(password)s)",
            parameters={
                "hostport": f"{config.PG_HOST}:{config.PG_PORT}",
                "db": config.PG_DATABASE,
                "table": table,
                "user": config.PG_USER,
                "password": config.PG_PASSWORD,
            },
        )
        return {row[0]: row[1] for row in result.result_rows}

    def target_columns(self, table):
        result = self.client.query(
            "SELECT name, type FROM system.columns WHERE database = %(db)s AND table = %(table)s",
            parameters={"db": config.CLICKHOUSE_DATABASE, "table": table},
        )
        return {row[0]: row[1] for row in result.result_rows}

    def show_create(self, name):
        """Definisi berjalan objek ClickHouse (dipakai rencana migrasi manual)."""
        try:
            return self.client.command(f"SHOW CREATE TABLE {config.CLICKHOUSE_DATABASE}.{name}")
        except Exception as e:
            return f"(gagal mengambil definisi {name}: {e})"

    def close(self):
        self.client.close()
