#!/bin/bash
# run_experiment.sh - master orchestrator for space and time experiments
#
# Usage:
#   ./run_experiment.sh space
#   ./run_experiment.sh time
#   ./run_experiment.sh all

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

K6_BIN="${K6_BIN:-k6}"
SERVER_IP="${SERVER_IP:?Set SERVER_IP to the server machine's IP}"
SPACE_ITERS=100

PAYLOAD_SIZES=(32 64 128 512 1024 8192 65536 524288)
STRUCTURES=(flat nested wide array)
PROTOCOLS=(rest grpc)

log() { echo "[experiment] $(date '+%H:%M:%S') $*"; }

run_space() {
  local iface="${IFACE:?Set IFACE to the network interface for tcpdump}"
  log "=== SPACE EXPERIMENT ==="

  mkdir -p "${PROJECT_ROOT}/metrics/raw/space" \
           "${PROJECT_ROOT}/metrics/raw/pcaps"

  for proto in "${PROTOCOLS[@]}"; do
    > "${PROJECT_ROOT}/metrics/raw/space/${proto}.csv"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "space: protocol=${proto} payload_size=${size}"

      "${SCRIPT_DIR}/capture_network.sh" start "$proto" "$size" "$iface" "$SERVER_IP"

      ${K6_BIN} run \
        -e "PROTOCOL=${proto}" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "ITERATIONS=${SPACE_ITERS}" \
        "${PROJECT_ROOT}/client/space/sweep.js" \
        2>&1 | head -20 || true

      "${SCRIPT_DIR}/capture_network.sh" stop

      "${SCRIPT_DIR}/analyse_pcap.sh" \
        "${PROJECT_ROOT}/metrics/raw/pcaps/${proto}_${size}.pcap"
    done
  done

  log "=== SPACE EXPERIMENT COMPLETE ==="
}

run_time() {
  log "=== TIME EXPERIMENT ==="

  mkdir -p "${PROJECT_ROOT}/metrics/raw/time"

  for proto in "${PROTOCOLS[@]}"; do
    for struct in "${STRUCTURES[@]}"; do
      local csv_file="${PROJECT_ROOT}/metrics/raw/time/${proto}_${struct}.csv"
      echo "iteration,client_ns,server_ns,total_ns" > "$csv_file"

      for size in "${PAYLOAD_SIZES[@]}"; do
        log "time: protocol=${proto} structure=${struct} payload_size=${size}"

        ${K6_BIN} run \
          -e "PROTOCOL=${proto}" \
          -e "SERVER_IP=${SERVER_IP}" \
          -e "PAYLOAD_SIZE=${size}" \
          -e "STRUCTURE=${struct}" \
          "${PROJECT_ROOT}/client/time/sweep.js" \
          2>&1 \
          | sed -n 's/.*msg="\([0-9][0-9]*,.*\)".*/\1/p' >> "$csv_file" || true
      done

      rows=$(wc -l < "$csv_file")
      log "  -> ${csv_file} (${rows} rows)"
    done
  done

  log "=== TIME EXPERIMENT COMPLETE ==="
}

case "${1:-all}" in
  space)  run_space ;;
  time)   run_time  ;;
  all)    run_space; run_time ;;
  *)
    echo "Usage: $0 {space|time|all}"
    exit 1
    ;;
esac