"""Util bersama untuk semua pemeriksaan pipeline-agent."""

from datetime import datetime


def log(check, msg):
    """Cetak pesan log dengan timestamp dan prefix nama pemeriksaan.

    Prefix ([registry]/[watchdog]/[schema]) memudahkan filter log per fungsi,
    misalnya: docker compose logs pipeline-agent | grep watchdog
    """
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | [{check}] {msg}", flush=True)
