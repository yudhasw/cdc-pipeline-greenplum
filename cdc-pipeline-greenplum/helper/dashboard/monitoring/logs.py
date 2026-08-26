"""Ambil log mentah dari container lain di stack yang sama lewat Docker socket.

Dashboard di-mount /var/run/docker.sock (read-only) di docker-compose.yml
supaya bisa baca log container lain (Kafka, Kafka Connect, Greenplum,
pipeline-agent) tanpa perlu tiap komponen expose log-nya sendiri lewat HTTP
terpisah. Daftar container dibatasi whitelist ALLOWED_CONTAINERS - endpoint
tidak menerima nama container bebas dari client.
"""

import docker

ALLOWED_CONTAINERS = {
    "kafka": "kafka",
    "debezium-connect": "debezium-connect",
    "jdbc-connect": "jdbc-connect",
    "cdc-service": "cdc-service",
    "dashboard": "dashboard",
}


def list_containers():
    return list(ALLOWED_CONTAINERS.keys())


def fetch_logs(alias, tail=200):
    if alias not in ALLOWED_CONTAINERS:
        raise ValueError(f"container '{alias}' tidak dikenal")
    client = docker.from_env()
    container = client.containers.get(ALLOWED_CONTAINERS[alias])
    raw = container.logs(tail=tail, timestamps=False)
    return raw.decode("utf-8", errors="replace").splitlines()
