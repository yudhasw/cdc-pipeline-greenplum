"""Backend deteksi skema untuk target Postgres-family/WarehousePG (dipakai
cdc-pipeline-greenplum).

Dua sisi (source & target) sama-sama dibaca langsung via psycopg2, karena
keduanya bicara protokol Postgres - tidak ada trik cross-query seperti
ClickHouse punya.
"""

import psycopg2

import config
from checks.schema.base import SchemaBackend


class GreenplumSchemaBackend(SchemaBackend):
    def __init__(self):
        self.src_conn = psycopg2.connect(
            host=config.PG_HOST,
            port=config.PG_PORT,
            dbname=config.PG_DATABASE,
            user=config.PG_USER,
            password=config.PG_PASSWORD,
            connect_timeout=config.HTTP_TIMEOUT,
        )
        self.tgt_conn = psycopg2.connect(
            host=config.TARGET_HOST,
            port=config.TARGET_PORT,
            dbname=config.TARGET_DATABASE,
            user=config.TARGET_USER,
            password=config.TARGET_PASSWORD,
            connect_timeout=config.HTTP_TIMEOUT,
        )

    def source_columns(self, table):
        with self.src_conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def _find_target_table(self, table):
        """Cari nama tabel di target yang berpadanan dengan tabel sumber.

        JDBC sink membuat nama tabel dari topic ("${topic}"), hasilnya diamati
        TIDAK selalu identik dengan nama tabel sumber - jadi dicari lewat
        kecocokan akhiran, bukan diasumsikan sama persis.
        """
        with self.tgt_conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND (table_name = %s OR table_name LIKE %s)",
                (config.TARGET_SCHEMA, table, f"%{table}"),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def target_columns(self, table):
        actual = self._find_target_table(table)
        if not actual:
            return {}
        with self.tgt_conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (config.TARGET_SCHEMA, actual),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def close(self):
        self.src_conn.close()
        self.tgt_conn.close()
