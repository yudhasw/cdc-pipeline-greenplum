import config


def get_backend():
    """Pilih backend analitik sesuai DB_BACKEND, tanpa main.py perlu tahu detilnya."""
    if config.DB_BACKEND == "clickhouse":
        from backends.clickhouse_backend import ClickHouseBackend
        return ClickHouseBackend()
    elif config.DB_BACKEND == "postgres":
        from backends.greenplum_backend import GreenplumBackend
        return GreenplumBackend()
    raise ValueError(f"DB_BACKEND tidak dikenal: {config.DB_BACKEND!r}")
