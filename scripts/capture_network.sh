#!/bin/bash
# capture_network.sh — start/stop tcpdump for a single space experiment run
#
# Usage:
#   ./capture_network.sh start <protocol> <payload_size> <interface> <server_ip>
#   ./capture_network.sh stop
#
# Writes pcap to: metrics/raw/pcaps/<protocol>_<payload_size>.pcap

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PCAP_DIR="${PROJECT_ROOT}/metrics/raw/pcaps"
PID_FILE="/tmp/tcpdump_experiment.pid"

mkdir -p "$PCAP_DIR"

case "${1:-}" in
  start)
    PROTOCOL="${2:?usage: capture_network.sh start <protocol> <payload_size> <iface> <server_ip>}"
    PAYLOAD_SIZE="${3:?}"
    IFACE="${4:?}"
    SERVER_IP="${5:?}"
    OUTFILE="${PCAP_DIR}/${PROTOCOL}_${PAYLOAD_SIZE}.pcap"

    echo "[capture] starting tcpdump on ${IFACE} for traffic TO ${SERVER_IP} (ports 8080,50051) → ${OUTFILE}"
    sudo tcpdump -i "$IFACE" dst host "$SERVER_IP" and \( port 8080 or port 50051 \) -w "$OUTFILE" -U &
    echo $! > "$PID_FILE"
    # Give tcpdump a moment to initialise
    sleep 1
    echo "[capture] tcpdump running (pid=$(cat "$PID_FILE"))"
    ;;

  stop)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      echo "[capture] stopping tcpdump (pid=${PID})"
      # Use SIGINT (2) to allow tcpdump to flush buffers and exit cleanly
      sudo kill -2 "$PID" 2>/dev/null || true
      # Wait for the process to finish writing
      sleep 2
      sync
      rm -f "$PID_FILE"
      
      # Ensure the pcap file is readable by the current user (it might be owned by root)
      # We find the file that was just created. We need the protocol and size from start.
      # For simplicity, we can just chown everything in the pcap dir or just the relevant one.
      # Actually, capture_network stop doesn't know the filename easily unless we store it.
      sudo chown "$(id -u):$(id -g)" "${PCAP_DIR}"/*.pcap || true
    else
      echo "[capture] no running capture found"
    fi
    ;;

  *)
    echo "Usage: $0 {start|stop} [args...]"
    exit 1
    ;;
esac
