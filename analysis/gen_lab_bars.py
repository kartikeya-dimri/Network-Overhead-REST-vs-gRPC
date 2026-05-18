#!/usr/bin/env python3
"""
gen_lab_bars.py — regenerate all 4 lab result plots in a clean, readable style
inspired by Excel-style charts: white bg, data table below bars, muted palette.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RESULTS_DIR = "../results_lab"
STRUCTURES = ["flat", "nested", "wide", "array"]
STRUCT_LABEL = {"flat": "Flat", "nested": "Nested", "wide": "Wide", "array": "Array"}
SIZES = [32, 64, 128, 512, 1024, 8192]
SIZE_LABELS = ["32 B", "64 B", "128 B", "512 B", "1 KB", "8 KB"]

# ── Muted, professional palette (Excel-like) ─────────────────────────
REST_COLOR = "#4682B4"   # steel blue
GRPC_COLOR = "#7EAB53"   # sampled green
BAR_WIDTH = 0.30
DPI = 200

# ── Global style ─────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor":   "white",
    "axes.edgecolor":   "#B0B0B0",
    "axes.linewidth":   0.8,
    "axes.grid":        True,
    "grid.color":       "#D9D9D9",
    "grid.alpha":       0.7,
    "grid.linestyle":   "-",
    "grid.linewidth":   0.5,
    "font.family":      "sans-serif",
    "font.sans-serif":  ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size":        12,
    "axes.titlesize":   15,
    "axes.titleweight": "bold",
    "axes.labelsize":   13,
    "xtick.labelsize":  11,
    "ytick.labelsize":  11,
    "xtick.direction":  "out",
    "ytick.direction":  "out",
    "xtick.major.size": 4,
    "ytick.major.size": 4,
})

def payload_label_log(x, _):
    x = int(x)
    return f"{x // 1024} KB" if x >= 1024 else f"{x} B"


# ═══════════════════════════════════════════════════════════════════════
# Helper: draw a 2×2 bar-chart grid WITH a data table under each subplot
# ═══════════════════════════════════════════════════════════════════════
def draw_bar_2x2(data, ylabel, val_fmt, out_name, baseline=None, ylim=None):
    fig, axes = plt.subplots(2, 2, figsize=(18, 13), sharey=True)
    for idx, struct in enumerate(STRUCTURES):
        ax = axes[idx // 2][idx % 2]
        x = np.arange(len(SIZES))
        d = data[struct]

        # Bars
        ax.bar(x - BAR_WIDTH / 2, d["rest"], BAR_WIDTH,
               color=REST_COLOR, edgecolor="white", linewidth=0.8, zorder=3,
               label="REST (JSON)")
        ax.bar(x + BAR_WIDTH / 2, d["grpc"], BAR_WIDTH,
               color=GRPC_COLOR, edgecolor="white", linewidth=0.8, zorder=3,
               label="gRPC (Protobuf)")

        # Baseline dashed line
        if baseline is not None:
            ax.axhline(y=baseline, color="#888888", linestyle="--",
                       linewidth=0.8, alpha=0.5)

        # Axis config
        ax.set_xticks(x)
        ax.set_xticklabels(SIZE_LABELS)
        ax.set_ylabel(ylabel)
        ax.set_title(STRUCT_LABEL[struct])
        if ylim is not None:
            ax.set_ylim(ylim)
        else:
            ax.set_ylim(bottom=0)
        ax.tick_params(labelleft=True)   # keep y-labels on every subplot
        ax.set_axisbelow(True)

        # ── Data table below the bars ──
        row_rest = [val_fmt(v) for v in d["rest"]]
        row_grpc = [val_fmt(v) for v in d["grpc"]]
        table = ax.table(
            cellText=[row_rest, row_grpc],
            rowLabels=["  REST  ", "  gRPC  "],
            rowColours=[REST_COLOR, GRPC_COLOR],
            colLabels=None,
            cellLoc="center",
            loc="bottom",
            bbox=[0.0, -0.28, 1.0, 0.18],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(14)
        # Style row labels white text
        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor("#D0D0D0")
            cell.set_linewidth(0.5)
            if col == -1:  # row-label column
                cell.set_text_props(color="white", fontweight="bold")
            else:
                cell.set_text_props(fontweight="normal")


    fig.tight_layout(rect=[0, 0.03, 1, 1])
    fig.subplots_adjust(hspace=0.45)
    fig.savefig(f"{RESULTS_DIR}/{out_name}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[done] {out_name}")


# ═══════════════════════════════════════════════════════════════════════
# Helper: draw a 2×2 line-chart grid WITH a data table under each subplot
# ═══════════════════════════════════════════════════════════════════════
def draw_line_2x2(data, ylabel, val_fmt, out_name,
                  baseline=None, share_y=False):
    fig, axes = plt.subplots(2, 2, figsize=(18, 13), sharey=True)
    for idx, struct in enumerate(STRUCTURES):
        ax = axes[idx // 2][idx % 2]
        d = data[struct]

        ax.plot(SIZES, d["rest"], "o-", color=REST_COLOR, linewidth=2.5,
                markersize=8, markeredgecolor="white", markeredgewidth=1.2,
                label="REST (JSON)", zorder=4)
        ax.plot(SIZES, d["grpc"], "s-", color=GRPC_COLOR, linewidth=2.5,
                markersize=8, markeredgecolor="white", markeredgewidth=1.2,
                label="gRPC (Protobuf)", zorder=4)

        if baseline is not None:
            ax.axhline(y=baseline, color="#888888", linestyle="--",
                       linewidth=0.8, alpha=0.5)

        ax.set_xscale("log", base=2)
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(payload_label_log))
        ax.set_title(STRUCT_LABEL[struct])
        ax.set_ylabel(ylabel)
        ax.tick_params(labelleft=True)   # keep y-labels on every subplot
        ax.set_axisbelow(True)

        # ── Data table ──
        row_rest = [val_fmt(v) for v in d["rest"]]
        row_grpc = [val_fmt(v) for v in d["grpc"]]
        table = ax.table(
            cellText=[row_rest, row_grpc],
            rowLabels=["  REST  ", "  gRPC  "],
            rowColours=[REST_COLOR, GRPC_COLOR],
            colLabels=None,
            cellLoc="center",
            loc="bottom",
            bbox=[0.0, -0.32, 1.0, 0.18],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(14)
        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor("#D0D0D0")
            cell.set_linewidth(0.5)
            if col == -1:
                cell.set_text_props(color="white", fontweight="bold")


    fig.tight_layout(rect=[0, 0.03, 1, 1])
    fig.subplots_adjust(hspace=0.50)
    fig.savefig(f"{RESULTS_DIR}/{out_name}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[done] {out_name}")


# ═══════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════

encoding_data = {
    "flat":   {"rest": [2.4, 1.7, 1.4, 1.1, 1.0, 1.0], "grpc": [2.4, 1.7, 1.3, 1.1, 1.1, 1.0]},
    "nested": {"rest": [5.4, 5.2, 5.4, 5.3, 5.3, 5.3], "grpc": [2.0, 2.0, 2.0, 2.0, 2.0, 2.0]},
    "wide":   {"rest": [5.5, 5.6, 5.7, 5.8, 5.9, 5.9], "grpc": [5.5, 5.6, 5.7, 5.8, 5.8, 5.9]},
    "array":  {"rest": [4.4, 4.4, 4.1, 4.0, 3.8, 3.6], "grpc": [1.9, 1.9, 1.8, 1.7, 1.6, 1.5]},
}

framing_data = {
    "flat":   {"rest": [132, 133, 133, 133, 134, 131], "grpc": [81, 81, 81, 81, 81, 81]},
    "nested": {"rest": [133, 133, 133, 134, 134, 131], "grpc": [81, 81, 81, 81, 81, 103]},
    "wide":   {"rest": [133, 133, 133, 134, 134, 134], "grpc": [81, 81, 81, 81, 81, 81]},
    "array":  {"rest": [133, 133, 133, 134, 134, 131], "grpc": [81, 81, 81, 81, 81, 81]},
}

overhead_ratio_data = {
    "flat":   {"rest": [6.53, 3.78, 2.39, 1.35, 1.17, 1.02],
               "grpc": [4.91, 2.95, 1.98, 1.26, 1.13, 1.02]},
    "nested": {"rest": [9.59, 7.33, 6.40, 5.60, 5.46, 5.35],
               "grpc": [4.53, 3.27, 2.64, 2.17, 2.09, 2.02]},
    "wide":   {"rest": [9.69, 7.69, 6.72, 6.05, 6.02, 6.13],
               "grpc": [8.03, 6.86, 6.31, 5.94, 5.97, 6.13]},
    "array":  {"rest": [8.56, 6.47, 5.14, 4.29, 3.98, 3.57],
               "grpc": [4.41, 3.14, 2.38, 1.85, 1.69, 1.56]},
}

ser_deser_data = {
    "flat":   {"rest": [6.29, 6.06, 8.04, 11.28, 16.42, 41.97],
               "grpc": [1.49, 1.53, 1.55, 1.88, 2.19, 5.72]},
    "nested": {"rest": [15.62, 18.93, 36.02, 91.19, 150.50, 1161.48],
               "grpc": [2.33, 3.73, 6.49, 23.84, 46.75, 323.38]},
    "wide":   {"rest": [11.41, 17.25, 31.07, 64.14, 113.14, 937.63],
               "grpc": [2.53, 4.37, 7.25, 25.55, 52.07, 358.82]},
    "array":  {"rest": [16.58, 25.93, 38.99, 82.52, 139.50, 886.77],
               "grpc": [1.78, 3.05, 4.92, 14.19, 26.69, 177.71]},
}

# ═══════════════════════════════════════════════════════════════════════
# GENERATE PLOTS
# ═══════════════════════════════════════════════════════════════════════

draw_bar_2x2(
    encoding_data,
    ylabel="Encoding Ratio  (body / logical)",
    val_fmt=lambda v: f"{v:.1f}×",
    out_name="encoding_overhead_2x2.png",
    baseline=1.0,
    ylim=(0, 6.5),
)

draw_bar_2x2(
    framing_data,
    ylabel="Header Bytes (per request)",
    val_fmt=lambda v: f"{int(v)}",
    out_name="framing_overhead_2x2.png",
)

draw_line_2x2(
    overhead_ratio_data,
    ylabel="Overhead Ratio (wire / logical)",
    val_fmt=lambda v: f"{v:.2f}",
    out_name="overhead_ratio_2x2.png",
    baseline=1.0,
)

draw_line_2x2(
    ser_deser_data,
    ylabel="Ser + Deser Time (µs)",
    val_fmt=lambda v: f"{v:.2f}",
    out_name="ser_deser_2x2_grid.png",
    share_y=True,
)
