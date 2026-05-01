# Two-Machine Experiment Setup Guide

> REST vs gRPC Network Overhead — Gigabit Ethernet, point-to-point

## Network Topology

```
┌─────────────────────────┐    Gigabit Ethernet    ┌─────────────────────────┐
│      CLIENT MACHINE     │  Realtek RTL8168/r8169  │      SERVER MACHINE     │
│                         │◄──────────────────────►│                         │
│  enp3s0: 10.10.10.1/30  │    1000 Mb/s  Full-Dup  │  enp3s0: 10.10.10.2/30  │
│                         │                         │                         │
│  • k6 (load gen)        │                         │  • rest-server :8080    │
│  • tcpdump / tshark     │                         │  • grpc-server :50051   │
│  • python3 (plots)      │                         │  • Go runtime           │
│  • this repo            │                         │  • this repo            │
└─────────────────────────┘                         └─────────────────────────┘
```

---

## Step 0 — Prerequisites

Install on **both machines**:

```bash
sudo apt update
sudo apt install -y golang-go git
```

Install on the **client machine** (10.10.10.1) only:

```bash
# k6 (load generator)
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D68
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt update && sudo apt install -y k6

# tshark + tcpdump (packet capture & analysis)
sudo apt install -y tshark tcpdump

# Python3 + matplotlib (aggregation & plotting)
sudo apt install -y python3 python3-pip python3-matplotlib python3-numpy
```

> [!TIP]
> When installing tshark, select **Yes** when asked if non-superusers should capture packets, then run:
> ```bash
> sudo usermod -aG wireshark $USER
> ```
> Log out and back in for the group change to take effect.

---

## Step 1 — Clone the Repo (Both Machines)

```bash
git clone <your-repo-url> ~/Network-Overhead
cd ~/Network-Overhead
```

---

## Step 2 — Build the Servers (Server Machine — 10.10.10.2)

```bash
cd ~/Network-Overhead
go mod download
go build -o rest-server ./servers/rest/
go build -o grpc-server ./servers/grpc/

# Verify binaries exist
ls -lh rest-server grpc-server
```

---

## Step 3 — Configure the Ethernet Link (Both Machines)

The point-to-point Ethernet cable has no DHCP — static IPs must be assigned manually.

**On the CLIENT machine (10.10.10.1):**

```bash
# Bring the interface up
sudo ip link set enp3s0 up

# Assign the static IP
sudo ip addr add 10.10.10.1/30 dev enp3s0
```

**On the SERVER machine (10.10.10.2):**

```bash
# Bring the interface up
sudo ip link set enp3s0 up

# Assign the static IP
sudo ip addr add 10.10.10.2/30 dev enp3s0
```

> [!NOTE]
> These IPs are ephemeral — they will be lost on reboot. To make them
> persistent, create a Netplan config:
> ```bash
> sudo tee /etc/netplan/99-experiment.yaml << 'EOF'
> network:
>   version: 2
>   ethernets:
>     enp3s0:
>       addresses:
>         - 10.10.10.1/30    # use 10.10.10.2/30 on the server
> EOF
> sudo netplan apply
> ```

**Verify on both machines:**

```bash
# Confirm interface is up at 1 Gbps
ethtool enp3s0 | grep -E 'Speed|Duplex|Link'
# Expected:
#   Speed: 1000Mb/s
#   Duplex: Full
#   Link detected: yes

# Confirm IP is assigned
ip addr show dev enp3s0 | grep inet
# Expected (client): inet 10.10.10.1/30
# Expected (server): inet 10.10.10.2/30
```

**Test connectivity from the client:**

```bash
ping -c 3 10.10.10.2
```

---

## Step 4 — Start the Servers (Server Machine — 10.10.10.2)

**Option A — Two terminals (or tmux panes):**

```bash
# Terminal 1
cd ~/Network-Overhead
./rest-server
# → "REST echo server listening on :8080"

# Terminal 2
cd ~/Network-Overhead
./grpc-server
# → "gRPC echo server listening on :50051"
```

**Option B — Single terminal with background processes:**

```bash
cd ~/Network-Overhead
./rest-server &
./grpc-server &
echo "Both servers started"
```

> [!IMPORTANT]
> Keep both servers running for the entire experiment duration.

---

## Step 5 — Verify Connectivity (Client Machine — 10.10.10.1)

```bash
# Test REST echo
curl -s -X POST http://10.10.10.2:8080/echo \
  -H "Content-Type: application/json" \
  -d '{"test":"ok"}' | head -c 100
echo

# Test gRPC port
nc -zv 10.10.10.2 50051
```

Expected: a JSON echo response and `Connection to 10.10.10.2 50051 port [tcp/*] succeeded!`

---

## Step 6 — Run the Experiment (Client Machine — 10.10.10.1)

```bash
cd ~/Network-Overhead
chmod +x scripts/run_experiment.sh

# Full experiment (space + time + analysis + plots)
SERVER_IP=10.10.10.2 IFACE=enp3s0 ./scripts/run_experiment.sh all
```

It will prompt for your `sudo` password once (needed for tcpdump), then run unattended.

### What Happens

| Phase | Description | Est. Duration |
|-------|-------------|---------------|
| **Connectivity** | Checks REST :8080 and gRPC :50051 reachable | ~2 sec |
| **Space** | 4 structures × 6 sizes × 2 protocols = 48 data points. Each: start tcpdump → 100 k6 requests → stop tcpdump → tshark analysis | ~8–10 min |
| **Time** | 4 structures × 6 sizes × 2 protocols = 48 sweeps, 1000 iterations each with nanosecond server timing | ~5–8 min |
| **Aggregation** | Computes overhead ratios, header/body ratios, decomposition table | ~1 sec |
| **Plots** | Generates all PNG charts (encoding, framing, overhead, timing) | ~5 sec |

### Running Individual Phases

```bash
# Space experiment only
SERVER_IP=10.10.10.2 IFACE=enp3s0 ./scripts/run_experiment.sh space

# Time experiment only
SERVER_IP=10.10.10.2 IFACE=enp3s0 ./scripts/run_experiment.sh time

# Re-run analysis + plots only (no server needed, uses existing CSVs)
./scripts/run_experiment.sh analysis
```

---

## Step 7 — Collect Results (Client Machine)

After completion, all outputs are on the client at `~/Network-Overhead/`:

```
metrics/
├── raw/
│   ├── space/               # Per-request wire/header/body bytes
│   │   ├── rest_flat.csv
│   │   ├── grpc_flat.csv
│   │   ├── rest_nested.csv
│   │   ├── grpc_nested.csv
│   │   ├── rest_wide.csv
│   │   ├── grpc_wide.csv
│   │   ├── rest_array.csv
│   │   └── grpc_array.csv
│   ├── time/                # Per-iteration server timing (ns)
│   │   └── (same 8 files)
│   └── pcaps/               # Raw packet captures (can delete)
└── aggregated/
    ├── overhead_ratio.csv
    ├── header_body_ratio.csv
    ├── ser_deser_overhead.csv
    └── overhead_decomposition.csv

results/                     # PNG plots
├── encoding_overhead_2x2.png
├── encoding_overhead_{flat,nested,wide,array}.png
├── framing_overhead_2x2.png
├── framing_overhead_{flat,nested,wide,array}.png
├── overhead_ratio_2x2.png
├── header_body_ratio_2x2.png
├── ser_deser_2x2_grid.png
└── ser_deser_vs_payload_{flat,nested,wide,array}.png
```

To copy results to your Mac for viewing:

```bash
scp -r user@10.10.10.1:~/Network-Overhead/results/ ./results_lab/
scp -r user@10.10.10.1:~/Network-Overhead/metrics/ ./metrics/
```

---

## Step 8 — Stop the Servers (Server Machine — 10.10.10.2)

```bash
# If foreground — Ctrl+C in each terminal

# If background
pkill rest-server
pkill grpc-server
```

---

## Troubleshooting

### "Connection refused" on port 8080 or 50051

```bash
# On server: verify servers are listening
ss -tlnp | grep -E '8080|50051'

# If using UFW firewall, open the ports
sudo ufw allow from 10.10.10.1 to any port 8080 proto tcp
sudo ufw allow from 10.10.10.1 to any port 50051 proto tcp
```

### tcpdump permission error

```bash
# The script uses sudo. If that fails:
sudo setcap cap_net_raw+ep $(which tcpdump)
```

### Empty CSVs / 0 bytes

tcpdump didn't capture anything. Verify the interface and IP:

```bash
# On client: manually check you can see traffic to the server
sudo tcpdump -i enp3s0 host 10.10.10.2 -c 5

# Then in another terminal:
curl http://10.10.10.2:8080/echo -X POST -d '{"a":"b"}' -H "Content-Type: application/json"
```

If tcpdump shows nothing, the interface name or IP is wrong.

### k6 not found

```bash
which k6 || echo "not installed"
# If snap-installed:
K6_BIN=/snap/bin/k6 SERVER_IP=10.10.10.2 IFACE=enp3s0 ./scripts/run_experiment.sh all
```

### tshark can't decode gRPC / missing grpc dissector

```bash
tshark --version | head -3
# Need tshark 3.x+. Update if older:
sudo apt install -y wireshark-common
```
