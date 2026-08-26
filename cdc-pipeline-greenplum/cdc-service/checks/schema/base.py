"""Kontrak backend deteksi skema.

Tiap backend menerjemahkan cara membaca struktur tabel sumber & target sesuai
teknologinya sendiri (ClickHouse lewat table function postgresql(), Postgres-
family lewat psycopg2 dua sisi) - tapi WAJIB mengembalikan bentuk yang sama:
dict {nama_kolom: tipe}, supaya check_schema_drift() tidak perlu tahu backend
mana yang sedang dipakai.
"""

from abc import ABC, abstractmethod


class SchemaBackend(ABC):
    @abstractmethod
    def source_columns(self, table: str) -> dict[str, str]:
        """Kembalikan {nama_kolom: tipe} tabel di Postgres sumber saat ini.

        Kembalikan dict kosong kalau tabel tidak ditemukan.
        """
        raise NotImplementedError

    @abstractmethod
    def target_columns(self, table: str) -> dict[str, str]:
        """Kembalikan {nama_kolom: tipe} tabel target saat ini.

        Kembalikan dict kosong kalau tabel belum ada di target.
        """
        raise NotImplementedError

    def close(self):
        """Tutup koneksi yang dibuka backend (opsional override)."""
        pass
