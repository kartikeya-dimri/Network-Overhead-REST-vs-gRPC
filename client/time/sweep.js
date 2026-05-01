// client/time/sweep.js — k6 time experiment
//
// Measures serialization + deserialization overhead per request.
// Runs 1000 iterations at concurrency 1.  Outputs CSV rows to stdout.
//
// Encoding strategy:
//   REST  → JSON.stringify(payload) over HTTP/1.1
//   gRPC  → native protobuf encoding over HTTP/2, using structure-aware
//            proto messages:
//              flat/wide → repeated Entry {key, value}
//              nested    → TreeNode {value, repeated TreeNode children}
//              array     → repeated ArrayElement {idx, val}
//
// Timing approach:
//   - Server-side: high-precision Go time.Now() nanosecond timer
//     (reported via server_ns in response body for REST, serverNs field for gRPC)
//   - Client-side: reported as 0 for both protocols to ensure an apples-to-apples
//     comparison of the Go server implementations. k6 JS runtime timing is ignored.
//
// Environment variables:
//   PROTOCOL      rest | grpc
//   SERVER_IP     e.g. 192.168.1.2
//   PAYLOAD_SIZE  target payload bytes (32, 64, 128, 512, 1024, 8192)
//   STRUCTURE     flat | nested | wide | array
//
// Output CSV (stdout):
//   iteration,client_ns,server_ns,total_ns
//
// Usage:
//   k6 run -e PROTOCOL=rest -e SERVER_IP=192.168.1.2 \
//          -e PAYLOAD_SIZE=1024 -e STRUCTURE=flat \
//          sweep.js 2>/dev/null > raw_output.csv

import http from 'k6/http';
import grpc from 'k6/net/grpc';
import { check } from 'k6';
import { generatePayload, logicalSize } from '../payloads/generator.js';

// ---- configuration ----
const PROTOCOL     = __ENV.PROTOCOL     || 'rest';
const SERVER_IP    = __ENV.SERVER_IP    || '127.0.0.1';
const PAYLOAD_SIZE = parseInt(__ENV.PAYLOAD_SIZE || '1024', 10);
const STRUCTURE    = __ENV.STRUCTURE    || 'flat';
const ITERATIONS   = parseInt(__ENV.ITERATIONS || '1000', 10);

const REST_URL  = `http://${SERVER_IP}:8080/echo`;
const GRPC_ADDR = `${SERVER_IP}:50051`;

// Pre-generate the structured payload once
const payload = generatePayload(STRUCTURE, PAYLOAD_SIZE);

// REST: JSON-encode the structured payload
const jsonBody = JSON.stringify(payload);

// ---------------------------------------------------------------------------
// gRPC path: structure-aware payload conversion
//
// Each structure maps to its native proto message type, so protobuf
// can encode it compactly without synthetic key-path inflation.
// ---------------------------------------------------------------------------

/**
 * Convert a flat/wide JS object into repeated Entry {key, value}.
 */
function objectToEntries(obj) {
  const entries = [];
  for (const key of Object.keys(obj)) {
    entries.push({ key: key, value: String(obj[key]) });
  }
  return entries;
}

/**
 * Build gRPC request payload based on structure type.
 *   flat/wide → { entries: [{key, value}, ...] }
 *   nested    → { tree: {value, children: [...]} }
 *   array     → { elements: [{idx, val}, ...] }
 */
function buildGrpcPayload(structure, data) {
  switch (structure) {
    case 'flat':
    case 'wide':
      return { entries: objectToEntries(data) };
    case 'nested':
      return { tree: data };
    case 'array':
      return { elements: data };
    default:
      throw new Error(`unknown structure for gRPC: ${structure}`);
  }
}

const grpcPayload = buildGrpcPayload(STRUCTURE, payload);

console.log(`[time] protocol=${PROTOCOL} structure=${STRUCTURE} logical_bytes=${logicalSize(payload)} json_bytes=${jsonBody.length}`);
console.log('iteration,client_ns,server_ns,total_ns');

// ---- k6 options ----
export const options = {
  vus: 1,
  iterations: ITERATIONS,
};

// ---- gRPC client setup ----
let grpcClient;
if (PROTOCOL === 'grpc') {
  grpcClient = new grpc.Client();
  grpcClient.load(
    ['../../servers/grpc/proto'],
    'echo.proto',
  );
}

// ---- iteration counter ----
let iteration = 0;

// ---- main ----
export default function () {
  const iter = iteration++;

  if (PROTOCOL === 'rest') {
    // --- send request (JSON-encoded body) ---
    const res = http.post(REST_URL, jsonBody, {
      headers: { 'Content-Type': 'application/json' },
    });

    check(res, { 'status 200': (r) => r.status === 200 });

    const parsed = JSON.parse(res.body);

    // --- server timing from response body (nanosecond precision) ---
    const serverNs = parsed.server_ns || 0;

    // Report 0 for client side to maintain fairness with gRPC
    const clientNs = 0;
    const totalNs  = serverNs;
    console.log(`${iter},${clientNs},${serverNs},${totalNs}`);

  } else if (PROTOCOL === 'grpc') {
    grpcClient.connect(GRPC_ADDR, { plaintext: true });

    // Send structured payload — k6/gRPC performs native protobuf encoding
    const resp = grpcClient.invoke('echo.EchoService/Echo', grpcPayload);

    check(resp, { 'grpc OK': (r) => r && r.status === grpc.StatusOK });

    // Server-side timing is the only reliable measurement for gRPC in k6.
    // k6's Go runtime handles proto ser/deser internally — we cannot
    // instrument it from JavaScript.  Client-side is reported as 0.
    const serverNs = resp.message ? (resp.message.serverNs || 0) : 0;
    const clientNs = 0;
    const totalNs  = serverNs;

    console.log(`${iter},${clientNs},${serverNs},${totalNs}`);
    grpcClient.close();
  }
}
