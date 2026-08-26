"""Bikin chart perbandingan 4-metrik: skenario CDC vs skenario Batch ETL.

Cara pakai:
    python plot_comparison.py run_cdc.csv run_batch.csv
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

NOMINAL_INTERVAL = 3  # detik - dipakai sebagai jarak antar-sample "ideal"


def load_csv(path):
    """Muat CSV dan tambahkan 't_nominal' = index * NOMINAL_INTERVAL.

    Jarak waktu ASLI antar-sample (kolom 't') tidak stabil - kena jitter
    latency jaringan ke cutidev (kadang 3 detik, kadang sampai 16 detik per
    sample), jadi total durasi 2 skenario bisa beda jauh secara wall-clock
    walau jumlah sample-nya sepadan. t_nominal mengasumsikan tiap sample
    berjarak rata NOMINAL_INTERVAL detik - menghilangkan efek jitter itu,
    supaya sumbu-x merepresentasikan "langkah pengukuran ke-n", bukan waktu
    nyata yang kena distorsi jaringan.
    """
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            rows.append({
                "t": float(r["t"]),
                "t_nominal": i * NOMINAL_INTERVAL,
                "phase": r.get("phase", ""),
                "tps": float(r["tps"]),
                "blks_read_rate": float(r["blks_read_rate"]),
                "seq_scan": int(r["seq_scan"]),
                "numbackends": int(r["numbackends"]),
            })
    return rows


def main():
    if len(sys.argv) < 3:
        print("Usage: python plot_comparison.py run_cdc.csv run_batch.csv")
        sys.exit(1)

    cdc_rows = load_csv(sys.argv[1])
    batch_rows = load_csv(sys.argv[2])

    fig, axes = plt.subplots(4, 1, figsize=(12, 13), sharex=True)
    metrics = [
        ("tps", "Transactions/sec"),
        ("blks_read_rate", "Blocks Read/sec"),
        ("seq_scan", "Sequential Scan (kumulatif)"),
        ("numbackends", "Jumlah Koneksi Aktif"),
    ]

    # Sample pertama tiap seri sering meleset jauh; tetap digambar, tapi
    # tidak dipakai menentukan batas atas sumbu y.
    for ax, (key, title) in zip(axes, metrics):
        cdc_vals = [r[key] for r in cdc_rows]
        batch_vals = [r[key] for r in batch_rows]
        ax.plot([r["t_nominal"] for r in cdc_rows], cdc_vals,
                 color="#2563eb", linewidth=1.5, label="Skenario CDC")
        ax.plot([r["t_nominal"] for r in batch_rows], batch_vals,
                 color="#dc2626", linewidth=1.5, label="Skenario Batch ETL")
        ax.set_ylabel(title)
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", fontsize=8)

        scale_vals = cdc_vals[1:] + batch_vals[1:]
        if scale_vals:
            ax.set_ylim(top=max(scale_vals) * 1.15)

    batch_moment = next((r["t_nominal"] for r in batch_rows if r["phase"] == "after_select"), None)
    if batch_moment:
        for ax in axes:
            ax.axvline(batch_moment, color="#f97316", linestyle="--", alpha=0.7)
        axes[0].text(batch_moment + 2, axes[0].get_ylim()[1] * 0.9, "SELECT *\ndieksekusi",
                      fontsize=8, color="#f97316")

    axes[-1].set_xlabel("Langkah pengukuran ke-n (interval nominal 3s, bukan waktu asli)")
    axes[0].set_title("Perbandingan Beban Source DB (cutidev): CDC vs Batch ETL Harian", fontsize=12)

    plt.tight_layout()
    out_path = Path(sys.argv[1]).parent / "comparison_chart.png"
    plt.savefig(out_path, dpi=150)
    print(f"Grafik tersimpan: {out_path}")


if __name__ == "__main__":
    main()
