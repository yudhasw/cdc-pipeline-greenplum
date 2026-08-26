import json
import os

# ---- Kafka Connect (registry, watchdog) ----
# Tiap connector punya connect_url sendiri karena debezium-connect (source) dan
# jdbc-connect (sink) adalah 2 Kafka Connect cluster terpisah.
CONNECTORS_JSON = os.environ.get(
    "CONNECTORS_JSON",
    '[{"name":"cutidev-gp-poc-source","config_file":"/postgres-connector.json",'
    '"connect_url":"http://debezium-connect:8083"},'
    '{"name":"greenplum-gp-poc-sink","config_file":"/sink-connector.json",'
    '"connect_url":"http://jdbc-connect:8083"}]'
)
CONNECTORS = json.loads(CONNECTORS_JSON)

# ---- Source PostgreSQL (schema drift detection) ----
SCHEMA_BACKEND = os.environ.get("SCHEMA_BACKEND", "postgres")
PG_HOST = os.environ.get("PG_HOST", "")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DATABASE = os.environ.get("PG_DATABASE", "")
PG_USER = os.environ.get("PG_USER", "")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")

# ---- Target database (merge job) ----
TARGET_HOST = os.environ.get("TARGET_HOST", "")
TARGET_PORT = int(os.environ.get("TARGET_PORT", "5432"))
TARGET_DATABASE = os.environ.get("TARGET_DATABASE", "")
TARGET_USER = os.environ.get("TARGET_USER", "")
TARGET_PASSWORD = os.environ.get("TARGET_PASSWORD", "")
TARGET_SCHEMA = os.environ.get("TARGET_SCHEMA", "public")

# ---- Connection configuration ----
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "10"))

# ---- Merge job configuration ----
INTERVAL_MERGE = int(os.environ.get("INTERVAL_MERGE", "15"))
INTERVAL_VACUUM = int(os.environ.get("INTERVAL_VACUUM", "3600"))
ENABLE_DELETED_LOG = os.environ.get("ENABLE_DELETED_LOG", "true").lower() == "true"
TABLES = os.environ.get(
    "TABLES", "leave_leavedocument,leave_historyleave,account_user"
).split(",")

# ---- Pipeline agent monitoring intervals ----
INTERVAL_REGISTRY = int(os.environ.get("INTERVAL_REGISTRY", "300"))
INTERVAL_WATCHDOG = int(os.environ.get("INTERVAL_WATCHDOG", "60"))
INTERVAL_SCHEMA = int(os.environ.get("INTERVAL_SCHEMA", "300"))

# ---- Metadata columns ----
PIPELINE_METADATA_COLUMNS = os.environ.get("PIPELINE_METADATA_COLUMNS", "__deleted,__op,__source_ts_ms").split(",")

# ---- Schema drift detection ----
STATE_FILE = os.environ.get("STATE_FILE", "/app/schema_state.json")
