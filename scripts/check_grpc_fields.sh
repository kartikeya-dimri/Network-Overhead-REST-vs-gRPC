#!/bin/bash
# check_grpc_fields.sh — test tshark gRPC dissection fields
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PCAP="$PROJECT_ROOT/metrics/raw/pcaps/grpc_128.pcap"

echo "=== Check grpc.message_length field ==="
tshark -r "$PCAP" -d tcp.port==50051,http2 \
  -T fields -e frame.number -e tcp.srcport -e tcp.dstport \
  -e http2.type -e http2.length -e grpc.message_length 2>&1

echo ""
echo "=== All HTTP/2 frame lengths summed by type ==="
for ftype in 0 1 2 3 4 5 6 7 8 9; do
  total=$(tshark -r "$PCAP" -d tcp.port==50051,http2 \
    -Y "http2.type==$ftype" -T fields -e http2.length 2>/dev/null \
    | awk '{s+=$1}END{print s+0}')
  if [ "$total" -gt 0 ]; then
    echo "  type=$ftype total=$total"
  fi
done

echo ""
echo "=== Per-direction DATA frame bytes ==="
echo -n "client→server DATA: "
tshark -r "$PCAP" -d tcp.port==50051,http2 \
  -Y "tcp.dstport==50051 and http2.type==0" \
  -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "server→client DATA: "
tshark -r "$PCAP" -d tcp.port==50051,http2 \
  -Y "tcp.srcport==50051 and http2.type==0" \
  -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo ""
echo "=== LARGER PAYLOAD: gRPC 8192B ==="
PCAP8K="$PROJECT_ROOT/metrics/raw/pcaps/grpc_8192.pcap"
echo -n "total tcp.len: "
tshark -r "$PCAP8K" -d tcp.port==50051,http2 \
  -T fields -e tcp.len 2>/dev/null | awk '{s+=$1}END{print s+0}'
echo -n "DATA (type=0): "
tshark -r "$PCAP8K" -d tcp.port==50051,http2 \
  -Y "http2.type==0" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'
echo -n "HEADERS (type=1): "
tshark -r "$PCAP8K" -d tcp.port==50051,http2 \
  -Y "http2.type==1" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo ""
echo "---CHECK-DONE---"
