from abc import ABC, abstractmethod


class DashboardBackend(ABC):
    @abstractmethod
    def employees_count(self) -> dict:
        """Jumlah karyawan aktif.

        Return: {"total": int}
        """
        raise NotImplementedError

    @abstractmethod
    def latest_documents(self, limit: int = 10) -> list[dict]:
        """N leave document terbaru (urut dari perubahan paling baru).

        Return: list of {
            "id": int, "user_id": int, "fullname": str,
            "document_type": str, "status": str,
            "start_leave": str, "end_leave": str,
            "created": str, "updated_at": Any, "leaving_reason": str,
        }
        """
        raise NotImplementedError

    @abstractmethod
    def recent_deleted(self, limit: int = 5) -> list[dict]:
        """N leave document yang baru dihapus (soft delete).

        Return: list of {
            "id": int, "user_id": int, "fullname": str,
            "document_type": str, "status": str, "deleted_at": Any,
        }
        """
        raise NotImplementedError

    @abstractmethod
    def week_count(self) -> dict:
        """Jumlah leave document yang dibuat minggu ini.

        Return: {"total": int}
        """
        raise NotImplementedError

    @abstractmethod
    def week_status(self) -> list[dict]:
        """Distribusi status leave document minggu ini.

        Return: list of {"status": str, "count": int}
        """
        raise NotImplementedError

    @abstractmethod
    def latest_accounts(self, limit: int = 10) -> list[dict]:
        """N akun karyawan terbaru.

        Return: list of {
            "id": int, "fullname": str, "level": str, "working_unit": str,
        }
        """
        raise NotImplementedError
