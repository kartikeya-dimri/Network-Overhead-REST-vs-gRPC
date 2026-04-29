// client/space/sweep.js — k6 space experiment
//
// Sends a single request with a flat payload at the specified size.
// Wire bytes are captured externally via tcpdump — this script just
// drives the traffic and logs the logical (pre-serialization) payload size.
//
// Environment variables:
//   PROTOCOL      rest | grpc
//   SERVER_IP     e.g. 192.168.1.2
//   PAYLOAD_SIZE  target payload bytes (128, 512, 1024, 8192, 65536, 524288)
//
// Usage:
//   k6 run -e PROTOCOL=rest -e SERVER_IP=192.168.1.2 -e PAYLOAD_SIZE=1024 sweep.js

import http from 'k6/http';
import grpc from 'k6/net/grpc';
import { check } from 'k6';
import encoding from 'k6/encoding';
import { generatePayload } from '../payloads/generator.js';

// ---- configuration ----
const PROTOCOL     = __ENV.PROTOCOL     || 'rest';
const SERVER_IP    = __ENV.SERVER_IP    || '127.0.0.1';
const PAYLOAD_SIZE = parseInt(__ENV.PAYLOAD_SIZE || '1024', 10);

const REST_URL  = `http://${SERVER_IP}:8080/echo`;
const GRPC_ADDR = `${SERVER_IP}:50051`;

// Pre-generate the payload once (space experiment uses flat only)
const payload = generatePayload('flat', PAYLOAD_SIZE);
const jsonBody = JSON.stringify(payload);

console.log(`[space] protocol=${PROTOCOL} payload_size=${PAYLOAD_SIZE} logical_bytes=${jsonBody.length}`);

// ---- k6 options: single iteration, single VU ----
export const options = {
  vus: 1,
  iterations: 1,
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

// ---- main ----
export default function () {
  if (PROTOCOL === 'rest') {
    const res = http.post(REST_URL, jsonBody, {
      headers: { 'Content-Type': 'application/json' },
    });
    check(res, {
      'status 200': (r) => r.status === 200,
    });
  } else if (PROTOCOL === 'grpc') {
    grpcClient.connect(GRPC_ADDR, { plaintext: true });

    // k6 gRPC requires bytes fields as base64-encoded strings
    const payloadB64 = encoding.b64encode(jsonBody);

    const resp = grpcClient.invoke('echo.EchoService/Echo', {
      payload: payloadB64,
    });
    check(resp, {
      'grpc status OK': (r) => r && r.status === grpc.StatusOK,
    });
    grpcClient.close();
  }
}
