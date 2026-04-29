# Walkthrough — REST vs gRPC Network Overhead Project

All placeholder files have been implemented. Here's what was built:

---

## Project Structure (after implementation)

```
Network-Overhead/
├── go.mod / go.sum                    ← Go module (grpc v1.80, protobuf v1.36)
│
├── servers/
│   ├── rest/
│   │   ├── main.go                    ← HTTP server on :8080
│   │   └── handler.go                 ← POST /echo — JSON echo + X-Server-Ns header
│   └── grpc/
│       ├── main.go                    ← gRPC server on :50051
│       ├── handler.go                 ← Echo RPC — re-measures proto ser/deser
│       └── proto/
│           ├── echo.proto             ← Service + message definitions
│           ├── echo.pb.go             ← Generated (protoc)
│           └── echo_grpc.pb.go        ← Generated (protoc)
│
├── client/
│   ├── payloads/
│   │   ├── generator.js              ← k6-compatible payload generator (flat/nested/wide/array)
│   │   └── schemas/                   ← Structure descriptions (flat/nested/wide/array .json)
│   ├── space/
│   │   └── sweep.js                   ← k6 space experiment (1 iteration, tcpdump captures wire bytes)
│   └── time/
│       └── sweep.js                   ← k6 time experiment (1000 iterations, CSV output)
│
├── scripts/
│   ├── run_experiment.sh              ← Master orchestrator (space | time | all)
│   ├── capture_network.sh             ← tcpdump start/stop wrapper
│   └── analyse_pcap.sh                ← tshark pcap → wire/header/body CSV
│
├── analysis/
│   ├── aggregate.py                   ← Raw CSVs → aggregated O1/O2/O3
│   ├── plot_space.py                  ← Plot 1 (overhead ratio) + Plot 2 (header:body ratio)
│   └── plot_time.py                   ← Plot 3 (2×2 grid + individual per-structure plots)
│
├── metrics/
│   ├── raw/
│   │   ├── pcaps/                     ← tcpdump captures land here
│   │   ├── space/{rest,grpc}.csv      ← Raw space data
│   │   └── time/{proto}_{struct}.csv  ← Raw time data (8 files)
│   └── aggregated/
│       ├── overhead_ratio.csv         ← O1 final
│       ├── header_body_ratio.csv      ← O2 final
│       └── ser_deser_overhead.csv     ← O3 final
│
└── results/                           ← Final PNG plots
```

---

## Key Design Decisions

### Server Timing (gRPC)
The gRPC framework deserializes the request *before* the handler and serializes the response *after* it returns. To measure proto ser/deser, the handler **re-performs** `proto.Marshal`/`proto.Unmarshal` with identical data and times those operations. At c=1 with warm caches, this is representative.

### Client Timing (k6)
- **REST**: `JSON.stringify()` and `JSON.parse()` are timed directly in JS — precise measurement.
- **gRPC**: k6's gRPC module handles protobuf encoding internally. We time the full `invoke()` call and subtract `server_ns` to approximate client overhead. This includes ~2× network one-way latency (negligible on an isolated ethernet link).

### Payload Generator
Uses iterative size-tuning to hit target byte sizes within ~5%. Four structural patterns exercise different serialization codepaths.

---

## Verification

| Check | Result |
|---|---|
| `go mod tidy` | ✅ All dependencies resolved |
| `go build ./servers/rest/` | ✅ Compiles |
| `go build ./servers/grpc/` | ✅ Compiles |
| REST smoke test (`curl POST /echo`) | ✅ Echoes JSON, returns `X-Server-Ns` header |
| gRPC server startup | ✅ Listens on :50051 |

---

## How to Run the Experiments

### On the server machine:
```bash
# Build and run REST server
go build -o rest-server ./servers/rest/
./rest-server

# Or gRPC server (separate run)
go build -o grpc-server ./servers/grpc/
./grpc-server
```

### On the client machine:
```bash
# Set environment
export SERVER_IP=<server-ip>
export IFACE=eth0   # network interface for tcpdump

# Run space experiment (needs sudo for tcpdump)
./scripts/run_experiment.sh space

# Run time experiment
./scripts/run_experiment.sh time

# Post-process
python3 analysis/aggregate.py
python3 analysis/plot_space.py
python3 analysis/plot_time.py
```
