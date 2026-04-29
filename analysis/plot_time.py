#!/usr/bin/env python3
"""
plot_time.py — generate Plot 3 (Ser/Deser Time, 2×2 subplot grid)

Reads:  metrics/aggregated/ser_deser_overhead.csv
Writes: results/ser_deser_vs_payload_flat_data.png
        results/ser_deser_vs_payload_nested.png
        results/ser_deser_vs_payload_wide.png
        results/ser_deser_vs_payload_array.png

Also generates a combined 2×2 grid saved as results/ser_deser_2x2_grid.png

Usage:
  python3 plot_time.py
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGG_DIR      = PROJECT_ROOT / "metrics" / "aggregated"
RESULTS_DIR  = PROJECT_ROOT / "results"

# Plot styling
COLORS = {"REST": "#E74C3C", "gRPC": "#3498DB"}
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
})

# Structure → output filename (matches your placeholder names)
STRUCTURE_FILES = {
    "flat":   "ser_deser_vs_payload_flat_data.png",
    "nested": "ser_deser_vs_payload_nested.png",
    "wide":   "ser_deser_vs_payload_wide.png",
    "array":  "ser_deser_vs_payload_array.png",
}

STRUCTURES = ["flat", "nested", "wide", "array"]


def payload_label(size_bytes):
    if size_bytes >= 1024:
        return f"{size_bytes // 1024}KB"
    return f"{size_bytes}B"


def load_data():
    """
    Load aggregated ser/deser CSV.
    Returns: { structure: { "sizes": [...], "rest": [...], "grpc": [...] } }
    """
    csv_path = AGG_DIR / "ser_deser_overhead.csv"
    if not csv_path.exists():
        print(f"[plot] {csv_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    data = {s: {"sizes": [], "rest": [], "grpc": []} for s in STRUCTURES}

    for row in rows:
        struct = row["structure"]
        if struct not in data:
            continue

        size = int(row["payload_size"])
        rest_val = float(row["rest_O3_mean_us"]) if row["rest_O3_mean_us"] else None
        grpc_val = float(row["grpc_O3_mean_us"]) if row["grpc_O3_mean_us"] else None

        data[struct]["sizes"].append(size)
        data[struct]["rest"].append(rest_val)
        data[struct]["grpc"].append(grpc_val)

    return data


def plot_individual(data):
    """Generate one plot per structure (matching placeholder filenames)."""
    for struct in STRUCTURES:
        d = data[struct]
        if not d["sizes"]:
            continue

        fig, ax = plt.subplots(figsize=(10, 6))

        rest_sizes = [s for s, v in zip(d["sizes"], d["rest"]) if v is not None]
        rest_vals  = [v for v in d["rest"] if v is not None]
        grpc_sizes = [s for s, v in zip(d["sizes"], d["grpc"]) if v is not None]
        grpc_vals  = [v for v in d["grpc"] if v is not None]

        if rest_vals:
            ax.plot(rest_sizes, rest_vals, 'o-', color=COLORS["REST"],
                    linewidth=2, markersize=8, label="REST (JSON)")
        if grpc_vals:
            ax.plot(grpc_sizes, grpc_vals, 's-', color=COLORS["gRPC"],
                    linewidth=2, markersize=8, label="gRPC (Protobuf)")

        ax.set_xscale("log", base=2)
        ax.set_xlabel("Payload Size")
        ax.set_ylabel("Ser + Deser Time (µs)")
        ax.set_title(f"Ser/Deser Overhead — {struct.capitalize()} Structure")
        ax.legend()
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(
            lambda x, _: payload_label(int(x))))

        fig.tight_layout()
        out_path = RESULTS_DIR / STRUCTURE_FILES[struct]
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"[plot] {struct} → {out_path}")


def plot_grid(data):
    """Generate the 2×2 subplot grid (Plot 3 from the README)."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True, sharey=True)
    grid_pos = {"flat": (0, 0), "nested": (0, 1), "wide": (1, 0), "array": (1, 1)}

    for struct in STRUCTURES:
        r, c = grid_pos[struct]
        ax = axes[r][c]
        d = data[struct]

        rest_sizes = [s for s, v in zip(d["sizes"], d["rest"]) if v is not None]
        rest_vals  = [v for v in d["rest"] if v is not None]
        grpc_sizes = [s for s, v in zip(d["sizes"], d["grpc"]) if v is not None]
        grpc_vals  = [v for v in d["grpc"] if v is not None]

        if rest_vals:
            ax.plot(rest_sizes, rest_vals, 'o-', color=COLORS["REST"],
                    linewidth=2, markersize=6, label="REST")
        if grpc_vals:
            ax.plot(grpc_sizes, grpc_vals, 's-', color=COLORS["gRPC"],
                    linewidth=2, markersize=6, label="gRPC")

        ax.set_xscale("log", base=2)
        ax.set_title(struct.capitalize(), fontweight="bold")
        ax.legend(fontsize=9)
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(
            lambda x, _: payload_label(int(x))))

    # Shared axis labels
    fig.supxlabel("Payload Size (log scale)", fontsize=13)
    fig.supylabel("Ser + Deser Time (µs)", fontsize=13)
    fig.suptitle("Plot 3 — Serialization/Deserialization Overhead by Structure",
                 fontsize=14, fontweight="bold")

    fig.tight_layout(rect=[0.02, 0.02, 1, 0.96])
    out_path = RESULTS_DIR / "ser_deser_2x2_grid.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[plot] 2×2 grid → {out_path}")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    plot_individual(data)
    plot_grid(data)
    print("[plot_time] done")


if __name__ == "__main__":
    main()
