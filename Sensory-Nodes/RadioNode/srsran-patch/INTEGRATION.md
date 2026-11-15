# FAPO Control Interface — Real srsRAN Project Integration

This directory contains the **real patch series** that integrates the FAPO
(Fast Autonomous Policy Optimizer) control interface into the
[srsRAN Project](https://github.com/srsran/srsRAN_Project) 5G SA gNB.
There is no demo/example backend: the control server runs inside the real
scheduler, serves telemetry collected from the real per-slice scheduler state,
and applies actions through the scheduler's own slice-policy machinery.

## What the patch does

The stock srsRAN scheduler has no runtime control API. This patch series adds
a small, self-contained control plane to the scheduler:

| Component | Location (after patch) | Purpose |
|-----------|------------------------|---------|
| Telemetry snapshots & command queue | `lib/scheduler/fapo/fapo_telemetry.h` | Per-slice state snapshots (seqlock store, writer = slot thread) + MPMC queue of control commands |
| FAPO v1 control server | `lib/scheduler/fapo/fapo_control_server.{h,cpp}` | JSON-Lines server (TCP or Unix socket) on a dedicated non real-time thread; implements `hello`, `ping`, `get_telemetry`, `apply`, `reset` |
| Slice telemetry collection | `inter_slice_scheduler::fapo_collect_cell_snapshot()` | Real per-slice state: RB limits, priority, #UEs, pending DL/UL bytes (RLC/BSR), allocation-rate EWMA, S-NSSAI |
| Action application | `inter_slice_scheduler::fapo_apply_slice_max_rbs()` | Changes the slice's maximum PRB limit (the same knob the RRM policy configuration uses), preserving `dedicated <= min <= max` |
| Baseline reset | `ran_slice_instance::cfg_baseline` + `fapo_reset_slice_policies_to_baseline()` | Restores the RB limits the slices were instantiated with |
| Slot-loop wiring | `ue_scheduler_impl::fapo_publish_snapshot()/fapo_drain_commands()` | Publishes snapshots and applies drained commands in the slot thread (non-blocking, RT-safe) |
| Real packet loss | `ue_event_manager` DL HARQ ACK/NACK counters | Cell-level DL HARQ NACK ratio |
| Config plumbing | `scheduler_expert_config` + gNB `fapo_control:` YAML section | Enable/disable, endpoint, telemetry period, metric normalization knobs |

### Threading model (real-time safety)

* The **slot thread** publishes snapshots into the seqlock store and drains
  commands from the MPMC queue — both are non-blocking operations, so the
  FAPO path is safe to call from `slot_indication()` (RTSAN-annotated).
* The **control server thread** owns the sockets and JSON handling; it never
  touches scheduler state directly. Actions are enqueued and applied by the
  slot thread at the next slot indication.
* TCP endpoints are loopback-enforced by the configuration validator
  (`allow_remote: true` overrides, explicitly).

### Telemetry semantics (all derived from real scheduler state)

* `slices.<id>.queue_depth` — pending bytes normalized to 0..100 % against
  `queue_ref_bytes` (config, default 1 MB).
* `slices.<id>.latency_ms` — pending bytes / estimated drain rate, where the
  drain rate is `(avg PDSCH + PUSCH RBs per slot) * tb_bytes_per_rb_slot * slots_per_sec`.
* `slices.<id>.prbs_used` — rounded allocation-rate EWMA maintained by
  `ran_slice_instance` (the same counters the inter-slice priority uses).
* `cell.packet_loss` — cumulative DL HARQ NACK ratio.
* `cell.available_prbs` — cell PRBs minus sum of per-slice used PRBs.
* `policies` — **the radio is the source of truth**: effective (possibly
  FAPO-modified) slice limits are echoed back; clients must clamp to these.
* Slice naming: `srb`, `default`, or `sst<N>` / `sst<N>-sd<0x…>` from the
  slice's S-NSSAI. The `slice_type` reported to FAPO follows the standardized
  SST values (1 = eMBB → `high_capacity`, 2 = URLLC → `rll`).

### Action semantics

* `apply {slice_id, prbs}` sets the slice's **maximum** PRB limit, clamped to
  `[1, cell PRBs]` and monotonic with the current min/dedicated limits.
  It takes effect at the next slot indication; the new effective policy is
  reported in the following telemetry response.
* `tx_power_dbm` is accepted and echoed (clamped), but is **advisory only**:
  the scheduler has no runtime TX-power control. This is reported in the
  telemetry via `nominal_tx_power_dbm` (0 = unknown).
* `reset` restores the baseline RB limits of all slices of every active cell.

## Base version

Series generated and verified against:

* **srsRAN Project `release_25_10`**, commit `d2f4b70dda8e2c557d5b05a0ac5f92dbddda19bc`

For other releases, expect to rebase the (small) scheduler-integration hunks;
the `lib/scheduler/fapo/` module itself is self-contained.

## Applying the patch

```bash
git clone https://github.com/srsran/srsRAN_Project.git
cd srsRAN_Project
git checkout release_25_10          # d2f4b70...

git am /path/to/fapo-ran/srsran-patch/patches/0001-*.patch
git am /path/to/fapo-ran/srsran-patch/patches/0002-*.patch
git am /path/to/fapo-ran/srsran-patch/patches/0003-*.patch
git am /path/to/fapo-ran/srsran-patch/patches/0004-*.patch
```

## Building

Follow the standard srsRAN Project build (cmake >= 3.16, g++, libsctp-dev,
yaml-cpp, mbedtls, fmt is vendored). Then build the gNB as usual:

```bash
mkdir build && cd build
cmake ../ -DCMAKE_BUILD_TYPE=RelWithDebInfo -DENABLE_WERROR=ON
make -j$(nproc) srsngb              # or the full `all`
```

The FAPO sources are compiled into `libsrsran_sched` (no new external
dependencies; the JSON parser/writer is self-contained).

### Tests (optional, require `-DBUILD_TESTING=ON`)

```bash
cmake --build build --target fapo_control_server_test
./tests/unittests/scheduler/fapo_control_server_test
```

### Standalone interop fixture (no full gNB build)

The `fapo_interop_server` fixture instantiates the *real*
`fapo_control_server` (the class compiled into `libsrsran_sched`) and
publishes deterministic telemetry from a background thread. If you
only want the cross-language interop check without configuring the
whole gNB build, it compiles standalone against the patched tree's
headers (all dependencies are vendored upstream):

```bash
cd srsRAN_Project
g++ -std=c++17 -O1 -DFMT_HEADER_ONLY \
    -Iinclude -Ilib -Iexternal -Iexternal/fmt/include \
    tests/unittests/scheduler/fapo/fapo_interop_main.cpp \
    lib/scheduler/fapo/fapo_control_server.cpp \
    lib/srslog/srslog.cpp lib/srslog/srslog_c.cpp \
    lib/srslog/backend_worker.cpp lib/srslog/event_trace.cpp \
    lib/srslog/formatters/*.cpp \
    -lpthread -o /tmp/fapo_interop_server
```

Verified with GCC 14.2 against `release_25_10` @ `d2f4b70`.

## Configuring the gNB

Add a `fapo_control` section to the gNB YAML (top level, next to `log`,
`metrics`, ...):

```yaml
fapo_control:
  enabled: true
  endpoint: tcp://127.0.0.1:4445     # or unix:///tmp/fapo-gnb.sock
  telemetry_period_ms: 1000          # snapshot publication period
  queue_ref_bytes: 1000000           # queue-depth normalization reference
  tb_bytes_per_rb_slot: 200          # ~1.6 Mbps/RB, used for latency estimation
  max_clients: 4
  # nominal_tx_power_dbm: 21         # optional: report cell TX power (advisory)
  # max_latency_ms: 1000             # optional: reported slice latency bound
  # allow_remote: false              # set true only on isolated test networks
```

Slices themselves are configured as usual via the cell `slices:` list
(S-NSSAI + RRM ratios). Each configured slice appears in the FAPO telemetry
under its S-NSSAI-derived name together with the reserved `srb` and `default`
slices.

## Running and verifying

Start the gNB. On success the log shows:

```
[FAPO    ] [I] FAPO control server: listening on tcp://127.0.0.1:4445
[SCHED   ] [I] FAPO control interface enabled (endpoint: tcp://127.0.0.1:4445, telemetry period: 1000 ms)
```

Once a cell is activated and the first telemetry period elapses, clients can
connect. A quick smoke test from the Python stack:

```bash
cd fapo-ran
python scripts/interop_check.py /path/to/fapo_interop_server   # against the test fixture
# or point the SRSRANAdapter / ControlLoop at tcp://127.0.0.1:4445
```

When FAPO applies an action, the scheduler log shows:

```
[SCHED   ] [I] cell=0 slice=2: FAPO changing slice max RBs: 20 -> 30 (min: 5, dedicated: 0)
```

and a reset:

```
[SCHED   ] [I] cell=0: FAPO restored baseline slice policies.
```

## Verification status (all executed against the real tree)

| Check | Result |
|-------|--------|
| Patch series applies (`git apply --check` + `git am`) to pristine `release_25_10` | PASS (4/4) |
| Full compile of `libsrsran_sched` incl. FAPO module (gcc 14) | PASS, no new warnings |
| Upstream scheduler regression suite (`scheduler_test`) | 95/95 PASS |
| Upstream `sched_no_ue_test` | 2/2 PASS |
| FAPO unit tests (`fapo_control_server_test`: seqlock consistency + full protocol e2e) | 3/3 PASS |
| Cross-language interop: Python `SRSRANAdapter` ↔ real C++ server (hello/telemetry/apply+clamp/reset) | PASS |
| Python side test suite (`pytest`, protocol/safety/twin/loop) | 38/38 PASS |

`fapo_interop_server` (from the tests patch) is a **test fixture** that runs
the real control server with a deterministic snapshot publisher emulating the
slot thread — it exists so external clients can be integration-tested without
an SDR. The production path is the server embedded in `scheduler_impl`.

## Safety properties

1. **Loopback by default** — the validator rejects non-loopback TCP endpoints
   unless `allow_remote: true`.
2. **Hard clamps** — every requested PRB limit is clamped to `[1, cell PRBs]`
   and kept monotonic with the slice's dedicated/min limits server-side
   (the Python `SafetyEnvelope` clamps again client-side).
3. **Bounded control** — max 4 clients (configurable up to 16), 1 MiB request
   line limit, bounded command queue, max 32 commands drained per slot.
4. **RT isolation** — the slot thread only performs non-blocking seqlock/queue
   operations; all socket and JSON work happens on the control thread.
5. **Resettable** — `reset` restores boot-time RRM policies; the DU manager's
   own slice reconfiguration always remains authoritative and overrides FAPO.
