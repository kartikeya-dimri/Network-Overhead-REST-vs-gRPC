#!/usr/bin/env python3
"""
plot_space.py — generate Plot 1 (Overhead Ratio) and Plot 2 (Header+Body:Body Ratio)

Reads:  metrics/aggregated/overhead_ratio.csv
        metrics/aggregated/header_body_ratio.csv
Writes: results/overhead_ratio_vs_payload.png
        results/header_body_ratio_vs_payload.png

Usage:
  python3 plot_space.py
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
    "font.size": 12,
})


def load_csv(path):
    """Load a CSV file into a list of dicts."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def payload_label(size_bytes):
    """Human-readable label for a payload size."""
    if size_bytes >= 1024:
        return f"{size_bytes // 1024}KB"
    return f"{size_bytes}B"


def plot_overhead_ratio():
    """Plot 1 — O1 = wire_bytes / logical_payload_bytes vs payload size."""
    csv_path = AGG_DIR / "overhead_ratio.csv"
    if not csv_path.exists():
        print(f"[plot] {csv_path} not found, skipping Plot 1", file=sys.stderr)
        return

    rows = load_csv(csv_path)

    sizes     = [int(r["payload_size"]) for r in rows]
    rest_o1   = [float(r["rest_O1"]) for r in rows if r["rest_O1"]]
    grpc_o1   = [float(r["grpc_O1"]) for r in rows if r["grpc_O1"]]
    rest_sizes = [int(r["payload_size"]) for r in rows if r["rest_O1"]]
    grpc_sizes = [int(r["payload_size"]) for r in rows if r["grpc_O1"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(rest_sizes, rest_o1, 'o-', color=COLORS["REST"], linewidth=2,
            markersize=8, label="REST (HTTP/1.1 + JSON)")
    ax.plot(grpc_sizes, grpc_o1, 's-', color=COLORS["gRPC"], linewidth=2,
            markersize=8, label="gRPC (HTTP/2 + Protobuf)")

    ax.set_xscale("log", base=2)
    ax.set_xlabel("Payload Size")
    ax.set_ylabel("Overhead Ratio (wire_bytes / logical_bytes)")
    ax.set_title("Plot 1 — Overhead Ratio vs Payload Size")
    ax.legend()
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: payload_label(int(x))))

    # Reference line at y=1 (no overhead)
    ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5, label="y=1 (no overhead)")

    fig.tight_layout()
    out_path = RESULTS_DIR / "overhead_ratio_vs_payload.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[plot] Plot 1 → {out_path}")


def plot_header_body_ratio():
    """Plot 2 — O2 = wire_bytes / encoded_body_bytes vs payload size."""
    csv_path = AGG_DIR / "header_body_ratio.csv"
    if not csv_path.exists():
        print(f"[plot] {csv_path} not found, skipping Plot 2", file=sys.stderr)
        return

    rows = load_csv(csv_path)

    rest_sizes = [int(r["payload_size"]) for r in rows if r["rest_O2"]]
    grpc_sizes = [int(r["payload_size"]) for r in rows if r["grpc_O2"]]
    rest_o2    = [float(r["rest_O2"]) for r in rows if r["rest_O2"]]
    grpc_o2    = [float(r["grpc_O2"]) for r in rows if r["grpc_O2"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(rest_sizes, rest_o2, 'o-', color=COLORS["REST"], linewidth=2,
            markersize=8, label="REST (HTTP/1.1)")
    ax.plot(grpc_sizes, grpc_o2, 's-', color=COLORS["gRPC"], linewidth=2,
            markersize=8, label="gRPC (HTTP/2 + HPACK)")

    ax.set_xscale("log", base=2)
    ax.set_xlabel("Payload Size")
    ax.set_ylabel("Header+Body : Body Ratio")
    ax.set_title("Plot 2 — Framing Overhead (Header+Body:Body) vs Payload Size")
    ax.legend()
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: payload_label(int(x))))

    ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5)

    fig.tight_layout()
    out_path = RESULTS_DIR / "header_body_ratio_vs_payload.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[plot] Plot 2 → {out_path}")


def generate_decomposition_table():
    """Generate a table for Framing vs Encoding overhead % instead of a plot."""
    rest_path = PROJECT_ROOT / "metrics" / "raw" / "space" / "rest.csv"
    grpc_path = PROJECT_ROOT / "metrics" / "raw" / "space" / "grpc.csv"
    
    if not rest_path.exists() or not grpc_path.exists():
        print("[plot] Raw space csvs not found, skipping table", file=sys.stderr)
        return

    rest_rows = load_csv(rest_path)
    grpc_rows = load_csv(grpc_path)

    sizes = [int(r["payload_size"]) for r in rest_rows]
    labels = [payload_label(s) for s in sizes]

    def get_pcts(rows):
        frm_pct, enc_pct = [], []
        for r in rows:
            sz = int(r["payload_size"])
            baseline = 2 * sz
            frm = int(r["header_bytes"])
            body = int(r["body_bytes"])
            enc = max(0, body - baseline)
            frm_pct.append((frm / baseline) * 100)
            enc_pct.append((enc / baseline) * 100)
        return frm_pct, enc_pct

    rest_frm, rest_enc = get_pcts(rest_rows)
    grpc_frm, grpc_enc = get_pcts(grpc_rows)

    out_csv = AGG_DIR / "overhead_decomposition.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["payload_size", "rest_framing_pct", "rest_encoding_pct", "rest_total_pct", "grpc_framing_pct", "grpc_encoding_pct", "grpc_total_pct"])
        for i in range(len(sizes)):
            writer.writerow([
                sizes[i], 
                f"{rest_frm[i]:.4f}", f"{rest_enc[i]:.4f}", f"{rest_frm[i]+rest_enc[i]:.4f}",
                f"{grpc_frm[i]:.4f}", f"{grpc_enc[i]:.4f}", f"{grpc_frm[i]+grpc_enc[i]:.4f}"
            ])
            
    print(f"[plot] Decomposition Table → {out_csv}")
    
    print("\n" + "="*89)
    print("OVERHEAD DECOMPOSITION TABLE (% ABOVE BASELINE)")
    print("="*89)
    print(f"{'Payload':>8} | {'REST Frm':>10} | {'REST Enc':>10} | {'REST Tot':>10} || {'gRPC Frm':>10} | {'gRPC Enc':>10} | {'gRPC Tot':>10}")
    print("-" * 89)
    for i in range(len(sizes)):
        r_f, r_e = rest_frm[i], rest_enc[i]
        g_f, g_e = grpc_frm[i], grpc_enc[i]
        print(f"{labels[i]:>8} | {r_f:>9.3f}% | {r_e:>9.3f}% | {r_f+r_e:>9.3f}% || {g_f:>9.3f}% | {g_e:>9.3f}% | {g_f+g_e:>9.3f}%")
    print("="*89 + "\n")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_overhead_ratio()
    plot_header_body_ratio()
    generate_decomposition_table()
    print("[plot_space] done")


if __name__ == "__main__":
    main()
