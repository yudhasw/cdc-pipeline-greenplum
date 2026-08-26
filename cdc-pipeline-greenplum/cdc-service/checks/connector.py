"""Pemeriksaan connector via Kafka Connect REST API - generik untuk N connector.

Dipakai baik oleh cdc-pipeline (1 connector: source ClickHouse) maupun
cdc-pipeline-greenplum (2 connector: source + sink JDBC) - jumlah dan identitas
connector yang dipantau ditentukan config.CONNECTORS, bukan hardcode di sini.
"""

import json

import requests

import config
from checks.common import log

_last_failed = set()


def ensure_connectors_registered():
    """Pastikan tiap connector di config.CONNECTORS terdaftar; daftarkan jika belum.

    Idempotent, self-healing: connector yang hilang kapan pun akan otomatis
    didaftarkan ulang dari file konfigurasinya pada siklus berikutnya.
    """
    for c in config.CONNECTORS:
        name, config_file, connect_url = c["name"], c["config_file"], c["connect_url"]
        url = f"{connect_url}/connectors/{name}"
        resp = requests.get(url, timeout=config.HTTP_TIMEOUT)
        if resp.status_code == 200:
            continue  # sudah terdaftar, diam

        if resp.status_code == 404:
            log("registry", f"connector {name} belum ada - mendaftarkan...")
            with open(config_file) as f:
                payload = json.load(f)
            reg = requests.post(
                f"{connect_url}/connectors",
                json=payload,
                timeout=config.HTTP_TIMEOUT,
            )
            if reg.status_code in (200, 201):
                log("registry", f"{name} berhasil didaftarkan")
            else:
                log(
                    "registry",
                    f"{name} gagal mendaftar (HTTP {reg.status_code}): {reg.text[:200]}",
                )
        else:
            log(
                "registry",
                f"{name}: status tak terduga saat cek (HTTP {resp.status_code})",
            )


def restart_failed_tasks():
    """Restart task FAILED pada tiap connector di config.CONNECTORS.

    Task Kafka Connect yang gagal (mis. koneksi ke Postgres putus) tidak pernah
    pulih sendiri dan harus di-restart eksplisit lewat REST API. Data yang
    berubah selama task mati tidak hilang: WAL ditahan replication slot dan
    ter-replay otomatis setelah task hidup kembali.
    """
    for c in config.CONNECTORS:
        name, connect_url = c["name"], c["connect_url"]
        url = f"{connect_url}/connectors/{name}/status"
        resp = requests.get(url, timeout=config.HTTP_TIMEOUT)
        if resp.status_code != 200:
            log("watchdog", f"{name}: tidak bisa baca status (HTTP {resp.status_code})")
            continue

        status = resp.json()
        for task in status.get("tasks", []):
            task_id = task["id"]
            key = (name, task_id)
            if task.get("state") == "FAILED":
                _last_failed.add(key)
                log("watchdog", f"{name} task {task_id} FAILED terdeteksi - restart...")
                requests.post(
                    f"{connect_url}/connectors/{name}/tasks/{task_id}/restart",
                    timeout=config.HTTP_TIMEOUT,
                )
                log("watchdog", f"{name} restart task {task_id} dikirim")
            elif task.get("state") == "RUNNING" and key in _last_failed:
                _last_failed.discard(key)
                log("watchdog", f"{name} task {task_id} sudah PULIH (RUNNING kembali)")


# Wrapper functions untuk main.py
def registry_check():
    """Alias untuk ensure_connectors_registered()."""
    return ensure_connectors_registered()


def watchdog_check():
    """Alias untuk restart_failed_tasks()."""
    return restart_failed_tasks()
