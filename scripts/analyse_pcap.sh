#!/bin/bash
# analyse_pcap.sh — extract wire bytes, header bytes, and body bytes from pcap files
#
# Processes all pcap files in metrics/raw/pcaps/ and appends results to
# metrics/raw/space/{rest,grpc}.csv
#
# Output CSV columns: payload_size,wire_bytes,header_bytes,body_bytes
#
# Usage:
#   ./analyse_pcap.sh                  # process all pcaps
#   ./analyse_pcap.sh <pcap_file>      # process a single pcap

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PCAP_DIR="${PROJECT_ROOT}/metrics/raw/pcaps"
SPACE_DIR="${PROJECT_ROOT}/metrics/raw/space"

mkdir -p "$SPACE_DIR"

analyse_one() {
  local pcap_file="$1"
  local basename
  basename="$(basename "$pcap_file" .pcap)"

  # Parse protocol and payload size from filename: <protocol>_<payload_size>.pcap
  local protocol payload_size
  protocol="$(echo "$basename" | cut -d'_' -f1)"
  payload_size="$(echo "$basename" | cut -d'_' -f2)"

  # Use the same iteration count as the orchestrator (100)
  local iters=100

  local csv_file="${SPACE_DIR}/${protocol}.csv"

  # --- O1: total wire bytes (sum of TCP payload lengths) ---
  local wire_bytes
  wire_bytes=$(tshark -n -r "$pcap_file" -T fields -e tcp.len \
    | awk -v i="$iters" '{ s += $1 } END { printf "%.0f\n", s/i }')

  # --- O2: header vs body bytes ---
  local header_bytes=0
  local body_bytes=0

  if [ "$protocol" = "grpc" ]; then
    # For gRPC: body = grpc.message_length, header = wire - body
    body_bytes=$(tshark -n -r "$pcap_file" -d tcp.port==50051,http2 \
      -T fields -e grpc.message_length \
      | tr ',' '\n' | awk -v i="$iters" '{ s += $1 } END { printf "%.0f\n", s/i }')
    header_bytes=$((wire_bytes - body_bytes))
  else
    # HTTP/1.1: use content-length for body, derive header from difference
    body_bytes=$(tshark -n -r "$pcap_file" -Y "http.content_length" \
      -T fields -e http.content_length \
      | tr ',' '\n' | awk -v i="$iters" '{ s += $1 } END { printf "%.0f\n", s/i }')

    # header_bytes = wire_bytes - body_bytes (includes TCP overhead,
    # but for HTTP/1.1 on a single request this is a reasonable approximation)
    header_bytes=$((wire_bytes - body_bytes))
  fi

  # Append to CSV (create header if file is empty)
  if [ ! -s "$csv_file" ]; then
    echo "payload_size,wire_bytes,header_bytes,body_bytes" > "$csv_file"
  fi
  echo "${payload_size},${wire_bytes},${header_bytes},${body_bytes}" >> "$csv_file"
  echo "[analyse] ${protocol} ${payload_size}B → wire=${wire_bytes} header=${header_bytes} body=${body_bytes}"
}

# ---- main ----
if [ $# -ge 1 ]; then
  analyse_one "$1"
else
  # Clear existing CSVs
  > "${SPACE_DIR}/rest.csv"
  > "${SPACE_DIR}/grpc.csv"

  for pcap in "$PCAP_DIR"/*.pcap; do
    [ -f "$pcap" ] || continue
    analyse_one "$pcap"
  done
  echo "[analyse] done — results in ${SPACE_DIR}/"
fi
