"""Ambil angka latensi merge dari log cdc-service, keluarkan sebagai CSV.

Membaca dari stdin, jadi bisa dipipe langsung dari docker:

    docker compose logs cdc-service --no-log-prefix | python extract_latency.py > hasil.csv

Baris log yang diparse bentuknya:
    2026-08-11 08:49:08 | [merge] [leave_leavedocument] 3 baris staging diproses,
    3 dibersihkan dari staging, 0 baris lama dihapus, 3 baris baru/update ditulis,
    latensi min=20.4s avg=20.5s max=20.7s

Baris merge tanpa bagian "latensi" (staging kosong / semua kalah guard) tetap
diambil, kolom latensinya dikosongkan - supaya jumlah siklus yang benar-benar
memproses data tidak hilang dari rekap.
"""

import csv
import re
import sys

POLA = re.compile(
    r"(?P<waktu>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r"\s*\|\s*\[merge\]\s*\[(?P<tabel>[^\]]+)\]\s*"
    r"(?P<diproses>\d+) baris staging diproses,\s*"
    r"(?P<dibersihkan>\d+) dibersihkan dari staging,\s*"
    r"(?P<dihapus>\d+) baris lama dihapus,\s*"
    r"(?P<ditulis>\d+) baris baru/update ditulis"
    r"(?:,\s*latensi min=(?P<min>[\d.]+)s avg=(?P<avg>[\d.]+)s max=(?P<max>[\d.]+)s)?"
)

KOLOM = [
    "waktu", "tabel", "diproses", "dibersihkan", "dihapus", "ditulis",
    "min_detik", "avg_detik", "max_detik",
]


def main():
    writer = csv.DictWriter(sys.stdout, fieldnames=KOLOM, lineterminator="\n")
    writer.writeheader()

    jumlah = 0
    for baris in sys.stdin:
        m = POLA.search(baris)
        if not m:
            continue
        writer.writerow({
            "waktu": m.group("waktu"),
            "tabel": m.group("tabel"),
            "diproses": m.group("diproses"),
            "dibersihkan": m.group("dibersihkan"),
            "dihapus": m.group("dihapus"),
            "ditulis": m.group("ditulis"),
            "min_detik": m.group("min") or "",
            "avg_detik": m.group("avg") or "",
            "max_detik": m.group("max") or "",
        })
        jumlah += 1

    print(f"[{jumlah} baris merge terekstrak]", file=sys.stderr)


if __name__ == "__main__":
    main()
