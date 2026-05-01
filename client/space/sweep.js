// client/space/sweep.js — k6 space experiment
//
// Sends structured payloads to measure wire-level overhead differences.
//
// Input space:  Payload Size × Structure × Protocol
//
// REST  → JSON.stringify(payload) over HTTP/1.1
// gRPC  → native protobuf encoding over HTTP/2, using structure-aware
//          proto messages:
//            flat/wide → repeated Entry {key, value}
//            nested    → TreeNode {value, repeated TreeNode children}
//            array     → repeated ArrayElement {idx, val}
//
// The generator produces structured JS objects at a target logical byte size.
// Logical payload bytes are held constant across structures so that encoding
// cost differences are isolated and observable.
//
// Wire bytes are captured externally via tcpdump — this script just
// drives the traffic and logs the logical (pre-serialization) payload size.
//
// Environment variables:
//   PROTOCOL      rest | grpc
//   SERVER_IP     e.g. 192.168.1.2
//   PAYLOAD_SIZE  target logical payload bytes (32, 64, 128, 512, 1024, 8192)
//   STRUCTURE     flat | nested | wide | array
//
// Usage:
//   k6 run -e PROTOCOL=rest -e STRUCTURE=wide -e PAYLOAD_SIZE=1024 sweep.js

import http from 'k6/http';
import grpc from 'k6/net/grpc';
import { check } from 'k6';
import { generatePayload, logicalSize } from '../payloads/generator.js';

// ---- configuration ----
const PROTOCOL     = __ENV.PROTOCOL     || 'rest';
const SERVER_IP    = __ENV.SERVER_IP    || '127.0.0.1';
const PAYLOAD_SIZE = parseInt(__ENV.PAYLOAD_SIZE || '1024', 10);
const STRUCTURE    = __ENV.STRUCTURE    || 'flat';
const ITERATIONS   = parseInt(__ENV.ITERATIONS || '100', 10);

const REST_URL  = `http://${SERVER_IP}:8080/echo`;
const GRPC_ADDR = `${SERVER_IP}:50051`;

// Pre-generate the structured payload once
const payload = generatePayload(STRUCTURE, PAYLOAD_SIZE);

// REST path: JSON-encode the structured payload
const jsonBody = JSON.stringify(payload);

// ---------------------------------------------------------------------------
// gRPC path: structure-aware payload conversion
//
// Each structure maps to its native proto message type, so protobuf
// can encode it compactly without synthetic key-path inflation.
// ---------------------------------------------------------------------------

/**
 * Convert a flat/wide JS object into repeated Entry {key, value}.
 * Only used for flat and wide structures.
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
 * Uses the native proto message for each structure:
 *   flat/wide → { entries: [{key, value}, ...] }
 *   nested    → { tree: {value, children: [{value, children: [...]}, ...]} }
 *   array     → { elements: [{idx, val}, ...] }
 */
function buildGrpcPayload(structure, data) {
  switch (structure) {
    case 'flat':
    case 'wide':
      return { entries: objectToEntries(data) };
    case 'nested':
      // The generator produces { value: "...", children: [...] } which maps
      // directly to the TreeNode proto message — no conversion needed!
      return { tree: data };
    case 'array':
      // The generator produces [ {idx, val}, ... ] which maps directly
      // to repeated ArrayElement — no conversion needed!
      return { elements: data };
    default:
      throw new Error(`unknown structure for gRPC: ${structure}`);
  }
}

const grpcPayload = buildGrpcPayload(STRUCTURE, payload);

console.log(`[space] protocol=${PROTOCOL} structure=${STRUCTURE} logical_bytes=${logicalSize(payload)} json_bytes=${jsonBody.length}`);

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
    for (let i = 0; i < ITERATIONS; i++) {
      const res = http.post(REST_URL, jsonBody, {
        headers: { 'Content-Type': 'application/json' },
      });
      check(res, {
        'status 200': (r) => r.status === 200,
      });
    }
  } else if (PROTOCOL === 'grpc') {
    grpcClient.connect(GRPC_ADDR, { plaintext: true });

    for (let i = 0; i < ITERATIONS; i++) {
      const resp = grpcClient.invoke('echo.EchoService/Echo', grpcPayload);
      check(resp, {
        'grpc status OK': (r) => r && r.status === grpc.StatusOK,
      });
    }
    grpcClient.close();
  }
}
