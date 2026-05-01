#!/bin/bash
# run_experiment.sh — master orchestrator for space and time experiments
#
# Two-machine setup (client runs this script, server runs the Go binaries):
#   Client  →  runs k6, tcpdump, tshark analysis
#   Server  →  runs rest-server on :8080, grpc-server on :50051
#
# Prerequisites on client machine (Ubuntu):
#   - k6                   (load generator)
#   - tcpdump, tshark      (packet capture + analysis)
#   - python3, matplotlib  (aggregation + plotting)
#
# Environment variables:
#   SERVER_IP   (required) — IP address of the server machine
#   IFACE       (required) — network interface facing the server (e.g. eth0, enp3s0)
#   K6_BIN      (optional) — path to k6 binary (default: k6)
#
# Usage:
#   SERVER_IP=192.168.1.2 IFACE=eth0 ./scripts/run_experiment.sh all
#   SERVER_IP=192.168.1.2 IFACE=eth0 ./scripts/run_experiment.sh space
#   SERVER_IP=192.168.1.2 IFACE=eth0 ./scripts/run_experiment.sh time

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ── required env ─────────────────────────────────────────────────────
SERVER_IP="${SERVER_IP:?Set SERVER_IP to the server machines IP}"
IFACE="${IFACE:?Set IFACE to the network interface facing the server (e.g. eth0)}"
