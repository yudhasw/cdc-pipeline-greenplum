"""Buat grafik dari hasil poll_perf.py (perf_samples.csv).

Cara pakai:
    python plot_perf.py perf_samples.csv

Menghasilkan file perf_chart.png di folder yang sama dengan CSV-nya.
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

PHASE_LABELS = {
    "baseline": "Baseline\n(generator OFF)",
    "generator_cdc_on": "Generator ON\n+ CDC aktif",
    "generator_cdc_off": "Generator ON\n+ CDC dipause",
    "generator_cdc_resumed": "CDC resume\n(catch-up)",
    "generator_off": "Generator OFF\n(kembali idle)",
}
PHASE_COLORS = {
    "baseline": "#94a3b8",
    "generator_cdc_on": "#f97316",
    "generator_cdc_off": "#dc2626",
    "generator_cdc_resumed": "#0ea5e9",
    "generator_off": "#94a3b8",
}


def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "t": float(r["t"]),
                "phase": r["phase"],
                "tps": float(r["tps"]),
                "debezium_conns": int(r["debezium_conns"]),
            })
    return rows


def main():
    if len(sys.argv) < 2:
        print("Usage: python plot_perf.py <perf_samples.csv>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    rows = load_csv(csv_path)

    t = [r["t"] for r in rows]
    tps = [r["tps"] for r in rows]
    conns = [r["debezium_conns"] for r in rows]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    # --- Panel 1: TPS ---
    ax1.plot(t, tps, color="#2563eb", linewidth=1.5, label="Transactions/sec (cutidev)")
    ax1.set_ylabel("TPS (cutidev)")
    ax1.set_title("Beban Source Database (cutidev) Selama CDC Aktif")
    ax1.grid(alpha=0.3)
    ax1.legend(loc="upper left")

    # --- Panel 2: Debezium connection count ---
    ax2.plot(t, conns, color="#16a34a", linewidth=2, drawstyle="steps-post",
              label="Jumlah koneksi Debezium")
    ax2.set_ylabel("Jumlah Koneksi")
    ax2.set_xlabel("Waktu (detik)")
    ax2.set_ylim(0, max(conns) + 2)
    ax2.grid(alpha=0.3)
    ax2.legend(loc="upper left")

    # Tandai batas fase di kedua panel
    seen_phases = []
    prev_phase = None
    for r in rows:
        if r["phase"] != prev_phase:
            seen_phases.append((r["t"], r["phase"]))
            prev_phase = r["phase"]

    for ax in (ax1, ax2):
        for i, (start_t, phase) in enumerate(seen_phases):
            end_t = seen_phases[i + 1][0] if i + 1 < len(seen_phases) else t[-1]
            ax.axvspan(start_t, end_t, color=PHASE_COLORS.get(phase, "#ccc"), alpha=0.08)

    for start_t, phase in seen_phases:
        ax1.text(start_t + 2, ax1.get_ylim()[1] * 0.92, PHASE_LABELS.get(phase, phase),
                  fontsize=8, va="top")

    plt.tight_layout()
    out_path = csv_path.with_name("perf_chart.png")
    plt.savefig(out_path, dpi=150)
    print(f"Grafik tersimpan: {out_path}")


if __name__ == "__main__":
    main()
