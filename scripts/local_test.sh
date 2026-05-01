#!/bin/bash
# local_test.sh — run a full end-to-end sanity check on macOS
#
# Runs BOTH experiments locally:
#   1. Space experiment (tcpdump on lo0 → tshark analysis)
#   2. Time experiment  (k6 20-iteration sweeps)
# Then aggregates and plots.
#
# Usage:
#   ./scripts/local_test.sh          # run everything
#   ./scripts/local_test.sh time     # time experiment only
#   ./scripts/local_test.sh space    # space experiment only

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

ITERS=20                   # reduced iterations for quick local test
SERVER_IP=127.0.0.1
K6_BIN="${K6_BIN:-k6}"
IFACE="lo0"               # macOS loopback interface
SPACE_ITERS=100           # run 100 iterations on a single connection to amortize handshake

PAYLOAD_SIZES=(32 64 128 512 1024 8192)
STRUCTURES=(flat nested wide array)

log() { echo -e "\n\033[1;36m[local-test]\033[0m $(date '+%H:%M:%S') $*"; }

cleanup() {
  log "cleaning up..."
  lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
  lsof -ti:50051 2>/dev/null | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT

wait_for_port() {
  local port=$1
  for i in {1..50}; do
    nc -z 127.0.0.1 "$port" 2>/dev/null && return 0
    sleep 0.1
  done
  log "WARNING: Port $port did not open in time"
}

# Helper: extract CSV data rows from k6 structured log output.
# k6 wraps console.log as:  level=info msg="0,123,456,579" source=console
extract_csv() {
  sed -n 's/.*msg="\([0-9][0-9]*,.*\)".*/\1/p'
}

MODE="${1:-all}"

# ──────────────────────────────────────────────────────────────────────
# Step 0: Build servers
# ──────────────────────────────────────────────────────────────────────
log "STEP 0 — Building servers"
cd "$PROJECT_ROOT"
go build -o rest-server ./servers/rest/
go build -o grpc-server ./servers/grpc/
log "  ✓ rest-server and grpc-server built"

# ──────────────────────────────────────────────────────────────────────
# Step 1: Space experiment — Payload × Structure × Protocol
#         (tcpdump on lo0)
# ──────────────────────────────────────────────────────────────────────
run_space() {
  log "STEP 1 — Space experiment: Payload × Structure × Protocol (tcpdump on ${IFACE})"

  mkdir -p "${PROJECT_ROOT}/metrics/raw/pcaps"
  mkdir -p "${PROJECT_ROOT}/metrics/raw/space"

  # ---- REST space sweep (all structures) ----
  cleanup
  ./rest-server &
  REST_PID=$!
  wait_for_port 8080

  for struct in "${STRUCTURES[@]}"; do
    rest_csv="${PROJECT_ROOT}/metrics/raw/space/rest_${struct}.csv"
    echo "payload_size,structure,wire_bytes,header_bytes,body_bytes" > "$rest_csv"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "  space: REST / ${struct} / ${size}B"
      pcap_file="${PROJECT_ROOT}/metrics/raw/pcaps/rest_${struct}_${size}.pcap"

      local iters=100
      if [ "$size" -ge 65536 ]; then
        iters=10
      fi

      # Start tcpdump on loopback
      tcpdump -i "$IFACE" port 8080 -w "$pcap_file" -U 2>/dev/null &
      TCPDUMP_PID=$!
      sleep 0.5

      # Run k6 — single connection, N requests
      ${K6_BIN} run \
        -e "PROTOCOL=rest" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "STRUCTURE=${struct}" \
        -e "ITERATIONS=${iters}" \
        client/space/sweep.js 2>&1 | tail -5

      sleep 0.5
      kill "$TCPDUMP_PID" 2>/dev/null || true
      wait "$TCPDUMP_PID" 2>/dev/null || true
      sleep 0.5

      # Analyse pcap — client→server only (dst port 8080)
      # 1. Count actual valid requests and get average body size
      body_avg=$(tshark -r "$pcap_file" -Y "tcp.dstport == 8080 and http.content_length" \
        -T fields -e http.content_length 2>/dev/null \
        | tr ',' '\n' | awk 'NF { s += $1; c++ } END { if(c>0) printf "%.0f %d\n", s/c, c; else print "0 0" }')
      
      body_bytes=$(echo "$body_avg" | awk '{print $1}')
      req_count=$(echo "$body_avg" | awk '{print $2}')

      if [ "$req_count" -gt 0 ]; then
        wire_bytes=$(tshark -r "$pcap_file" -Y "tcp.dstport == 8080" \
          -T fields -e tcp.len 2>/dev/null \
          | awk -v c="$req_count" '{ s += $1 } END { printf "%.0f\n", s/c }')
        header_bytes=$((wire_bytes - body_bytes))
      else
        wire_bytes=0
        header_bytes=0
      fi

      echo "${size},${struct},${wire_bytes},${header_bytes},${body_bytes}" >> "$rest_csv"
      log "    wire=${wire_bytes} header=${header_bytes} body=${body_bytes}"
    done
    log "  ✓ REST / ${struct} complete → ${rest_csv}"
  done

  kill $REST_PID 2>/dev/null || true
  wait $REST_PID 2>/dev/null || true
  log "  ✓ REST space complete (all structures)"

  # ---- gRPC space sweep (all structures) ----
  ./grpc-server &
  GRPC_PID=$!
  wait_for_port 50051

  for struct in "${STRUCTURES[@]}"; do
    grpc_csv="${PROJECT_ROOT}/metrics/raw/space/grpc_${struct}.csv"
    echo "payload_size,structure,wire_bytes,header_bytes,body_bytes" > "$grpc_csv"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "  space: gRPC / ${struct} / ${size}B"
      pcap_file="${PROJECT_ROOT}/metrics/raw/pcaps/grpc_${struct}_${size}.pcap"

      local iters=100
      if [ "$size" -ge 65536 ]; then
        iters=10
      fi

      tcpdump -i "$IFACE" port 50051 -w "$pcap_file" -U 2>/dev/null &
      TCPDUMP_PID=$!
      sleep 0.5

      ${K6_BIN} run \
        -e "PROTOCOL=grpc" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "STRUCTURE=${struct}" \
        -e "ITERATIONS=${iters}" \
        client/space/sweep.js 2>&1 | tail -5

      sleep 0.5
      kill "$TCPDUMP_PID" 2>/dev/null || true
      wait "$TCPDUMP_PID" 2>/dev/null || true
      sleep 0.5

      # HTTP/2: client→server only (dst port 50051)
      # -d forces tshark to decode port 50051 as HTTP/2
      body_avg=$(tshark -r "$pcap_file" -d tcp.port==50051,http2 \
        -Y "tcp.dstport == 50051" \
        -T fields -e grpc.message_length 2>/dev/null \
        | tr ',' '\n' | awk 'NF { s += $1; c++ } END { if(c>0) printf "%.0f %d\n", s/c, c; else print "0 0" }')
        
      body_bytes=$(echo "$body_avg" | awk '{print $1}')
      req_count=$(echo "$body_avg" | awk '{print $2}')

      if [ "$req_count" -gt 0 ]; then
        wire_bytes=$(tshark -r "$pcap_file" -d tcp.port==50051,http2 \
          -Y "tcp.dstport == 50051" \
          -T fields -e tcp.len 2>/dev/null \
          | awk -v c="$req_count" '{ s += $1 } END { printf "%.0f\n", s/c }')
        header_bytes=$((wire_bytes - body_bytes))
      else
        wire_bytes=0
        header_bytes=0
      fi

      echo "${size},${struct},${wire_bytes},${header_bytes},${body_bytes}" >> "$grpc_csv"
      log "    wire=${wire_bytes} header=${header_bytes} body=${body_bytes}"
    done
    log "  ✓ gRPC / ${struct} complete → ${grpc_csv}"
  done

  kill $GRPC_PID 2>/dev/null || true
  wait $GRPC_PID 2>/dev/null || true
  log "  ✓ gRPC space complete (all structures)"
}

# ──────────────────────────────────────────────────────────────────────
# Step 2: Time experiment
# ──────────────────────────────────────────────────────────────────────
run_time() {
  log "STEP 2 — Time experiment (${ITERS} iterations per config)"

  # ---- REST time sweep ----
  cleanup
  ./rest-server &
  REST_PID=$!
  wait_for_port 8080

  for struct in "${STRUCTURES[@]}"; do
    csv_file="${PROJECT_ROOT}/metrics/raw/time/rest_${struct}.csv"
    echo "iteration,client_ns,server_ns,total_ns" > "$csv_file"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "  time: REST / ${struct} / ${size}B"
      ${K6_BIN} run \
        -e "PROTOCOL=rest" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "STRUCTURE=${struct}" \
        -e "ITERATIONS=${ITERS}" \
        "${PROJECT_ROOT}/client/time/sweep.js" \
        2>&1 | extract_csv >> "$csv_file"
    done
    log "  ✓ ${csv_file} ($(wc -l < "$csv_file") rows)"
  done

  kill $REST_PID 2>/dev/null || true
  wait $REST_PID 2>/dev/null || true
  log "  REST server stopped"

  # ---- gRPC time sweep ----
  ./grpc-server &
  GRPC_PID=$!
  wait_for_port 50051

  for struct in "${STRUCTURES[@]}"; do
    csv_file="${PROJECT_ROOT}/metrics/raw/time/grpc_${struct}.csv"
    echo "iteration,client_ns,server_ns,total_ns" > "$csv_file"

    for size in "${PAYLOAD_SIZES[@]}"; do
      log "  time: gRPC / ${struct} / ${size}B"
      ${K6_BIN} run \
        -e "PROTOCOL=grpc" \
        -e "SERVER_IP=${SERVER_IP}" \
        -e "PAYLOAD_SIZE=${size}" \
        -e "STRUCTURE=${struct}" \
        -e "ITERATIONS=${ITERS}" \
        "${PROJECT_ROOT}/client/time/sweep.js" \
        2>&1 | extract_csv >> "$csv_file"
    done
    log "  ✓ ${csv_file} ($(wc -l < "$csv_file") rows)"
  done

  kill $GRPC_PID 2>/dev/null || true
  wait $GRPC_PID 2>/dev/null || true
  log "  gRPC server stopped"
}

# ──────────────────────────────────────────────────────────────────────
# Step 3: Aggregate + Plot
# ──────────────────────────────────────────────────────────────────────
run_analysis() {
  log "STEP 3 — Aggregating raw data"
  python3 "${PROJECT_ROOT}/analysis/aggregate.py"

  log "STEP 4 — Generating plots"
  python3 "${PROJECT_ROOT}/analysis/plot_space.py"
  python3 "${PROJECT_ROOT}/analysis/plot_time.py"
  python3 "${PROJECT_ROOT}/analysis/plot_bars.py"
}

# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
case "$MODE" in
  space)
    run_space
    run_analysis
    ;;
  time)
    run_time
    run_analysis
    ;;
  all)
    run_space
    run_time
    run_analysis
    ;;
  *)
    echo "Usage: $0 {all|space|time}"
    exit 1
    ;;
esac

log "========================================="
log "LOCAL TEST COMPLETE"
log "========================================="
log ""
log "Raw data:       metrics/raw/{space,time}/*.csv"
log "Pcap captures:  metrics/raw/pcaps/*.pcap"
log "Aggregated:     metrics/aggregated/*.csv"
log "Plots:          results/*.png"
log ""
ls -lh "${PROJECT_ROOT}/results/"*.png 2>/dev/null || echo "(no plots found)"
