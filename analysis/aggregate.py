#!/usr/bin/env python3
"""
aggregate.py — post-processing pipeline for raw experiment data.

Reads raw CSVs from metrics/raw/ and produces aggregated CSVs in
metrics/aggregated/:

  overhead_ratio.csv      — O1 = wire_bytes / logical_payload_bytes
  header_body_ratio.csv   — O2 = wire_bytes / encoded_body_bytes
  ser_deser_overhead.csv  — O3 = mean(total_ns), warm-up trimmed

Input space:  Payload Size × Structure × Protocol

Usage:
  python3 aggregate.py                     # process everything
  python3 aggregate.py --space-only        # only O1 + O2
  python3 aggregate.py --time-only         # only O3
"""

import argparse
import csv
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_SPACE_DIR = PROJECT_ROOT / "metrics" / "raw" / "space"
RAW_TIME_DIR  = PROJECT_ROOT / "metrics" / "raw" / "time"
AGG_DIR       = PROJECT_ROOT / "metrics" / "aggregated"

# Logical payload sizes (pre-serialization application data in bytes)
PAYLOAD_SIZES = [32, 64, 128, 512, 1024, 8192]
STRUCTURES = ["flat", "nested", "wide", "array"]

# Fraction of warm-up samples to discard from the front
WARMUP_FRACTION = 0.10


def read_csv(filepath):
    """Read a CSV file into a list of dicts."""
    rows = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def aggregate_space():
    """
    Compute O1 (overhead ratio) and O2 (header+body : body ratio)
    from raw space CSVs.

    Raw CSV schema: payload_size,structure,wire_bytes,header_bytes,body_bytes
    Files:          rest_{structure}.csv, grpc_{structure}.csv
    """
    o1_rows = []  # payload_size, structure, rest_O1, grpc_O1
    o2_rows = []  # payload_size, structure, rest_O2, grpc_O2

    # Load raw data keyed by (protocol, structure, payload_size)
    data = {}  # (protocol, structure, payload_size_int) → dict
    for proto in ("rest", "grpc"):
        for struct in STRUCTURES:
            csv_path = RAW_SPACE_DIR / f"{proto}_{struct}.csv"
            if not csv_path.exists():
                print(f"[warn] {csv_path} not found, skipping {proto}/{struct}", file=sys.stderr)
                continue
            for row in read_csv(csv_path):
                key = (proto, struct, int(row["payload_size"]))
                data[key] = {
                    "wire_bytes":   int(row["wire_bytes"]),
                    "header_bytes": int(row["header_bytes"]),
                    "body_bytes":   int(row["body_bytes"]),
                }

    for struct in STRUCTURES:
        for size in PAYLOAD_SIZES:
            rest = data.get(("rest", struct, size))
            grpc = data.get(("grpc", struct, size))

            # O1 = wire_bytes / logical_payload_bytes
            rest_o1 = rest["wire_bytes"] / size if rest else ""
            grpc_o1 = grpc["wire_bytes"] / size if grpc else ""
            o1_rows.append({
                "payload_size": size,
                "structure": struct,
                "rest_O1": rest_o1,
                "grpc_O1": grpc_o1,
            })

            # O2 = wire_bytes / encoded_body_bytes  (= (header+body) / body)
            rest_o2 = rest["wire_bytes"] / rest["body_bytes"] if rest and rest["body_bytes"] else ""
            grpc_o2 = grpc["wire_bytes"] / grpc["body_bytes"] if grpc and grpc["body_bytes"] else ""
            o2_rows.append({
                "payload_size": size,
                "structure": struct,
                "rest_O2": rest_o2,
                "grpc_O2": grpc_o2,
            })

    # Write O1
    o1_path = AGG_DIR / "overhead_ratio.csv"
    with open(o1_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["payload_size", "structure", "rest_O1", "grpc_O1"])
        w.writeheader()
        w.writerows(o1_rows)
    print(f"[aggregate] O1 → {o1_path} ({len(o1_rows)} rows)")

    # Write O2
    o2_path = AGG_DIR / "header_body_ratio.csv"
    with open(o2_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["payload_size", "structure", "rest_O2", "grpc_O2"])
        w.writeheader()
        w.writerows(o2_rows)
    print(f"[aggregate] O2 → {o2_path} ({len(o2_rows)} rows)")


def aggregate_time():
    """
    Compute O3 (mean ser/deser overhead) from raw time CSVs.
    Discards the first WARMUP_FRACTION of samples per file.

    Raw CSV schema: iteration,client_ns,server_ns,total_ns
    Aggregated schema: payload_size,structure,rest_O3_mean_us,grpc_O3_mean_us
    """
    # Collect per-configuration means: (structure, size) → {rest: mean_us, grpc: mean_us}
    means = {}

    for proto in ("rest", "grpc"):
        for struct in STRUCTURES:
            csv_path = RAW_TIME_DIR / f"{proto}_{struct}.csv"
            if not csv_path.exists():
                print(f"[warn] {csv_path} not found, skipping", file=sys.stderr)
                continue

            rows = read_csv(csv_path)

            # The raw CSV may contain data for multiple payload sizes
            # (appended by the orchestrator). Group by payload size blocks.
            # Since data is appended in order, each block has ~1000 rows.
            # We split by iteration resets (iteration goes 0..999, 0..999, ...).
            blocks = split_into_blocks(rows)

            for block, size in zip(blocks, PAYLOAD_SIZES):
                total_ns_values = [int(r["total_ns"]) for r in block]

                # Discard warm-up
                warmup_count = int(len(total_ns_values) * WARMUP_FRACTION)
                trimmed = total_ns_values[warmup_count:]

                if not trimmed:
                    continue

                mean_ns = sum(trimmed) / len(trimmed)
                mean_us = mean_ns / 1000.0  # ns → µs

                key = (struct, size)
                if key not in means:
                    means[key] = {}
                means[key][proto] = mean_us

    # Write aggregated CSV
    o3_rows = []
    for struct in STRUCTURES:
        for size in PAYLOAD_SIZES:
            key = (struct, size)
            m = means.get(key, {})
            o3_rows.append({
                "payload_size":     size,
                "structure":        struct,
                "rest_O3_mean_us":  f"{m.get('rest', ''):.2f}" if "rest" in m else "",
                "grpc_O3_mean_us":  f"{m.get('grpc', ''):.2f}" if "grpc" in m else "",
            })

    o3_path = AGG_DIR / "ser_deser_overhead.csv"
    with open(o3_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "payload_size", "structure", "rest_O3_mean_us", "grpc_O3_mean_us",
        ])
        w.writeheader()
        w.writerows(o3_rows)
    print(f"[aggregate] O3 → {o3_path} ({len(o3_rows)} rows)")


def split_into_blocks(rows):
    """
    Split a list of CSV rows into blocks where each block corresponds to
    one payload size run (~1000 iterations). Splits on iteration resets
    (when iteration goes from a high number back to 0).
    """
    if not rows:
        return []

    blocks = []
    current_block = [rows[0]]

    for i in range(1, len(rows)):
        curr_iter = int(rows[i]["iteration"])
        prev_iter = int(rows[i - 1]["iteration"])
        if curr_iter <= prev_iter:
            # Iteration reset — start new block
            blocks.append(current_block)
            current_block = [rows[i]]
        else:
            current_block.append(rows[i])

    if current_block:
        blocks.append(current_block)

    return blocks


def main():
    parser = argparse.ArgumentParser(description="Aggregate raw experiment data")
    parser.add_argument("--space-only", action="store_true")
    parser.add_argument("--time-only", action="store_true")
    args = parser.parse_args()

    AGG_DIR.mkdir(parents=True, exist_ok=True)

    do_space = not args.time_only
    do_time = not args.space_only

    if do_space:
        aggregate_space()
    if do_time:
        aggregate_time()

    print("[aggregate] done")


if __name__ == "__main__":
    main()
