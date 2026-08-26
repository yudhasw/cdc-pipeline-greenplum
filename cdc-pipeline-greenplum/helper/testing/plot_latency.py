"""Dua grafik latensi merge dari hasil extract_latency.py:

  1. scatter  - jumlah baris vs latensi, membuktikan keduanya tidak berhubungan
  2. timeline - latensi terhadap waktu, menunjukkan lonjakan menggerombol di
                satu rentang waktu (insiden jaringan), bukan tersebar acak

Cara pakai:
    python plot_latency.py hasil.csv
"""

import csv
import statistics
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

AMBANG = 60
WARNA_NORMAL = "#2563eb"
WARNA_ANOMALI = "#dc2626"


def buka(p):
    """PowerShell '>' menulis UTF-16 dengan BOM; shell lain UTF-8. Tangani keduanya."""
    with open(p, "rb") as fb:
        awal = fb.read(2)
    enc = "utf-16" if awal in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    return open(p, newline="", encoding=enc)


def muat(path):
    rows = []
    with buka(path) as f:
        for r in csv.DictReader(f):
            if not r.get("avg_detik"):
                continue
            rows.append(
                {
                    "waktu": datetime.strptime(r["waktu"], "%Y-%m-%d %H:%M:%S"),
                    "diproses": int(r["diproses"]),
                    "avg": float(r["avg_detik"]),
                    "min": float(r["min_detik"]),
                    "max": float(r["max_detik"]),
                }
            )
    return sorted(rows, key=lambda r: r["waktu"])


def korelasi(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    atas = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    bawah = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return atas / bawah if bawah else 0.0


def main():
    if len(sys.argv) < 2:
        print("Usage: python plot_latency.py hasil.csv")
        sys.exit(1)

    path = Path(sys.argv[1])
    rows = muat(path)
    if not rows:
        print("Tidak ada baris berlatensi di file itu.")
        sys.exit(1)

    normal = [r for r in rows if r["avg"] <= AMBANG]
    anomali = [r for r in rows if r["avg"] > AMBANG]
    r_all = korelasi([r["diproses"] for r in rows], [r["avg"] for r in rows])
    r_norm = (
        korelasi([r["diproses"] for r in normal], [r["avg"] for r in normal])
        if len(normal) > 2
        else 0
    )

    _, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10))

    # ---- 1. Scatter: jumlah baris vs latensi ----
    ax1.scatter(
        [r["diproses"] for r in normal],
        [r["avg"] for r in normal],
        s=28,
        alpha=0.65,
        color=WARNA_NORMAL,
        label=f"Kondisi normal (n={len(normal)})",
    )
    ax1.scatter(
        [r["diproses"] for r in anomali],
        [r["avg"] for r in anomali],
        s=28,
        alpha=0.65,
        color=WARNA_ANOMALI,
        marker="^",
        label=f"Periode gangguan jaringan (n={len(anomali)})",
    )
    ax1.set_yscale("log")  # rentang 3-865 detik terlalu lebar untuk skala linear
    ax1.set_xlabel("Jumlah baris diproses dalam satu siklus")
    ax1.set_ylabel("Latensi rata-rata (detik, skala log)")
    ax1.set_title(
        f"Latensi tidak ditentukan oleh jumlah baris\n"
        f"Pearson r = {r_all:.3f}  (r² = {r_all**2:.3f} → hanya menjelaskan "
        f"{r_all**2*100:.1f}% variasi)",
        fontsize=11,
    )
    ax1.grid(alpha=0.3, which="both")
    ax1.legend(fontsize=8)

    # ---- 2. Timeline: latensi terhadap waktu ----
    ax2.plot(
        [r["waktu"] for r in rows],
        [r["avg"] for r in rows],
        color="#94a3b8",
        linewidth=0.8,
        zorder=1,
    )
    ax2.scatter(
        [r["waktu"] for r in normal],
        [r["avg"] for r in normal],
        s=18,
        color=WARNA_NORMAL,
        zorder=2,
        label="Normal",
    )
    ax2.scatter(
        [r["waktu"] for r in anomali],
        [r["avg"] for r in anomali],
        s=28,
        color=WARNA_ANOMALI,
        marker="^",
        zorder=3,
        label="Gangguan",
    )
    ax2.axhline(
        AMBANG, color="#f97316", linestyle="--", alpha=0.7, label=f"Ambang {AMBANG}s"
    )
    ax2.set_yscale("log")
    ax2.set_xlabel("Waktu")
    ax2.set_ylabel("Latensi rata-rata (detik, skala log)")
    med_n = statistics.median([r["avg"] for r in normal]) if normal else 0
    med_a = statistics.median([r["avg"] for r in anomali]) if anomali else 0
    ax2.set_title(
        f"Lonjakan datang berkelompok (burst) dan berulang sepanjang sesi\n"
        f"median normal {med_n:.1f}s  vs  median saat lonjakan {med_a:.1f}s",
        fontsize=11,
    )
    ax2.grid(alpha=0.3, which="both")
    ax2.legend(fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    # Rotasi label khusus ax2 saja. JANGAN pakai fig.autofmt_xdate(): fungsi itu
    # berlaku untuk seluruh figure dan menyembunyikan label sumbu-X di subplot
    # atas, padahal di sana sumbu-X-nya "jumlah baris" - bukan tanggal, dan
    # justru wajib terbaca.
    for label in ax2.get_xticklabels():
        label.set_rotation(30)
        label.set_horizontalalignment("right")

    plt.tight_layout()
    keluar = path.parent / "latency_chart.png"
    plt.savefig(keluar, dpi=150)
    print(f"Grafik tersimpan: {keluar}")
    print(f"  total sampel     : {len(rows)}")
    print(f"  normal (<= {AMBANG}s) : {len(normal)}  median {med_n:.1f}s")
    print(f"  gangguan (> {AMBANG}s): {len(anomali)}  median {med_a:.1f}s")
    print(f"  korelasi semua data      : r = {r_all:.3f}")
    print(f"  korelasi data normal saja: r = {r_norm:.3f}")


if __name__ == "__main__":
    main()
