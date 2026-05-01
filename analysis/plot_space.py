#!/usr/bin/env python3
"""
plot_space.py — generate space overhead plots for Payload × Structure × Protocol

Reads:  metrics/aggregated/overhead_ratio.csv    (has structure column)
        metrics/aggregated/header_body_ratio.csv  (has structure column)
        metrics/raw/space/rest_{struct}.csv
        metrics/raw/space/grpc_{struct}.csv
Writes: results/overhead_ratio_2x2.png
        results/header_body_ratio_2x2.png
        results/overhead_decomposition.csv   (+ printed table)

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
RAW_DIR      = PROJECT_ROOT / "metrics" / "raw" / "space"
RESULTS_DIR  = PROJECT_ROOT / "results"

STRUCTURES = ["flat", "nested", "wide", "array"]
STRUCT_TITLES = {"flat": "Flat", "nested": "Nested", "wide": "Wide", "array": "Array"}

# Plot styling
COLORS = {"REST": "#E74C3C", "gRPC": "#3498DB"}
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
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


def plot_metric_2x2(csv_path, rest_col, grpc_col, ylabel, title_prefix, out_name):
    """
    Create a 2×2 grid of plots, one per structure, for a given metric.
    """
    if not csv_path.exists():
        print(f"[plot] {csv_path} not found, skipping {out_name}", file=sys.stderr)
        return

    rows = load_csv(csv_path)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
    fig.suptitle(f"{title_prefix} — by Structure", fontsize=16, fontweight="bold")

    for idx, struct in enumerate(STRUCTURES):
        ax = axes[idx // 2][idx % 2]

        struct_rows = [r for r in rows if r["structure"] == struct]
        if not struct_rows:
            ax.set_title(f"{STRUCT_TITLES[struct]} (no data)")
            continue

        rest_sizes = [int(r["payload_size"]) for r in struct_rows if r[rest_col]]
        rest_vals  = [float(r[rest_col]) for r in struct_rows if r[rest_col]]
        grpc_sizes = [int(r["payload_size"]) for r in struct_rows if r[grpc_col]]
        grpc_vals  = [float(r[grpc_col]) for r in struct_rows if r[grpc_col]]

        ax.plot(rest_sizes, rest_vals, 'o-', color=COLORS["REST"], linewidth=2,
                markersize=7, label="REST (HTTP/1.1 + JSON)")
        ax.plot(grpc_sizes, grpc_vals, 's-', color=COLORS["gRPC"], linewidth=2,
                markersize=7, label="gRPC (HTTP/2 + Protobuf)")

        ax.set_xscale("log", base=2)
        ax.set_title(STRUCT_TITLES[struct], fontsize=13)
        ax.set_ylabel(ylabel)
        ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5)
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(
            lambda x, _: payload_label(int(x))))
        ax.legend(fontsize=9)

    for ax in axes[1]:
        ax.set_xlabel("Payload Size")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = RESULTS_DIR / f"{out_name}.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[plot] {out_name} → {out_path}")


def plot_overhead_ratio():
    """Plot 1 — O1 = wire_bytes / logical_payload_bytes, 2×2 by structure."""
    plot_metric_2x2(
        csv_path=AGG_DIR / "overhead_ratio.csv",
        rest_col="rest_O1",
        grpc_col="grpc_O1",
        ylabel="Overhead Ratio (wire / logical)",
        title_prefix="Overhead Ratio vs Payload Size",
        out_name="overhead_ratio_2x2",
    )


def plot_header_body_ratio():
    """Plot 2 — O2 = wire_bytes / encoded_body_bytes, 2×2 by structure."""
    plot_metric_2x2(
        csv_path=AGG_DIR / "header_body_ratio.csv",
        rest_col="rest_O2",
        grpc_col="grpc_O2",
        ylabel="Framing Ratio (wire / body)",
        title_prefix="Framing Overhead vs Payload Size",
        out_name="header_body_ratio_2x2",
    )


def generate_decomposition_table():
    """
    Generate Framing vs Encoding overhead % decomposition table,
    now for each structure.
    """
    all_data = {}  # (proto, struct, size) → dict

    for proto in ("rest", "grpc"):
        for struct in STRUCTURES:
            csv_path = RAW_DIR / f"{proto}_{struct}.csv"
            if not csv_path.exists():
                continue
            for row in load_csv(csv_path):
                key = (proto, struct, int(row["payload_size"]))
                all_data[key] = {
                    "wire_bytes":   int(row["wire_bytes"]),
                    "header_bytes": int(row["header_bytes"]),
                    "body_bytes":   int(row["body_bytes"]),
                }

    if not all_data:
        print("[plot] No raw space data found, skipping decomposition table", file=sys.stderr)
        return

    # Collect all payload sizes from the data
    sizes = sorted(set(s for (_, _, s) in all_data.keys()))

    # Write CSV
    out_csv = AGG_DIR / "overhead_decomposition.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "payload_size", "structure",
            "rest_framing_pct", "rest_encoding_pct", "rest_total_pct",
            "grpc_framing_pct", "grpc_encoding_pct", "grpc_total_pct",
        ])
        for struct in STRUCTURES:
            for size in sizes:
                rest = all_data.get(("rest", struct, size))
                grpc = all_data.get(("grpc", struct, size))
                baseline = size  # request logical bytes only (client->server)

                def pcts(d):
                    if not d:
                        return 0, 0
                    frm = d["header_bytes"]
                    enc = max(0, d["body_bytes"] - baseline)
                    return (frm / baseline) * 100, (enc / baseline) * 100

                r_frm, r_enc = pcts(rest)
                g_frm, g_enc = pcts(grpc)
                writer.writerow([
                    size, struct,
                    f"{r_frm:.4f}", f"{r_enc:.4f}", f"{r_frm + r_enc:.4f}",
                    f"{g_frm:.4f}", f"{g_enc:.4f}", f"{g_frm + g_enc:.4f}",
                ])
    print(f"[plot] Decomposition Table → {out_csv}")

    # Print table to stdout
    print(f"\n{'=' * 99}")
    print("OVERHEAD DECOMPOSITION TABLE (% ABOVE BASELINE) — by Structure")
    print(f"{'=' * 99}")
    print(f"{'Struct':>8} {'Payload':>8} | {'REST Frm':>10} | {'REST Enc':>10} | {'REST Tot':>10} ||"
          f" {'gRPC Frm':>10} | {'gRPC Enc':>10} | {'gRPC Tot':>10}")
    print("-" * 99)

    for struct in STRUCTURES:
        for size in sizes:
            rest = all_data.get(("rest", struct, size))
            grpc = all_data.get(("grpc", struct, size))
            baseline = size

            def pcts(d):
                if not d:
                    return 0, 0
                frm = d["header_bytes"]
                enc = max(0, d["body_bytes"] - baseline)
                return (frm / baseline) * 100, (enc / baseline) * 100

            r_f, r_e = pcts(rest)
            g_f, g_e = pcts(grpc)
            label = payload_label(size)
            print(f"{struct:>8} {label:>8} | {r_f:>9.3f}% | {r_e:>9.3f}% | {r_f+r_e:>9.3f}% ||"
                  f" {g_f:>9.3f}% | {g_e:>9.3f}% | {g_f+g_e:>9.3f}%")
        if struct != STRUCTURES[-1]:
            print("-" * 99)

    print("=" * 99 + "\n")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_overhead_ratio()
    plot_header_body_ratio()
    generate_decomposition_table()
    print("[plot_space] done")


if __name__ == "__main__":
    main()
