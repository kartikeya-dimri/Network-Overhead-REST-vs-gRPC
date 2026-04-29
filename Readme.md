## Final Experimentation Design

**0. Project Title**
Characterising Network Overhead in REST vs gRPC

---

**1. Experimental Setup**

I have the following setup:

* Two isolated linux machines connected via an ethernet cable.
* On one k6 client will run that does a sweep on input space for one protocol.
* On the other the server runs - only one at a time for a given protocol.
* So separate runs for REST and gRPC

---

**2. Aim**
Study and characterise network overheads across two dimensions: Space (protocol framing and encoding efficiency) and Time (serialization and deserialization cost).

---

**3. Input Space**

```
I_space = Payload × Protocol
I_time  = Payload × Structure × Protocol

Payload    = {128B, 512B, 1KB, 8KB, 64KB, 512KB}
Structure  = {flat, nested, wide, array}
Protocol   = {REST, gRPC}
Concurrency = 1  (fixed, controlled)

|I_space| = 6 × 2 = 12 configurations
|I_time|  = 6 × 4 × 2 = 48 configurations
```

---

**4. Output Parameters**

Number of output parameters: n = 2 for space experiment, n = 1 for time experiment.

Let x denote an input configuration from the respective input space.

**O1(x) — Overhead Ratio** *(space experiment)*
```
O1(x) = wire_bytes(x) / logical_payload_bytes(x)

where logical_payload_bytes = pre-serialization application data size
      wire_bytes = TCP payload bytes captured via tcpdump
```
Captures combined encoding + framing overhead. Denominator is pre-serialization size so both JSON verbosity and HTTP header cost are reflected.

**O2(x) — Header+Body:Body Ratio** *(space experiment)*
```
O2(x) = wire_bytes(x) / encoded_body_bytes(x)
       = (header_bytes + body_bytes) / body_bytes

where encoded_body_bytes = serialized payload bytes on wire, excluding protocol headers
```
Captures framing overhead only. Denominator is post-serialization so encoding cost is excluded. The difference between O1 and O2 isolates encoding efficiency (JSON vs Protobuf) from header framing cost (HTTP/1.1 vs HTTP/2 HPACK).

**O3(x) — Serialization + Deserialization Time** *(time experiment)*
```
O3(x) = (ser_client + deser_client) + (deser_server + ser_server)

measured on separate clocks:
  client clock : ser_client + deser_client
  server clock : deser_server + ser_server
  reported     : sum of the two, added in post-processing
```
Each configuration runs for R = 1000 requests in a single k6 run. First 10% of samples discarded as warm-up. Mean reported per configuration:
```
O3_mean(x) = mean over R samples of O3(x)
```

**Final output sets:**
```
O1_final = { O1(x)      | x ∈ I_space }   →  12 values
O2_final = { O2(x)      | x ∈ I_space }   →  12 values
O3_final = { O3_mean(x) | x ∈ I_time  }   →  48 values
```

---

**5. Measurement Method**

| Output | Tool | Side | Notes |
|---|---|---|---|
| O1 | tcpdump + tshark | Client | `wire_bytes = sum(tcp.len)` across all frames per run |
| O2 | tcpdump + tshark | Client | Header bytes from HTTP/1.1 header fields or HTTP/2 HEADERS frames (type=1); body bytes from HTTP/2 DATA frames (type=0) |
| O3 | time.Since(time.Now()).Nanoseconds() on client and server side
     independently measured on each machine's monotonic clock and
     summed in post-processing. Unit: nanoseconds.

For O1 and O2: a single tcpdump capture per configuration is sufficient — wire bytes are fully deterministic on a dedicated point-to-point ethernet link with no competing traffic.

For O3: 1000 request samples per configuration within one k6 run. No repeated runs needed — variance at c=1 on an isolated machine is negligible.

---

**6. Total Recorded Values**

```
Space experiment : |I_space| × 2 outputs  =  12 × 2       =    24 values
Time experiment  : |I_time|  × R samples  =  48 × 1000    = 48000 values
                                                             ──────────────
Total raw                                                  = 48024 values

Collapsed for plotting:
  O1_final : 12 values
  O2_final : 12 values
  O3_final : 48 values  (1000 samples → 1 mean per configuration)
```

---

**7. Plots**

**Plot 1 — Overhead Ratio vs Payload Size**
```
Type    : line graph
x-axis  : payload size (log scale)
y-axis  : O1 = wire_bytes / logical_payload_bytes
Lines   : 2 — REST, gRPC
Captures: combined encoding + framing overhead
```

**Plot 2 — Header+Body:Body Ratio vs Payload Size**
```
Type    : line graph
x-axis  : payload size (log scale)
y-axis  : O2 = wire_bytes / encoded_body_bytes
Lines   : 2 — REST, gRPC
Captures: framing overhead only (HPACK compression effect visible here)
```

**Plot 3 — Ser/Deser Time vs Payload Size (2×2 subplot grid)**
```
Type    : 2×2 grid of line graphs, one cell per structure
x-axis  : payload size (log scale), shared across all cells
y-axis  : O3_mean in microseconds, shared scale across all cells
Lines   : 2 per cell — REST, gRPC
Layout  :
          ┌─────────────┬─────────────┐
          │    Flat     │   Nested    │
          ├─────────────┼─────────────┤
          │    Wide     │    Array    │
          └─────────────┴─────────────┘
Captures: ser/deser cost by structure type and protocol
```