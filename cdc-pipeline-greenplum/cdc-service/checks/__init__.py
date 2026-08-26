"""Kumpulan pemeriksaan berkala pipeline-agent.

- connector.py : registrasi & kesehatan connector Kafka Connect (generik, N connector)
- schema/      : deteksi perubahan struktur tabel sumber vs target (backend pluggable:
                 ClickHouse atau Postgres-family/WarehousePG)
- common.py    : util bersama (logging)
"""
