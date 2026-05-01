# Fix: Native Encoding per Protocol

## Problem

When payloads were pre-serialized as JSON strings, both REST and gRPC transported **identical data** — the same JSON blob. gRPC wrapped it in an opaque `bytes payload` protobuf field, so protobuf's native encoding was never exercised. The only observable difference was HTTP/2 vs HTTP/1.1 header overhead.

## Solution

Changed the data flow so each protocol uses its **native serialization format** on the same structured data:

```
Generator → Structured JS Object (flat key-value map)
     │
     ├── REST  → JSON.stringify(object)           → HTTP/1.1 POST body
     │
     └── gRPC  → repeated Entry {key, value}       → native protobuf encoding
```

## Files Changed

### 1. [echo.proto](file:///Users/kartikeya-dimri/Desktop/Projects/REST%20vs%20gRPC/Network-Overhead/servers/grpc/proto/echo.proto)

```diff
-message EchoRequest {
-  bytes payload = 1;
-}
-message EchoResponse {
-  bytes payload   = 1;
-  int64 server_ns = 2;
-}
+message Entry {
+  string key = 1;
+  string value = 2;
+}
+message EchoRequest {
+  repeated Entry entries = 1;
+}
+message EchoResponse {
+  repeated Entry entries = 1;
+  int64 server_ns = 2;
+}
```

Protobuf now has **typed, structured fields** to encode — not just an opaque byte blob.

### 2. [echo.pb.go](file:///Users/kartikeya-dimri/Desktop/Projects/REST%20vs%20gRPC/Network-Overhead/servers/grpc/proto/echo.pb.go) + [echo_grpc.pb.go](file:///Users/kartikeya-dimri/Desktop/Projects/REST%20vs%20gRPC/Network-Overhead/servers/grpc/proto/echo_grpc.pb.go)

Regenerated via `protoc`. New `Entry`, `EchoRequest.Entries`, `EchoResponse.Entries` types.

### 3. [handler.go](file:///Users/kartikeya-dimri/Desktop/Projects/REST%20vs%20gRPC/Network-Overhead/servers/grpc/handler.go) (gRPC server)

```diff
-  resp := &pb.EchoResponse{Payload: req.Payload}
+  resp := &pb.EchoResponse{Entries: req.Entries}
```

### 4. [sweep.js (space)](file:///Users/kartikeya-dimri/Desktop/Projects/REST%20vs%20gRPC/Network-Overhead/client/space/sweep.js)

- **REST path**: `JSON.stringify(payload)` → sends structured JSON body *(unchanged)*
- **gRPC path**: Converts `{key_0:"...", key_1:"..."}` → `{entries: [{key:"key_0", value:"..."}, ...]}` for native protobuf encoding
- Removed `encoding` import and base64 workaround

### 5. [sweep.js (time)](file:///Users/kartikeya-dimri/Desktop/Projects/REST%20vs%20gRPC/Network-Overhead/client/time/sweep.js)

- Same fix as space sweep
- Added `flattenToEntries()` recursive flattener to handle all 4 structure types (flat, nested, wide, array)
- Removed `encoding` import and base64 workaround

## What This Enables

| Metric | Before (broken) | After (fixed) |
|--------|-----------------|---------------|
| **Body bytes** | Identical (both carry JSON) | Different (JSON vs protobuf binary) |
| **Header bytes** | Different (HTTP/1.1 vs HTTP/2) | Different (HTTP/1.1 vs HTTP/2) |
| **Encoding observable** | ❌ No | ✅ Yes |
| **Protobuf advantage visible** | Only headers | Headers + body encoding |

## Rebuild & Test

```bash
# Rebuild servers (protobuf code already regenerated)
go build -o rest-server ./servers/rest/
go build -o grpc-server ./servers/grpc/

# Run the full experiment
./scripts/local_test.sh space
```
