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
K6_BIN="${K6_BIN:-k6}"

# ── experiment parameters ────────────────────────────────────────────
PAYLOAD_SIZES=(32 64 128 512 1024 8192)
STRUCTURES=(flat nested wide array)
SPACE_ITERS=100       # requests per space data point (amortize connection setup)

REST_PORT=8080
GRPC_PORT=50051

REST_URL="http://${SERVER_IP}:${REST_PORT}/echo"
GRPC_ADDR="${SERVER_IP}:${GRPC_PORT}"

# ── directories ──────────────────────────────────────────────────────
RAW_SPACE="${PROJECT_ROOT}/metrics/raw/space"
RAW_TIME="${PROJECT_ROOT}/metrics/raw/time"
PCAP_DIR="${PROJECT_ROOT}/metrics/raw/pcaps"

log() { echo -e "\n\033[1;36m[experiment]\033[0m $(date '+%H:%M:%S') $*"; }

# Prime sudo credentials (needed for tcpdump)
echo "[experiment] Priming sudo credentials for tcpdump..."
sudo -v
# Keep-alive: update existing sudo time stamp in the background
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &
KEEPALIVE_PID=$!
trap 'kill $KEEPALIVE_PID 2>/dev/null || true' EXIT

# Helper: extract CSV data rows from k6 structured log output.
# k6 wraps console.log as:  level=info msg="0,123,456,579" source=console
extract_csv() {
  sed -n 's/.*msg="\([0-9][0-9]*,.*\)".*/\1/p'
}

# ──────────────────────────────────────────────────────────────────────
# Connectivity check
# ──────────────────────────────────────────────────────────────────────
check_server() {
  log "Checking connectivity to server ${SERVER_IP}..."

  # Check REST
  if nc -z -w3 "$SERVER_IP" "$REST_PORT" 2>/dev/null; then
    log "  ✓ REST server reachable on :${REST_PORT}"
  else
    log "  ✗ REST server NOT reachable on :${REST_PORT}"
    log "    Start the REST server on the server machine:"
    log "      ./rest-server"
    exit 1
  fi

  # Check gRPC
  if nc -z -w3 "$SERVER_IP" "$GRPC_PORT" 2>/dev/null; then
    log "  ✓ gRPC server reachable on :${GRPC_PORT}"
  else
    log "  ✗ gRPC server NOT reachable on :${GRPC_PORT}"
    log "    Start the gRPC server on the server machine:"
    log "      ./grpc-server"
    exit 1
  fi
}

# ──────────────────────────────────────────────────────────────────────
# Space experiment: Payload × Structure × Protocol
#   - tcpdump captures client→server traffic on the ethernet interface
#   - tshark analyses pcap for wire/header/body bytes (one-way only)
# ──────────────────────────────────────────────────────────────────────
run_space() {
  log "=== SPACE EXPERIMENT ==="
  log "  Server: ${SERVER_IP}  Interface: ${IFACE}"
  log "  Payload sizes: ${PAYLOAD_SIZES[*]}"
  log "  Structures: ${STRUCTURES[*]}"
  log "  Iterations per point: ${SPACE_ITERS}"

  mkdir -p "$RAW_SPACE" "$PCAP_DIR"

  # ---- REST space sweep (all structures) ----
  for struct in "${STRUCTURES[@]}"; do
    local rest_csv="${RAW_SPACE}/rest_${struct}.csv"
    echo "payload_size,structure,wire_bytes,header_bytes,body_bytes" > "$rest_csv"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "  space: REST / ${struct} / ${size}B"
      local pcap_file="${PCAP_DIR}/rest_${struct}_${size}.pcap"

      local iters=$SPACE_ITERS
      if [ "$size" -ge 65536 ]; then iters=10; fi

      # Start tcpdump: capture only client→server traffic (dst = server IP)
      sudo tcpdump -i "$IFACE" "dst host ${SERVER_IP} and port ${REST_PORT}" \
        -w "$pcap_file" -U 2>/dev/null &
      local TCPDUMP_PID=$!
      sleep 1

      # Run k6 — single connection, N requests
      ${K6_BIN} run \
        -e "PROTOCOL=rest" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "STRUCTURE=${struct}" \
        -e "ITERATIONS=${iters}" \
        client/space/sweep.js 2>&1 | tail -5

      sleep 1
      sudo kill -2 "$TCPDUMP_PID" 2>/dev/null || true
      wait "$TCPDUMP_PID" 2>/dev/null || true
      sleep 1

      # Fix pcap ownership (tcpdump runs as root)
      sudo chown "$(id -u):$(id -g)" "$pcap_file" 2>/dev/null || true

      # Analyse pcap — client→server only (already filtered by tcpdump dst filter)
      # Count actual requests via http.content_length
      local body_avg
      local awk_prog='NF { s += $1; c++ } END { if(c>0) printf "%.0f %d\n", s/c, c; else print "0 0" }'
      body_avg=$(tshark -r "$pcap_file" -Y "http.content_length" \
        -T fields -e http.content_length 2>/dev/null \
        | tr ',' '\n' | awk "$awk_prog")

      local body_bytes req_count wire_bytes header_bytes
      body_bytes=$(echo "$body_avg" | awk '{print $1}')
      req_count=$(echo "$body_avg" | awk '{print $2}')

      if [ "$req_count" -gt 0 ]; then
        wire_bytes=$(tshark -r "$pcap_file" \
          -T fields -e tcp.len 2>/dev/null \
          | awk -v c="$req_count" '{ s += $1 } END { printf "%.0f\n", s/c }')
        header_bytes=$((wire_bytes - body_bytes))
      else
        wire_bytes=0
        header_bytes=0
        body_bytes=0
      fi

      echo "${size},${struct},${wire_bytes},${header_bytes},${body_bytes}" >> "$rest_csv"
      log "    wire=${wire_bytes} header=${header_bytes} body=${body_bytes} [${req_count} reqs]"
    done
    log "  ✓ REST / ${struct} complete → ${rest_csv}"
  done

  # ---- gRPC space sweep (all structures) ----
  for struct in "${STRUCTURES[@]}"; do
    local grpc_csv="${RAW_SPACE}/grpc_${struct}.csv"
    echo "payload_size,structure,wire_bytes,header_bytes,body_bytes" > "$grpc_csv"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "  space: gRPC / ${struct} / ${size}B"
      local pcap_file="${PCAP_DIR}/grpc_${struct}_${size}.pcap"

      local iters=$SPACE_ITERS
      if [ "$size" -ge 65536 ]; then iters=10; fi

      # Start tcpdump: capture only client→server traffic
      sudo tcpdump -i "$IFACE" "dst host ${SERVER_IP} and port ${GRPC_PORT}" \
        -w "$pcap_file" -U 2>/dev/null &
      local TCPDUMP_PID=$!
      sleep 1

      ${K6_BIN} run \
        -e "PROTOCOL=grpc" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "STRUCTURE=${struct}" \
        -e "ITERATIONS=${iters}" \
        client/space/sweep.js 2>&1 | tail -5

      sleep 1
      sudo kill -2 "$TCPDUMP_PID" 2>/dev/null || true
      wait "$TCPDUMP_PID" 2>/dev/null || true
      sleep 1

      sudo chown "$(id -u):$(id -g)" "$pcap_file" 2>/dev/null || true

      # Analyse pcap — already filtered to client→server by tcpdump
      # HTTP/2: -d forces tshark to decode port as http2
      local body_avg
      local awk_prog='NF { s += $1; c++ } END { if(c>0) printf "%.0f %d\n", s/c, c; else print "0 0" }'
      body_avg=$(tshark -r "$pcap_file" -d tcp.port==${GRPC_PORT},http2 \
        -T fields -e grpc.message_length 2>/dev/null \
        | tr ',' '\n' | awk "$awk_prog")

      local body_bytes req_count wire_bytes header_bytes
      body_bytes=$(echo "$body_avg" | awk '{print $1}')
      req_count=$(echo "$body_avg" | awk '{print $2}')

      if [ "$req_count" -gt 0 ]; then
        wire_bytes=$(tshark -r "$pcap_file" -d tcp.port==${GRPC_PORT},http2 \
          -T fields -e tcp.len 2>/dev/null \
          | awk -v c="$req_count" '{ s += $1 } END { printf "%.0f\n", s/c }')
        header_bytes=$((wire_bytes - body_bytes))
      else
        wire_bytes=0
        header_bytes=0
        body_bytes=0
      fi

      echo "${size},${struct},${wire_bytes},${header_bytes},${body_bytes}" >> "$grpc_csv"
      log "    wire=${wire_bytes} header=${header_bytes} body=${body_bytes} [${req_count} reqs]"
    done
    log "  ✓ gRPC / ${struct} complete → ${grpc_csv}"
  done

  log "=== SPACE EXPERIMENT COMPLETE ==="
}

# ──────────────────────────────────────────────────────────────────────
# Time experiment: Payload × Structure × Protocol
#   - No tcpdump needed — timing comes from server-side nanosecond timer
# ──────────────────────────────────────────────────────────────────────
run_time() {
  log "=== TIME EXPERIMENT ==="

  mkdir -p "$RAW_TIME"

  for proto in rest grpc; do
    for struct in "${STRUCTURES[@]}"; do
      local csv_file="${RAW_TIME}/${proto}_${struct}.csv"
      echo "iteration,client_ns,server_ns,total_ns" > "$csv_file"

      for size in "${PAYLOAD_SIZES[@]}"; do
        log "  time: ${proto} / ${struct} / ${size}B"

        ${K6_BIN} run \
          -e "PROTOCOL=${proto}" \
          -e "SERVER_IP=${SERVER_IP}" \
          -e "PAYLOAD_SIZE=${size}" \
          -e "STRUCTURE=${struct}" \
          client/time/sweep.js 2>&1 \
          | extract_csv >> "$csv_file" || true
      done

      local rows
      rows=$(wc -l < "$csv_file")
      log "  ✓ ${csv_file} [${rows} rows]"
    done
  done

  log "=== TIME EXPERIMENT COMPLETE ==="
}

# ──────────────────────────────────────────────────────────────────────
# Aggregation + Plotting
# ──────────────────────────────────────────────────────────────────────
run_analysis() {
  log "STEP — Aggregating raw data"
  python3 "${PROJECT_ROOT}/analysis/aggregate.py"

  log "STEP — Generating plots"
  python3 "${PROJECT_ROOT}/analysis/plot_space.py"
  python3 "${PROJECT_ROOT}/analysis/plot_time.py"
  python3 "${PROJECT_ROOT}/analysis/plot_bars.py"
}

# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
MODE="${1:-all}"

case "$MODE" in
  space)
    check_server
    run_space
    run_analysis
    ;;
  time)
    check_server
    run_time
    run_analysis
    ;;
  all)
    check_server
    run_space
    run_time
    run_analysis
    ;;
  analysis)
    run_analysis
    ;;
  *)
    echo "Usage: $0 {all|space|time|analysis}"
    exit 1
    ;;
esac

log "==========================================="
log "EXPERIMENT COMPLETE"
log "==========================================="
log ""
log "Raw data:       metrics/raw/{space,time}/*.csv"
log "Pcap captures:  metrics/raw/pcaps/*.pcap"
log "Aggregated:     metrics/aggregated/*.csv"
log "Plots:          results/*.png"