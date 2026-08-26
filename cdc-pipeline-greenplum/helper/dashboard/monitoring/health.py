"""Pemeriksaan kesehatan tiap lapisan pipeline CDC - dipakai endpoint /api/health.

Diadaptasi dari rencana lama (Dokumentasi Proses/rencana-panel-kesehatan-pipeline.md,
ditulis untuk arsitektur ClickHouse) ke arsitektur staging+job-merge yang
sekarang berjalan - kartu "ClickHouse Consumer" diganti kartu "Merge Job",
nama connector dan slot disesuaikan.

Tiap pemeriksaan dibungkus try/except sendiri: kegagalan satu pemeriksaan
(mis. source tidak terjangkau) menghasilkan status fail pada kartu itu saja,
tidak menggagalkan pemeriksaan lain.
"""

import re
import time

import psycopg2
import requests

import config
from monitoring.logs import fetch_logs

# Connectors dan service-nya
CONNECTORS = [
    ("cutidev-gp-poc-source", "http://debezium-connect:8083"),  # source connector
    ("greenplum-gp-poc-sink", "http://jdbc-connect:8083"),  # sink connector
]


def _check_connectors():
    checks = []
    for name, connect_url in CONNECTORS:
        try:
            resp = requests.get(f"{connect_url}/connectors/{name}/status", timeout=5)
            if resp.status_code == 404:
                checks.append(
                    {
                        "name": f"connector: {name}",
                        "status": "fail",
                        "detail": "belum terdaftar",
                    }
                )
                continue
            resp.raise_for_status()
            data = resp.json()
            tasks = data.get("tasks", [])
            failed = [t for t in tasks if t.get("state") == "FAILED"]
            if failed:
                checks.append(
                    {
                        "name": f"connector: {name}",
                        "status": "fail",
                        "detail": f"task {failed[0]['id']} FAILED",
                    }
                )
            elif tasks and all(t.get("state") == "RUNNING" for t in tasks):
                checks.append(
                    {
                        "name": f"connector: {name}",
                        "status": "ok",
                        "detail": f"{len(tasks)} task RUNNING",
                    }
                )
            else:
                states = (
                    ", ".join(t.get("state", "?") for t in tasks) or "tidak ada task"
                )
                checks.append(
                    {"name": f"connector: {name}", "status": "warn", "detail": states}
                )
        except Exception as e:
            checks.append(
                {"name": f"connector: {name}", "status": "fail", "detail": str(e)}
            )
    return checks


def _check_replication_lag():
    try:
        conn = psycopg2.connect(
            host=config.SOURCE_PG_HOST,
            port=config.SOURCE_PG_PORT,
            dbname=config.SOURCE_PG_DATABASE,
            user=config.SOURCE_PG_USER,
            password=config.SOURCE_PG_PASSWORD,
            connect_timeout=5,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT active, pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) "
                "FROM pg_replication_slots WHERE slot_name = %s",
                (config.SOURCE_SLOT_NAME,),
            )
            row = cur.fetchone()
        conn.close()
        if not row:
            return {
                "name": "replication lag",
                "status": "fail",
                "detail": "slot tidak ditemukan",
            }
        active, lag_bytes = row
        if not active:
            return {
                "name": "replication lag",
                "status": "fail",
                "detail": "slot tidak aktif",
            }
        lag_mb = (lag_bytes or 0) / 1024 / 1024
        status = "ok" if lag_mb < 100 else "warn"
        return {
            "name": "replication lag",
            "status": status,
            "detail": f"{lag_mb:.1f} MB",
        }
    except Exception as e:
        return {"name": "replication lag", "status": "fail", "detail": str(e)}


def _check_merge_job():
    try:
        lines = fetch_logs("cdc-service", tail=200)
        merge_lines = [l for l in lines if "[merge]" in l]
        if not merge_lines:
            return {
                "name": "merge job",
                "status": "warn",
                "detail": "belum ada log merge",
            }
        last = merge_lines[-1]
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", last)
        if not m:
            return {
                "name": "merge job",
                "status": "warn",
                "detail": "format log tidak dikenali",
            }
        last_time = time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        age = time.time() - time.mktime(last_time)
        status = "ok" if age < 120 else "warn" if age < 600 else "fail"
        return {
            "name": "merge job",
            "status": status,
            "detail": f"siklus terakhir {int(age)} detik lalu",
        }
    except Exception as e:
        return {"name": "merge job", "status": "fail", "detail": str(e)}


def _check_freshness():
    try:
        conn = psycopg2.connect(
            host=config.PG_HOST,
            port=config.PG_PORT,
            dbname=config.PG_DATABASE,
            user=config.PG_USER,
            password=config.PG_PASSWORD,
            connect_timeout=5,
        )
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT max(__source_ts_ms) FROM {config.PG_SCHEMA}.leave_leavedocument"
            )
            row = cur.fetchone()
        conn.close()
        if not row or row[0] is None:
            return {
                "name": "kesegaran data",
                "status": "warn",
                "detail": "belum ada data",
            }
        age_sec = (time.time() * 1000 - row[0]) / 1000
        if age_sec < 3600:
            detail = f"event terakhir {int(age_sec)} detik lalu"
        else:
            detail = f"event terakhir {age_sec / 3600:.1f} jam lalu"
        return {"name": "kesegaran data", "status": "ok", "detail": detail}
    except Exception as e:
        return {"name": "kesegaran data", "status": "fail", "detail": str(e)}


def get_health():
    checks = []
    checks.extend(_check_connectors())
    checks.append(_check_replication_lag())
    checks.append(_check_merge_job())
    checks.append(_check_freshness())

    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "ok"

    return {"overall": overall, "checks": checks}
