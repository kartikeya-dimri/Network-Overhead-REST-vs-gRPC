#!/bin/bash
# run_experiment.sh — master orchestrator for space and time experiments
#
# Usage:
#   ./run_experiment.sh space   # run space experiment (O1, O2)
#   ./run_experiment.sh time    # run time experiment  (O3)
#   ./run_experiment.sh all     # run both
#
# Required environment variables:
#   SERVER_IP     IP address of the server machine
#   CLIENT_IP     IP address of the client machine (used by tcpdump filter)
#   IFACE         Network interface for tcpdump (e.g. eth0)  [space only]
#
# Optional:
#   K6_BIN        Path to k6 binary         (default: k6)
#   REST_BIN      Path to REST server binary (default: built from source)
#   GRPC_BIN      Path to gRPC server binary (default: built from source)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

K6_BIN="${K6_BIN:-k6}"
SERVER_IP="${SERVER_IP:?Set SERVER_IP to the server machine's IP}"
SPACE_ITERS=100

# Payload sizes to sweep (bytes)
PAYLOAD_SIZES=(128 512 1024 8192 65536 524288)

# Structures for time experiment
STRUCTURES=(flat nested)

# Protocols
PROTOCOLS=(rest grpc)

# ---- helpers ----
log() { echo "[experiment] $(date '+%H:%M:%S') $*"; }

# ---- space experiment ----
run_space() {
  local iface="${IFACE:?Set IFACE to the network interface for tcpdump}"
  log "=== SPACE EXPERIMENT ==="

  for proto in "${PROTOCOLS[@]}"; do
    # Clear raw CSV
    > "${PROJECT_ROOT}/metrics/raw/space/${proto}.csv"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "space: protocol=${proto} payload_size=${size}"

      # Start packet capture
      "${SCRIPT_DIR}/capture_network.sh" start "$proto" "$size" "$iface" "$SERVER_IP"

      # Run k6 — N iterations on a single connection
      ${K6_BIN} run \
        -e "PROTOCOL=${proto}" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "ITERATIONS=${SPACE_ITERS}" \
        "${PROJECT_ROOT}/client/space/sweep.js" \
        2>&1 | head -20

      # Stop capture
      "${SCRIPT_DIR}/capture_network.sh" stop

      # Analyse the pcap
      "${SCRIPT_DIR}/analyse_pcap.sh" \
        "${PROJECT_ROOT}/metrics/raw/pcaps/${proto}_${size}.pcap"
    done
  done

  log "=== SPACE EXPERIMENT COMPLETE ==="
}

# ---- time experiment ----
run_time() {
  log "=== TIME EXPERIMENT ==="

  for proto in "${PROTOCOLS[@]}"; do
    for struct in "${STRUCTURES[@]}"; do
      local csv_file="${PROJECT_ROOT}/metrics/raw/time/${proto}_${struct}.csv"
      # Write CSV header
      echo "iteration,client_ns,server_ns,total_ns" > "$csv_file"

      for size in "${PAYLOAD_SIZES[@]}"; do
        log "time: protocol=${proto} structure=${struct} payload_size=${size}"

        # Run k6 — 1000 iterations, extract CSV rows from k6's structured log output
        # k6 wraps console.log in: level=info msg="<data>" source=console
        ${K6_BIN} run \
          -e "PROTOCOL=${proto}" \
          -e "SERVER_IP=${SERVER_IP}" \
          -e "PAYLOAD_SIZE=${size}" \
          -e "STRUCTURE=${struct}" \
          "${PROJECT_ROOT}/client/time/sweep.js" \
          2>&1 \
          | sed -n 's/.*msg="\([0-9][0-9]*,.*\)".*/\1/p' >> "$csv_file"
      done

      log "  → ${csv_file} ($(wc -l < "$csv_file") rows)"
    done
  done

  log "=== TIME EXPERIMENT COMPLETE ==="
}

# ---- main ----
case "${1:-all}" in
  space)  run_space ;;
  time)   run_time  ;;
  all)    run_space; run_time ;;
  *)
    echo "Usage: $0 {space|time|all}"
    exit 1
    ;;
esac
