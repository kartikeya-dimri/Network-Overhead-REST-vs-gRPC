# Measuring Network Overhead in Space and Time — REST vs gRPC

## Lab Setup

![Lab Setup](assets/lab_setup.jpeg)

---

## Architecture

![Architecture Diagram](assets/setup.png)

---

## Running the Experiments

### Prerequisites

Install the following tools on the **client machine** (or the single machine for local tests):

| Tool | Purpose | Install |
|------|---------|---------|
| **Go** ≥ 1.22 | Build the echo servers | [go.dev/dl](https://go.dev/dl/) |
| **k6** ≥ v0.50 | Load generation & parameter sweeps | [k6.io/docs/get-started/installation](https://k6.io/docs/get-started/installation/) |
| **tcpdump** | Packet capture (Space experiment) | `apt install tcpdump` / pre-installed on macOS |
| **tshark** (Wireshark CLI) | Pcap → wire/header/body byte analysis | `apt install tshark` / `brew install wireshark` |
| **Python 3** + matplotlib, numpy | Aggregation & plot generation | `pip3 install matplotlib numpy` |

On the **server machine** (two-machine setup only), you need **Go** to build the servers.

### Two-Machine Lab Run

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

### Local Test (Single Machine / macOS)

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

### Analysis Only

If you already have raw CSVs and pcaps and just want to re-run aggregation and plotting:

```bash
./scripts/run_experiment.sh analysis
```

This runs:
1. `analysis/aggregate.py` — raw CSVs → aggregated overhead metrics
2. `analysis/plot_space.py` — encoding & framing overhead charts
3. `analysis/plot_time.py` — ser/deser timing charts
4. `analysis/plot_bars.py` — bar chart variants

### Output Locations

| Output | Path |
|--------|------|
| Raw space CSVs | `metrics/raw/space/*.csv` |
| Raw time CSVs | `metrics/raw/time/*.csv` |
| Packet captures | `metrics/raw/pcaps/*.pcap` |
| Aggregated metrics | `metrics/aggregated/*.csv` |
| Plots (lab run) | `results_lab/*.png` |
| Plots (local test) | `results_local/*.png` |
