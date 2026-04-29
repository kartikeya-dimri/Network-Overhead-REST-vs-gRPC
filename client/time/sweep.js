// client/time/sweep.js — k6 time experiment
//
// Measures serialization + deserialization overhead per request.
// Runs 1000 iterations at concurrency 1.  Outputs CSV rows to stdout.
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
//   PAYLOAD_SIZE  target payload bytes (32, 64, 128, 512, 1024, 8192, 65536, 524288)
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
import encoding from 'k6/encoding';
import { generatePayload } from '../payloads/generator.js';

// ---- configuration ----
const PROTOCOL     = __ENV.PROTOCOL     || 'rest';
const SERVER_IP    = __ENV.SERVER_IP    || '127.0.0.1';
const PAYLOAD_SIZE = parseInt(__ENV.PAYLOAD_SIZE || '1024', 10);
const STRUCTURE    = __ENV.STRUCTURE    || 'flat';
const ITERATIONS   = parseInt(__ENV.ITERATIONS || '1000', 10);

const REST_URL  = `http://${SERVER_IP}:8080/echo`;
const GRPC_ADDR = `${SERVER_IP}:50051`;

// Pre-generate the payload once
const payload = generatePayload(STRUCTURE, PAYLOAD_SIZE);

console.log(`[time] protocol=${PROTOCOL} structure=${STRUCTURE} payload_size=${PAYLOAD_SIZE}`);
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
    const body = JSON.stringify(payload);

    // --- send request ---
    const res = http.post(REST_URL, body, {
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

    // k6 gRPC requires bytes fields as base64-encoded strings
    const jsonStr = JSON.stringify(payload);
    const payloadB64 = encoding.b64encode(jsonStr);

    const resp = grpcClient.invoke('echo.EchoService/Echo', {
      payload: payloadB64,
    });

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
