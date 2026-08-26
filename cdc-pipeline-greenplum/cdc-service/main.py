#!/usr/bin/env python3
"""CDC Service: Orchestrator utama untuk merge job + pipeline monitoring.

Koordinasi:
1. Merge job: merge data staging → target setiap INTERVAL_MERGE detik
2. Vacuum job: VACUUM tabel berkala setiap INTERVAL_VACUUM detik
3. Registry check: verifikasi connector terdaftar setiap INTERVAL_REGISTRY detik
4. Watchdog check: verifikasi connector RUNNING setiap INTERVAL_WATCHDOG detik
5. Schema drift: deteksi perubahan schema setiap INTERVAL_SCHEMA detik

Semua berjalan concurrent menggunakan threading.
"""

import threading
import time
import config
from checks.common import log
from merge import run_merge_job, run_vacuum
from checks.connector import registry_check, watchdog_check
from checks.schema import schema_check


def merge_loop():
    """Loop untuk merge job dan vacuum."""
    last_vacuum = time.time()
    while True:
        try:
            run_merge_job()
        except Exception as e:
            log("merge", f"Error: {e}")

        now = time.time()
        if now - last_vacuum >= config.INTERVAL_VACUUM:
            try:
                run_vacuum()
                last_vacuum = now
            except Exception as e:
                log("merge", f"Vacuum error: {e}")

        time.sleep(config.INTERVAL_MERGE)


def registry_loop():
    """Loop untuk registry check."""
    while True:
        try:
            registry_check()
        except Exception as e:
            log("registry", f"Error: {e}")
        time.sleep(config.INTERVAL_REGISTRY)


def watchdog_loop():
    """Loop untuk watchdog check."""
    while True:
        try:
            watchdog_check()
        except Exception as e:
            log("watchdog", f"Error: {e}")
        time.sleep(config.INTERVAL_WATCHDOG)


def schema_loop():
    """Loop untuk schema drift detection."""
    while True:
        try:
            schema_check()
        except Exception as e:
            log("schema", f"Error: {e}")
        time.sleep(config.INTERVAL_SCHEMA)


def main():
    log(
        "agent",
        f"Starting CDC service: "
        f"merge_interval={config.INTERVAL_MERGE}s, "
        f"vacuum_interval={config.INTERVAL_VACUUM}s, "
        f"registry_interval={config.INTERVAL_REGISTRY}s, "
        f"watchdog_interval={config.INTERVAL_WATCHDOG}s, "
        f"schema_interval={config.INTERVAL_SCHEMA}s, "
        f"target_schema={config.TARGET_SCHEMA}",
    )

    # Start background threads
    threads = [
        threading.Thread(target=merge_loop, daemon=True, name="merge"),
        threading.Thread(target=registry_loop, daemon=True, name="registry"),
        threading.Thread(target=watchdog_loop, daemon=True, name="watchdog"),
        threading.Thread(target=schema_loop, daemon=True, name="schema"),
    ]

    for t in threads:
        t.start()
        log("agent", f"Started thread: {t.name}")

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("agent", "Shutting down...")


if __name__ == "__main__":
    main()
