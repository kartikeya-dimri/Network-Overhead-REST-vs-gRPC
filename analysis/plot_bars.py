#!/usr/bin/env python3
"""
plot_bars.py — bar chart visualisations for encoding and framing overhead

Generates:
  1. Encoding Overhead (body_bytes / logical_payload_size)
     - 4 individual bar charts (one per structure)
     - 1 combined 2×2 grid

  2. Framing Overhead (header_bytes)
     - 4 individual bar charts (one per structure)
     - 1 combined 2×2 grid

Reads:  metrics/raw/space/{rest,grpc}_{struct}.csv
Writes: results/encoding_overhead_{struct}.png      (×4)
        results/encoding_overhead_2x2.png
        results/framing_overhead_{struct}.png        (×4)
        results/framing_overhead_2x2.png

Usage:
  python3 analysis/plot_bars.py
"""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")       # non-interactive backend — no GUI needed
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ── paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR      = PROJECT_ROOT / "metrics" / "raw" / "space"
RESULTS_DIR  = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── constants ────────────────────────────────────────────────────────────
STRUCTURES   = ["flat", "nested", "wide", "array"]
STRUCT_TITLES = {"flat": "Flat", "nested": "Nested", "wide": "Wide", "array": "Array"}

# Premium colour palette
REST_COLOR = "#E74C3C"   # warm red
GRPC_COLOR = "#3498DB"   # cool blue

# Global matplotlib styling
plt.rcParams.update({
    "figure.facecolor":  "#FAFAFA",
    "axes.facecolor":    "#FAFAFA",
    "axes.edgecolor":    "#CCCCCC",
    "axes.grid":         True,
    "grid.alpha":        0.25,
    "grid.linestyle":    "--",
    "font.family":       "sans-serif",
    "font.size":         11,
    "axes.titlesize":    14,
    "axes.labelsize":    12,
    "xtick.labelsize":   10,
    "ytick.labelsize":   10,
})

BAR_WIDTH = 0.32          # width of each bar
DPI       = 180           # output resolution


# ── helpers ──────────────────────────────────────────────────────────────

def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def payload_label(size_bytes):
    if size_bytes >= 1024:
        return f"{size_bytes // 1024} KB"
    return f"{size_bytes} B"


def load_structure_data(struct):
    """Return (sizes[], rest_dict, grpc_dict) for a structure.
    Each dict maps payload_size → {wire_bytes, header_bytes, body_bytes}.
    """
    rest_rows = load_csv(RAW_DIR / f"rest_{struct}.csv")
    grpc_rows = load_csv(RAW_DIR / f"grpc_{struct}.csv")

    sizes = sorted(set(int(r["payload_size"]) for r in rest_rows))

    def to_dict(rows):
        d = {}
        for r in rows:
            s = int(r["payload_size"])
            d[s] = {
                "wire":   int(r["wire_bytes"]),
                "header": int(r["header_bytes"]),
                "body":   int(r["body_bytes"]),
            }
        return d

    return sizes, to_dict(rest_rows), to_dict(grpc_rows)


# ── single-structure bar plot ────────────────────────────────────────────

def _draw_encoding_bars(ax, struct, sizes, rest, grpc):
    """Draw encoding-overhead bars on the given axes."""
    x = np.arange(len(sizes))
    rest_ratios = [rest[s]["body"] / s for s in sizes]
    grpc_ratios = [grpc[s]["body"] / s for s in sizes]

    bars_r = ax.bar(x - BAR_WIDTH / 2, rest_ratios, BAR_WIDTH,
                    color=REST_COLOR, edgecolor="white", linewidth=0.6,
                    label="REST (JSON)", zorder=3)
    bars_g = ax.bar(x + BAR_WIDTH / 2, grpc_ratios, BAR_WIDTH,
                    color=GRPC_COLOR, edgecolor="white", linewidth=0.6,
                    label="gRPC (Protobuf)", zorder=3)

    # value labels on top of each bar
    for bar in bars_r:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.08,
                f"{h:.1f}×", ha="center", va="bottom", fontsize=7.5,
                color=REST_COLOR, fontweight="bold")
    for bar in bars_g:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.08,
                f"{h:.1f}×", ha="center", va="bottom", fontsize=7.5,
                color=GRPC_COLOR, fontweight="bold")

    ax.axhline(y=1.0, color="#888888", linestyle="--", linewidth=1, alpha=0.6,
               label="1× (no overhead)")
    ax.set_xticks(x)
    ax.set_xticklabels([payload_label(s) for s in sizes])
    ax.set_ylabel("Encoding Ratio  (body bytes / logical bytes)")
    ax.set_title(f"{STRUCT_TITLES[struct]} — Encoding Overhead")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_ylim(bottom=0)


def _draw_framing_bars(ax, struct, sizes, rest, grpc):
    """Draw framing-overhead bars on the given axes."""
    x = np.arange(len(sizes))
    rest_hdrs = [rest[s]["header"] for s in sizes]
    grpc_hdrs = [grpc[s]["header"] for s in sizes]

    bars_r = ax.bar(x - BAR_WIDTH / 2, rest_hdrs, BAR_WIDTH,
                    color=REST_COLOR, edgecolor="white", linewidth=0.6,
                    label="REST (HTTP/1.1)", zorder=3)
    bars_g = ax.bar(x + BAR_WIDTH / 2, grpc_hdrs, BAR_WIDTH,
                    color=GRPC_COLOR, edgecolor="white", linewidth=0.6,
                    label="gRPC (HTTP/2)", zorder=3)

    # value labels
    for bar in bars_r:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 1,
                f"{h}", ha="center", va="bottom", fontsize=7.5,
                color=REST_COLOR, fontweight="bold")
    for bar in bars_g:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 1,
                f"{h}", ha="center", va="bottom", fontsize=7.5,
                color=GRPC_COLOR, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([payload_label(s) for s in sizes])
    ax.set_ylabel("Header Bytes (per request)")
    ax.set_title(f"{STRUCT_TITLES[struct]} — Framing Overhead")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_ylim(bottom=0)


# ── main plot drivers ────────────────────────────────────────────────────

def plot_encoding_individual():
    """4 individual encoding-overhead bar charts."""
    for struct in STRUCTURES:
        sizes, rest, grpc = load_structure_data(struct)
        fig, ax = plt.subplots(figsize=(8, 5))
        _draw_encoding_bars(ax, struct, sizes, rest, grpc)
        ax.set_xlabel("Payload Size (logical bytes)")
        fig.tight_layout()
        out = RESULTS_DIR / f"encoding_overhead_{struct}.png"
        fig.savefig(out, dpi=DPI)
        plt.close(fig)
        print(f"[plot] encoding individual → {out}")


def plot_encoding_2x2():
    """2×2 grid of encoding-overhead bar charts."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("Encoding Overhead  (body bytes / logical bytes)  — by Structure",
                 fontsize=17, fontweight="bold", y=0.98)

    for idx, struct in enumerate(STRUCTURES):
        ax = axes[idx // 2][idx % 2]
        sizes, rest, grpc = load_structure_data(struct)
        _draw_encoding_bars(ax, struct, sizes, rest, grpc)

    for ax in axes[1]:
        ax.set_xlabel("Payload Size (logical bytes)")

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = RESULTS_DIR / "encoding_overhead_2x2.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"[plot] encoding 2×2 → {out}")


def plot_framing_individual():
    """4 individual framing-overhead bar charts."""
    for struct in STRUCTURES:
        sizes, rest, grpc = load_structure_data(struct)
        fig, ax = plt.subplots(figsize=(8, 5))
        _draw_framing_bars(ax, struct, sizes, rest, grpc)
        ax.set_xlabel("Payload Size (logical bytes)")
        fig.tight_layout()
        out = RESULTS_DIR / f"framing_overhead_{struct}.png"
        fig.savefig(out, dpi=DPI)
        plt.close(fig)
        print(f"[plot] framing individual → {out}")


def plot_framing_2x2():
    """2×2 grid of framing-overhead bar charts."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("Framing Overhead  (header bytes per request)  — by Structure",
                 fontsize=17, fontweight="bold", y=0.98)

    for idx, struct in enumerate(STRUCTURES):
        ax = axes[idx // 2][idx % 2]
        sizes, rest, grpc = load_structure_data(struct)
        _draw_framing_bars(ax, struct, sizes, rest, grpc)

    for ax in axes[1]:
        ax.set_xlabel("Payload Size (logical bytes)")

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = RESULTS_DIR / "framing_overhead_2x2.png"
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"[plot] framing 2×2 → {out}")


# ── entry point ──────────────────────────────────────────────────────────

def main():
    print("[plot_bars] generating encoding & framing bar charts...")
    plot_encoding_individual()
    plot_encoding_2x2()
    plot_framing_individual()
    plot_framing_2x2()
    print("[plot_bars] done — 10 charts written")


if __name__ == "__main__":
    main()
