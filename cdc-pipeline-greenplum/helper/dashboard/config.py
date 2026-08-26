import os

DB_BACKEND = os.environ.get("DB_BACKEND", "postgres")  # "clickhouse" | "postgres"

# ClickHouse (dipakai kalau DB_BACKEND=clickhouse, mis. dari cdc-pipeline)
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "")

# Greenplum / Postgres-family / WarehousePG (dipakai kalau DB_BACKEND=postgres, mis. dari cdc-pipeline-greenplum)
PG_HOST = os.environ.get("PG_HOST", "")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
PG_DATABASE = os.environ.get("PG_DATABASE", "")
PG_SCHEMA = os.environ.get("PG_SCHEMA", "public")
ENABLE_DELETED_LOG = os.environ.get("ENABLE_DELETED_LOG", "true").lower() == "true"

CONNECT_URL = os.environ.get("CONNECT_URL", "http://connect:8083")

SOURCE_PG_HOST = os.environ.get("SOURCE_PG_HOST", "")
SOURCE_PG_PORT = int(os.environ.get("SOURCE_PG_PORT", "5432"))
SOURCE_PG_DATABASE = os.environ.get("SOURCE_PG_DATABASE", "")
SOURCE_PG_USER = os.environ.get("SOURCE_PG_USER", "")
SOURCE_PG_PASSWORD = os.environ.get("SOURCE_PG_PASSWORD", "")
SOURCE_SLOT_NAME = os.environ.get("SOURCE_SLOT_NAME", "debezium_cutidev_gp_poc")
