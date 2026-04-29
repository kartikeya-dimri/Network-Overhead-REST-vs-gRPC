#!/bin/bash
# diagnose_pcaps.sh — deep-dive into pcap files to understand measurement issues
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PCAP_DIR="${PROJECT_ROOT}/metrics/raw/pcaps"

echo "=============================="
echo "PCAP FILE SIZES"
echo "=============================="
ls -lh "$PCAP_DIR"/*.pcap

echo ""
echo "=============================="
echo "REST 128B — per-packet breakdown"
echo "=============================="
tshark -r "$PCAP_DIR/rest_128.pcap" \
  -T fields -e frame.number -e tcp.srcport -e tcp.dstport -e tcp.len \
  -e http.request.method -e http.response.code -e http.content_length 2>/dev/null

echo ""
echo "=============================="
echo "REST 128B — total wire bytes and body breakdown"
echo "=============================="
echo -n "total tcp.len (both dirs): "
tshark -r "$PCAP_DIR/rest_128.pcap" -T fields -e tcp.len 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "request body (client→server, dstport=8080): "
tshark -r "$PCAP_DIR/rest_128.pcap" -Y "tcp.dstport==8080" -T fields -e tcp.len 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "response body (server→client, srcport=8080): "
tshark -r "$PCAP_DIR/rest_128.pcap" -Y "tcp.srcport==8080" -T fields -e tcp.len 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "http.content_length values: "
tshark -r "$PCAP_DIR/rest_128.pcap" -Y "http.content_length" \
  -T fields -e http.content_length 2>/dev/null | tr '\n' ' '
echo ""

echo ""
echo "=============================="
echo "gRPC 128B — per-packet breakdown"
echo "=============================="
tshark -r "$PCAP_DIR/grpc_128.pcap" -d tcp.port==50051,http2 \
  -T fields -e frame.number -e tcp.srcport -e tcp.dstport -e tcp.len \
  -e http2.type -e http2.length 2>/dev/null

echo ""
echo "=============================="
echo "gRPC 128B — HTTP/2 frame analysis"
echo "=============================="
echo -n "total tcp.len (both dirs): "
tshark -r "$PCAP_DIR/grpc_128.pcap" -d tcp.port==50051,http2 \
  -T fields -e tcp.len 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "HEADERS frames (type=1) total length: "
tshark -r "$PCAP_DIR/grpc_128.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==1" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "DATA frames (type=0) total length: "
tshark -r "$PCAP_DIR/grpc_128.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==0" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "SETTINGS frames (type=4) total length: "
tshark -r "$PCAP_DIR/grpc_128.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==4" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo -n "WINDOW_UPDATE frames (type=8): "
tshark -r "$PCAP_DIR/grpc_128.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==8" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo ""
echo "=============================="
echo "gRPC 512B — HTTP/2 frame analysis"
echo "=============================="
echo -n "total tcp.len: "
tshark -r "$PCAP_DIR/grpc_512.pcap" -d tcp.port==50051,http2 \
  -T fields -e tcp.len 2>/dev/null | awk '{s+=$1}END{print s+0}'
echo -n "HEADERS (type=1): "
tshark -r "$PCAP_DIR/grpc_512.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==1" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'
echo -n "DATA (type=0): "
tshark -r "$PCAP_DIR/grpc_512.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==0" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo ""
echo "=============================="
echo "gRPC 65536B — HTTP/2 frame analysis"
echo "=============================="
echo -n "total tcp.len: "
tshark -r "$PCAP_DIR/grpc_65536.pcap" -d tcp.port==50051,http2 \
  -T fields -e tcp.len 2>/dev/null | awk '{s+=$1}END{print s+0}'
echo -n "HEADERS (type=1): "
tshark -r "$PCAP_DIR/grpc_65536.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==1" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'
echo -n "DATA (type=0): "
tshark -r "$PCAP_DIR/grpc_65536.pcap" -d tcp.port==50051,http2 \
  -Y "http2.type==0" -T fields -e http2.length 2>/dev/null | awk '{s+=$1}END{print s+0}'

echo ""
echo "=============================="
echo "LOGICAL PAYLOAD SIZES (what generator.js produces)"
echo "=============================="
# Quick check: what does the generator actually produce for each target size?
node -e '
const sizes = [128, 512, 1024, 8192, 65536, 524288];
// Replicate the flat generator logic
for (const target of sizes) {
  const numKeys = 4;
  const overhead = 2 + numKeys * 12;
  const valueLen = Math.max(1, Math.floor((target - overhead) / numKeys));
  const obj = {};
  for (let i = 0; i < numKeys; i++) {
    obj["key_" + i] = "x".repeat(valueLen);
  }
  // Tune
  let current = JSON.stringify(obj).length;
  if (current < target) {
    obj["key_3"] += "x".repeat(target - current);
  } else if (current > target) {
    obj["key_3"] = obj["key_3"].substring(0, Math.max(1, obj["key_3"].length - (current - target)));
  }
  const json = JSON.stringify(obj);
  console.log("target=" + target + " actual_json_bytes=" + json.length);
}
'

echo ""
echo "---DIAGNOSIS-DONE---"
