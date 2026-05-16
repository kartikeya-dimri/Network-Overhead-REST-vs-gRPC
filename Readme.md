# Measuring Network Overhead in Space and Time — REST vs gRPC

[**📄 Read the Full Paper (PDF)**](docs/Paper.pdf)

![Lab Setup](assets/lab_setup.jpeg)

## Table of Contents

- [1. Aim](#1-aim)
- [2. Folder Structure](#2-folder-structure)
- [3. Input Space](#3-input-space)
  - [3.1 Space Experiments](#31-space-experiments-encoding--framing-overhead)
  - [3.2 Time Experiments](#32-time-experiments-serialization-overhead)
- [4. Two-Machine Setup](#4-two-machine-setup)
  - [4.1 Network Topology](#41-network-topology)
  - [4.2 Machine Specifications](#42-machine-specifications)
  - [4.3 Software Versions](#43-software-versions)
- [5. Architecture](#5-architecture)
  - [5.1 Client — k6 Sweep & Metric Collection](#51-client--k6-sweep--metric-collection)
  - [5.2 Server — Minimal Echo Servers](#52-server--minimal-echo-servers)
  - [5.3 Native Encoding per Protocol](#53-native-encoding-per-protocol)
- [6. Running the Experiments](#6-running-the-experiments)
  - [6.1 Prerequisites](#61-prerequisites)
  - [6.2 Two-Machine Lab Run](#62-two-machine-lab-run)
  - [6.3 Local Test (Single Machine / macOS)](#63-local-test-single-machine--macos)
  - [6.4 Analysis Only](#64-analysis-only)
  - [6.5 Output Locations](#65-output-locations)

---

## 1. Aim

This project studies the **network overheads** introduced by REST (HTTP/1.1 + JSON) and gRPC (HTTP/2 + Protobuf) across two dimensions:

| Dimension | What it captures | Overhead type |
|-----------|-----------------|---------------|
| **Space** | How many extra bytes each protocol puts on the wire beyond the logical application data | **Encoding overhead** (JSON vs Protobuf binary) and **Framing (Header) overhead** (HTTP/1.1 headers vs HTTP/2 HPACK-compressed frames) |
| **Time** | How long each protocol spends converting structured data to/from its wire format | **Serialization / Deserialization overhead** (`JSON.stringify`/`JSON.parse` vs `proto.Marshal`/`proto.Unmarshal`) |

Both protocols transport the **same logical data** — a structured key-value object — but each uses its own native serialization: REST sends JSON over HTTP/1.1, and gRPC sends Protobuf-encoded binary over HTTP/2. This ensures we observe real encoding differences rather than an opaque byte blob.

---

## 2. Folder Structure

```
Network-Overhead/
│
├── go.mod / go.sum                       # Go module (grpc v1.80, protobuf v1.36)
│
├── servers/
│   ├── rest/
│   │   ├── main.go                       # HTTP server on :8080
│   │   └── handler.go                    # POST /echo — JSON echo + X-Server-Ns header
│   └── grpc/
│       ├── main.go                       # gRPC server on :50051
│       ├── handler.go                    # Echo RPC — proto echo + server timing
│       └── proto/
│           ├── echo.proto                # Service + message definitions (repeated Entry)
│           ├── echo.pb.go                # Generated (protoc)
│           └── echo_grpc.pb.go           # Generated (protoc)
│
├── client/
│   ├── payloads/
│   │   ├── generator.js                  # k6-compatible payload generator (flat/nested/wide/array)
│   │   └── schemas/                      # Structure descriptions (flat/nested/wide/array .json)
│   ├── space/
│   │   └── sweep.js                      # k6 space experiment (1 iter, tcpdump captures wire bytes)
│   └── time/
│       └── sweep.js                      # k6 time experiment (1000 iters, CSV output)
│
├── scripts/
│   ├── run_experiment.sh                 # Master orchestrator (space | time | analysis | all)
│   ├── local_test.sh                     # Local testing variant (single-machine)
│   ├── capture_network.sh               # tcpdump start/stop wrapper
│   └── analyse_pcap.sh                  # tshark pcap → wire/header/body CSV
│
├── analysis/
│   ├── aggregate.py                      # Raw CSVs → aggregated metrics
│   ├── plot_space.py                     # Encoding overhead + framing overhead plots
│   ├── plot_time.py                      # Ser/deser 2×2 grid + per-structure plots
│   └── plot_bars.py                      # Bar chart variants
│
├── metrics/
│   ├── raw/
│   │   ├── pcaps/                        # tcpdump packet captures
│   │   ├── space/                        # Per-request wire/header/body bytes CSVs
│   │   └── time/                         # Per-iteration server timing CSVs (ns)
│   └── aggregated/
│       ├── overhead_ratio.csv            # Total overhead — wire_bytes / logical_bytes
│       ├── header_body_ratio.csv         # Framing overhead — wire_bytes / encoded_body_bytes
│       ├── overhead_decomposition.csv    # Breakdown of encoding vs framing contribution
│       └── ser_deser_overhead.csv        # Ser/deser overhead — ser+deser time (ns)
│
├── results_lab/                          # Final PNG plots (two-machine experiment)
├── results_local/                        # Final PNG plots (local testing)
│
├── machine_specs.txt                     # Hardware specs capture script + output
└── versions_used.txt                     # k6, tshark, Go version strings
```

---

## 3. Input Space

### 3.1 Space Experiments (Encoding & Framing Overhead)

The space experiment measures how many bytes land on the wire relative to the logical payload.

```
I_space = Payload × Structure × Protocol

Payload   = { 32B, 64B, 128B, 512B, 1KB, 8KB }
Structure = { flat, nested, wide, array }
Protocol  = { REST, gRPC }

|I_space|  = 6 × 4 × 2 = 48 configurations
```

| Dimension | Values | Description |
|-----------|--------|-------------|
| **Payload** | 32 B → 8 KB (6 sizes) | Target logical (pre-serialization) data size. The generator iteratively tunes the number/length of key-value pairs to hit each target within ~5%. |
| **Structure** | flat, nested, wide, array | Four structural patterns that exercise different serialization code-paths. |
| **Protocol** | REST, gRPC | REST = JSON body over HTTP/1.1; gRPC = Protobuf binary over HTTP/2. |

**Structure Types:**

| Structure | Shape | Exercises |
|-----------|-------|-----------|
| **Flat** | `{key_0: "val", key_1: "val", ...}` | Baseline — simple string-to-string map |
| **Nested** | `{a: {b: {c: ... }}}` | Deep object nesting; tests recursive serialization |
| **Wide** | `{k0: "v", k1: "v", ..., kN: "v"}` | Many short keys; high key-count-to-value-size ratio |
| **Array** | `{items: ["v0", "v1", ...]}` | Repeated homogeneous elements |

### 3.2 Time Experiments (Serialization Overhead)

The time experiment measures how long serialization and deserialization take, in nanoseconds.

```
I_time = Payload × Structure × Protocol

Payload   = { 32B, 64B, 128B, 512B, 1KB, 8KB }
Structure = { flat, nested, wide, array }
Protocol  = { REST, gRPC }

|I_time|   = 6 × 4 × 2 = 48 configurations
```

Each configuration runs for **R = 1000 requests** in a single k6 run. The first 10% of samples are discarded as warm-up, and the **mean** is reported per configuration.

**Concurrency is fixed at c = 1** — a single sequential request stream — to isolate serialization cost from queueing and scheduling effects.

---

## 4. Two-Machine Setup

### 4.1 Network Topology

```
┌─────────────────────────┐    Gigabit Ethernet    ┌─────────────────────────┐
│      CLIENT MACHINE     │  Realtek RTL8168/r8169  │      SERVER MACHINE     │
│                         │◄──────────────────────►│                         │
│  enp3s0: 10.10.10.1/30  │    1000 Mb/s  Full-Dup  │  enp3s0: 10.10.10.2/30  │
│                         │                         │                         │
│  • k6 (load generator)  │                         │  • rest-server :8080    │
│  • tcpdump / tshark     │                         │  • grpc-server :50051   │
│  • python3 (plots)      │                         │  • Go runtime           │
│  • this repo            │                         │  • this repo            │
└─────────────────────────┘                         └─────────────────────────┘
```

Two isolated Linux machines are connected via a **point-to-point Gigabit Ethernet** cable with static IPs on a `/30` subnet. There is no router, switch, or competing traffic — ensuring fully deterministic wire captures.

### 4.2 Machine Specifications

Both machines are **identical**:

| Component | Specification |
|-----------|--------------|
| **OS** | Ubuntu 24.04.4 LTS |
| **Kernel** | 6.8.0-85-generic |
| **CPU** | 12th Gen Intel Core i7-12700 (12 cores, 24 threads, up to 4.9 GHz) |
| **RAM** | 16 GB DDR |
| **NIC** | Realtek RTL8111/8168/8411 PCI Express Gigabit Ethernet Controller |
| **NIC Driver** | r8169 |
| **Link** | 1000 Mb/s, Full Duplex, Twisted Pair |

### 4.3 Software Versions

| Tool | Version | Used On |
|------|---------|---------|
| **Go** | go1.26.2 linux/amd64 | Both (server builds + k6 runtime) |
| **k6** | v2.0.0-rc1 (commit fb943a6a80) | Client only |
| **TShark (Wireshark)** | 3.6.2 | Client only |
| **tcpdump** | system default (Ubuntu 24.04) | Client only |
| **Python 3** | system default (Ubuntu 24.04) + matplotlib, numpy | Client only |
| **gRPC (Go)** | v1.80.0 | Server builds |
| **Protobuf (Go)** | v1.36.11 | Server builds |

---

## 5. Architecture

### 5.1 Client — k6 Sweep & Metric Collection

The client machine runs **k6** (a Go-based load generator) that performs a parameter sweep over the input space. For each `(payload_size, structure, protocol)` configuration:

1. **Payload generation** — `generator.js` builds a structured JS object targeting the specified byte size.
2. **Request dispatch** — k6 sends the request using the appropriate protocol (HTTP POST for REST, gRPC `invoke()` for gRPC).
3. **Metric capture** — depending on the experiment:
   - **Space**: `tcpdump` captures all packets on `enp3s0` during the request; `tshark` post-processes the pcap into wire/header/body byte counts.
   - **Time**: k6 extracts and logs the server-side ser/deser timing returned via a response header (REST) or response field (gRPC).

### 5.2 Server — Minimal Echo Servers

Both servers are **minimal echo servers** written in Go — they receive a payload and echo it back with no business logic:

| Server | Port | Behaviour |
|--------|------|-----------|
| **REST** | `:8080` | `POST /echo` — reads JSON body, echoes it back as JSON. Returns `X-Server-Ns` header with server-side deser+ser time in nanoseconds. |
| **gRPC** | `:50051` | `Echo` RPC — receives `EchoRequest` with `repeated Entry`, echoes the entries back in `EchoResponse`. Returns `server_ns` field with server-side timing. |

The echo design isolates **protocol overhead** from application logic — the server does zero processing on the payload data itself.

### 5.3 Native Encoding per Protocol

Each protocol uses its **native serialization** on the same logical data:

```
Generator → Structured JS Object (key-value map)
     │
     ├── REST  → JSON.stringify(object)                → HTTP/1.1 POST body
     │
     └── gRPC  → repeated Entry { key, value }         → native Protobuf encoding
```

This ensures the Space experiment observes **real encoding differences** (JSON text verbosity vs Protobuf binary compactness), not just header framing differences.

### Architecture Diagram

![Architecture Diagram](assets/setup.png)

```
CLIENT MACHINE (10.10.10.1)                              SERVER MACHINE (10.10.10.2)
┌──────────────────────────────────────┐                 ┌────────────────────────────┐
│                                      │                 │                            │
│  ┌────────────────────────────────┐  │   HTTP/1.1      │  ┌──────────────────────┐  │
│  │         k6 Sweep Engine        │  │   POST /echo    │  │   REST Echo Server   │  │
│  │                                │──│────────────────►│──│     :8080            │  │
│  │  • generator.js (payloads)     │  │◄────────────────│──│  JSON ↔ JSON echo    │  │
│  │  • sweep.js    (experiment)    │  │   JSON response  │  │  + X-Server-Ns hdr   │  │
│  │                                │  │                 │  └──────────────────────┘  │
│  │  Sweeps over:                  │  │                 │                            │
│  │   payload × structure ×proto   │  │   HTTP/2        │  ┌──────────────────────┐  │
│  │                                │──│────────────────►│──│   gRPC Echo Server   │  │
│  └────────────────────────────────┘  │◄────────────────│──│     :50051           │  │
│                                      │  gRPC Echo RPC   │  │  Protobuf ↔ Proto   │  │
│  ┌────────────────────────────────┐  │                 │  │  + server_ns field    │  │
│  │      Metric Collection         │  │                 │  └──────────────────────┘  │
│  │                                │  │                 │                            │
│  │  [Space] tcpdump on enp3s0     │  │                 └────────────────────────────┘
│  │     └─► tshark → CSV           │  │
│  │         (wire / header / body) │  │
│  │                                │  │
│  │  [Time] server_ns (server)     │  │
│  │     └─► CSV (per-request ns)   │  │
│  │                                │  │
│  └────────────────────────────────┘  │
│                                      │
│  ┌────────────────────────────────┐  │
│  │     Post-Processing (Python)   │  │
│  │                                │  │
│  │  aggregate.py  → Metrics      │  │
│  │  plot_space.py → PNG charts   │  │
│  │  plot_time.py  → PNG charts   │  │
│  └────────────────────────────────┘  │
│                                      │
└──────────────────────────────────────┘
```

---

## 6. Running the Experiments

### 6.1 Prerequisites

Install the following tools on the **client machine** (or the single machine for local tests):

| Tool | Purpose | Install |
|------|---------|---------|
| **Go** ≥ 1.22 | Build the echo servers | [go.dev/dl](https://go.dev/dl/) |
| **k6** ≥ v0.50 | Load generation & parameter sweeps | [k6.io/docs/get-started/installation](https://k6.io/docs/get-started/installation/) |
| **tcpdump** | Packet capture (Space experiment) | `apt install tcpdump` / pre-installed on macOS |
| **tshark** (Wireshark CLI) | Pcap → wire/header/body byte analysis | `apt install tshark` / `brew install wireshark` |
| **Python 3** + matplotlib, numpy | Aggregation & plot generation | `pip3 install matplotlib numpy` |

On the **server machine** (two-machine setup only), you need **Go** to build the servers.

### 6.2 Two-Machine Lab Run

This is the primary experiment mode. The client machine runs k6 + tcpdump; the server machine runs the Go echo servers.

**Step 1 — Build and start servers on the server machine:**

```bash
cd Network-Overhead
go build -o rest-server ./servers/rest/
go build -o grpc-server ./servers/grpc/

# Start both servers (in separate terminals or backgrounded)
./rest-server &    # listens on :8080
./grpc-server &    # listens on :50051
```

**Step 2 — Run experiments from the client machine:**

```bash
# Set required environment variables
export SERVER_IP=10.10.10.2          # IP of the server machine
export IFACE=enp3s0                  # network interface facing the server

# Run everything: space + time experiments, then aggregation & plots
./scripts/run_experiment.sh all

# Or run individual stages:
./scripts/run_experiment.sh space      # space experiment only (+ analysis)
./scripts/run_experiment.sh time       # time experiment only  (+ analysis)
./scripts/run_experiment.sh analysis   # aggregation + plotting only
```

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `SERVER_IP` | **Yes** | — | IP address of the server machine |
| `IFACE` | **Yes** | — | Network interface facing the server (e.g. `eth0`, `enp3s0`) |
| `K6_BIN` | No | `k6` | Path to the k6 binary |

> **Note:** The space experiment requires `sudo` for tcpdump. The script will prompt for your password once and keep credentials alive for the duration of the run.

### 6.3 Local Test (Single Machine / macOS)

For quick sanity checks without a two-machine setup. Runs everything locally on the loopback interface (`lo0` on macOS).

```bash
cd Network-Overhead

# Run all experiments (space + time + analysis)
./scripts/local_test.sh

# Or run individual stages:
./scripts/local_test.sh space     # space experiment only
./scripts/local_test.sh time      # time experiment only
```

The local test script automatically:
- Builds both Go servers (`rest-server`, `grpc-server`)
- Starts and stops servers as needed
- Uses `lo0` (loopback) for tcpdump captures
- Runs 20 iterations per config for time (vs 1000 in lab) and 100 for space
- Cleans up server processes on exit

### 6.4 Analysis Only

If you already have raw CSVs and pcaps and just want to re-run aggregation and plotting:

```bash
./scripts/run_experiment.sh analysis
```

This runs:
1. `analysis/aggregate.py` — raw CSVs → aggregated overhead metrics
2. `analysis/plot_space.py` — encoding & framing overhead charts
3. `analysis/plot_time.py` — ser/deser timing charts
4. `analysis/plot_bars.py` — bar chart variants

### 6.5 Output Locations

| Output | Path |
|--------|------|
| Raw space CSVs | `metrics/raw/space/*.csv` |
| Raw time CSVs | `metrics/raw/time/*.csv` |
| Packet captures | `metrics/raw/pcaps/*.pcap` |
| Aggregated metrics | `metrics/aggregated/*.csv` |
| Plots (lab run) | `results_lab/*.png` |
| Plots (local test) | `results_local/*.png` |

---

## Acknowledgements

COMET Lab, IIIT Bangalore, for providing access to lab systems for the purpose of conducting the experiments in this project.

---

**Author:** Kartikeya Dimri
<br>**Email:** Kartikeya.Dimri@iiitb.ac.in
<br>Integrated Master of Technology in CSE, IIIT Bangalore
