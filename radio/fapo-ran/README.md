# FAPO RAN Capability

Exoskeleton RAN Capability for AVA007: **FAPO** (Fast Autonomous
Policy Optimizer) isolated inside a `ran` capability, behind a real
srsRAN adapter, with a safety envelope between the optimizer and the
radio.

`models.py`, `capability.py`, and the AVA007 registry keep the
architecture note's contracts (same `optimize()` signatures, same
`RANState`). What this repo adds is the step the note ended on:
**replacing the `NotImplementedError` stub with a real srsRAN
control/telemetry interface** — plus the Lyapunov engine upgrade
(`fapo.py`, LDPTRLQ drift-plus-penalty with the `V` operating point),
the safety layer, and the validation stack a 1 s control loop needs
before it touches hardware.

## Architecture

```
AVA007 / AMOS
             |
       Capability API      registry.get("ran")  ->  optimize()
             v
    +--------------------------------------+
    | RAN Capability  (ran_capability/)    |
    |   FAPO            policy optimizer    |
    |   SafetyEnvelope  clamps, ramping,   |
    |                   rate limit,        |
    |                   stale-telemetry    |
    |                   watchdog           |
    |   RANAdapter      transport boundary |
    +------------------+-------------------+
                       |
        +--------------+---------------+
        |              |               |
 SRSRANAdapter  SimulatedSRSRANAdapter  (tools/fake_srsran.py)
 control socket   in-process digital     wire-compatible test
 (JSON-Lines v1)  twin, no hardware      peer for CI
        |
        v
  srsRAN Project gNB  <-- srsran-patch/ (real scheduler patch series)
        |
     gNB  /  SDR/RF
        |
        UE
```

Three peer implementations of the same wire protocol: the real
patched srsRAN scheduler (C++), a Python fake gNB for integration
tests, and a digital twin (no sockets) for closed-loop FAPO
validation. The C++ server is not a demo: it is compiled into
`libsrsran_sched` and serves telemetry collected from the scheduler's
own per-slice state.

## Repository layout

```
ava007/capabilities.py            CapabilityRegistry (agent side; unchanged)
ran_capability/
  models.py                       SlicePolicy / RANTelemetry (+ per-slice SliceTelemetry view)
  fapo.py                         FAPO — LDPTRLQ Lyapunov drift-plus-penalty optimizer
  capability.py                   RANCapability (unchanged)
  adapter.py                      RANAdapter ABC + SRSRANAdapter re-export
  protocol.py                     wire protocol v1 constants + endpoint parsing
  safety.py                       SafetyEnvelope + SafetyLimits + SafetyReport
  control_loop.py                 failure-isolated asyncio loop (observe->optimize->apply)
  config.py                       default slice policies, cell PRB budget
  cli.py                          build_registry() + fapo-loop entrypoint
  srsran/
    control_socket_adapter.py     SRSRANAdapter (the real adapter)
    json_socket.py                async JSON-Lines client (tcp:// / unix://)
    twin.py                       SimulatedSRSRANAdapter digital twin
bootstrap.py                      wiring; AVA invokes registry.get("ran").optimize()
tools/fake_srsran.py              protocol-compatible fake gNB (CI test peer)
scripts/interop_check.py          cross-language interop check (Python adapter <-> real C++ server)
srsran-patch/                     real srsRAN Project patch series + INTEGRATION.md
tests/                            47 pytest cases (FAPO/Lyapunov, safety, wire, closed loop)
docs/                             handoff manifest + full build worklog
```

## Quickstart

```bash
pip install -e .[dev]

# 1. closed loop against the digital twin (no SDR, no sockets)
python bootstrap.py --twin --period 1.0

# 2. adapter over the wire against the fake gNB
python tools/fake_srsran.py --endpoint tcp://127.0.0.1:9001 &
python bootstrap.py --endpoint tcp://127.0.0.1:9001

# 3. the real gNB: apply the patch series to srsRAN Project release_25_10
#    (see srsran-patch/INTEGRATION.md), run the gNB with
#      fapo_control: { enabled: true, endpoint: tcp://127.0.0.1:4445 }
#    and start the loop:
python bootstrap.py --endpoint tcp://127.0.0.1:4445

# 4. cross-language interop check against the real C++ server (test fixture).
#    Either build it inside the full srsRAN build tree
#    (build/tests/unittests/scheduler/fapo_interop_server, see
#    srsran-patch/INTEGRATION.md), or compile it standalone:
#      cd srsRAN_Project && g++ -std=c++17 -O1 -DFMT_HEADER_ONLY \
#        -Iinclude -Ilib -Iexternal -Iexternal/fmt/include \
#        tests/unittests/scheduler/fapo/fapo_interop_main.cpp \
#        lib/scheduler/fapo/fapo_control_server.cpp \
#        lib/srslog/srslog.cpp lib/srslog/srslog_c.cpp \
#        lib/srslog/backend_worker.cpp lib/srslog/event_trace.cpp \
#        lib/srslog/formatters/*.cpp -lpthread -o /tmp/fapo_interop_server
python scripts/interop_check.py /tmp/fapo_interop_server

# 5. tests
python -m pytest tests/ -q
```

Endpoints are `tcp://host:port` or `unix:///path/to/sock` (the
original note's `http://127.0.0.1:9000` becomes
`tcp://127.0.0.1:9001`; the control plane is JSON-Lines, not REST).

## Wire protocol v1 (summary)

One UTF-8 JSON object per `\n`-terminated line. Full schema and error
codes: `ran_capability/protocol.py`.

| Op | Request | Response payload |
|----|---------|------------------|
| `hello` | `{"v":1,"id":N,"op":"hello"}` | `server`, `protocol`, `capabilities` |
| `get_telemetry` | `...` | `ts`, `cell{...}`, `slices{...}`, `policies{...}` |
| `apply` | `{"actions":[{slice_id, prbs, tx_power_dbm}]}` | `applied[]`, `rejected[]` (partial success) |
| `reset` | `{"mode":"baseline"}` | watchdog revert to static config |
| `ping` | `...` | `pong` |

Design points:

* **Radio is source of truth.** Every telemetry response carries the
  gNB's static slice policies; `RANState.slices` is built from them,
  never from client-side assumptions.
* **Per-slice telemetry, two views.** The patched scheduler feed is
  per-slice (queue depth, latency, actual PRB grant, HARQ loss). The
  frozen flat `RANTelemetry` fields keep the worst-slice aggregation
  (max over slices) for backward compatibility, while the full view is
  preserved on the additive `RANTelemetry.slices` map — that is what
  the Lyapunov virtual queues (`y`, `z`, `F`) consume. Both the real
  adapter and the twin populate it identically.
* **Partial success on apply.** Unknown/out-of-bound slices come back
  in `rejected[]`; the adapter logs them as warnings.

## The operating point: Lyapunov `V` (power–delay tradeoff)

`fapo.py` implements the LDPTRLQ framework from the FAPO design:
per-slice **virtual queues** accumulate constraint violation (the
Lyapunov drift), and each cycle the decision minimizes the
drift-plus-penalty objective with penalty weight `V`:

* `y[s,t]` — backlog vs service deficit (queue-stability drift);
* `z[s,t]` — latency-budget violation budget (ms over the slice cap,
  e.g. the RLL 10 ms ceiling);
* `F[s,t]` — guaranteed-share isolation deficit: grows when the
  scheduler's *actual* grant (`prbs_used` from the gNB feed) drops
  below the slice's guaranteed minimum, and pushes back.

The `[O(1/V), O(V)]` tradeoff of the Lyapunov bound is the runtime
knob, not a simulation parameter:

```
python bootstrap.py --endpoint tcp://127.0.0.1:4445 --fapo-v 100
```

* Larger `V` (e.g. 100) discounts accumulated pressure → the engine
  holds fewer resources, spends **less transmit power**, tolerates
  more queueing delay.
* Smaller `V` (e.g. 1) chases zero drift → maximum allocations and
  power, minimal delay.

`V_REF = 100` is the reference operating point (the tuned production
setting); defaults preserve the original backoff/ramp semantics. The
closed-loop signature is asserted in `tests/test_fapo_lyapunov.py::
test_closed_loop_v_operating_point_over_twin`, and the virtual queues
drive the *real* per-slice scheduler metrics over the wire — the same
engine runs against the twin, the fake gNB, and the patched srsRAN
gNB unchanged.

Adversarial conditions (sustained overload, jamming-style telemetry
degradation, feed loss) are handled by construction, not by
simulation: overload raises `y`/`z` and saturates the RLL slice
within its budget; feed loss trips the stale-telemetry watchdog and
reverts to baseline; under-granting raises `F` and defends the
guaranteed share.

## FAPO action -> gNB change (mapping)

| FAPOAction field | Patched-scheduler meaning |
|------------------|---------------------------|
| `prbs` | new **maximum PRB limit** for the slice (the same RRM-policy knob the static config uses), clamped to the cell capacity, effective at the next slot indication |
| `tx_power_dbm` | accepted and echoed but **advisory**: the scheduler has no runtime TX-power control (SDR-specific) until RF headroom is validated on the bench |

See `srsran-patch/INTEGRATION.md` for the three control surfaces and
their caveats.

## Safety model (`safety.py`)

`SafetyEnvelope` decorates FAPO with the same
`optimize(state) -> list[FAPOAction]` contract, so `RANCapability` is
untouched. Layers, outermost first:

1. **Stale-telemetry watchdog** — telemetry older than
   `telemetry_max_age_s` (default 3 s = 3 cycles): stop optimizing,
   apply *baseline* (min PRBs / max power), bypass the rate limiter,
   mark the report degraded.
2. **Optimizer failure containment** — an exception in FAPO reverts to
   baseline instead of crashing the loop.
3. **Apply rate limit** — at most one optimization per
   `min_apply_interval_s` (0.5 s default); holds the previous policy
   between applies.
4. **Hard clamps** — PRBs into `[min_prbs, max_prbs]`, power into
   `[floor, max_power_dbm]` (defense in depth; FAPO also clamps).
5. **Ramp limits** — ≤ 25% of a slice's max PRBs per cycle, ≤ 2 dB
   power per cycle; cold start ramps up from baseline, so the radio
   never sees a step change.
6. **Cell budget** — sums of slice allocations exceeding
   `cell_prb_cap` are shaved proportionally from headroom above each
   minimum.

The gNB side re-clamps everything independently (never trusts the
client) — see `srsran-patch/INTEGRATION.md`.

The 1 s default period (`--period`, `ControlLoop(period_s=1.0)`)
matches the srsRAN metrics cadence; the loop itself is
failure-isolated (errors are counted, retried with exponential
backoff, never fatal).

## Tests

`python -m pytest tests/ -q` → 47 passed:

* `test_fapo.py` — bounds, saturation, per-slice latency pressure,
  monotonicity.
* `test_fapo_lyapunov.py` — the `V` operating point (fixed-state and
  closed-loop over the twin), virtual-queue stability (y/z drain after
  relief), `F` isolation defense against real under-granting,
  determinism, backoff window, constructor compatibility.
* `test_safety.py` — clamps, ramp ratchet, rate limit, budget scaling,
  watchdog revert, optimizer-failure containment.
* `test_protocol.py` — endpoint parsing (rejects the old `http://`
  form), protocol constants.
* `test_adapter_protocol.py` — the real `SRSRANAdapter` over TCP:
  telemetry aggregation, apply round-trip, error responses, silent-peer
  timeout, unreachable endpoint.
* `test_capability_loop.py` — closed loop over the twin (queues drain,
  zero errors), watchdog degrades and applies baseline mid-run, loop
  survives an adapter outage and recovers.

Verified additionally, against the real srsRAN tree
(`release_25_10`, commit `d2f4b70`):

* patch series applies cleanly (`git apply --check` + `git am`, 4/4);
* `libsrsran_sched` incl. the FAPO module compiles warning-free;
* upstream scheduler regression suite `scheduler_test`: 95/95;
* C++ unit tests (telemetry seqlock + full protocol end-to-end): 3/3;
* cross-language interop: the Python `SRSRANAdapter` drives the real
  C++ server (hello / telemetry / apply with server-side clamping /
  reset) — PASS; `scripts/interop_check.py` reproduces it, and the
  per-slice scheduler view (`prbs_used`, per-slice queue/latency)
  arrives in `RANTelemetry.slices` from the real server.

## Honest limitations

* **The patch is pinned to srsRAN Project `release_25_10`** (commit
  `d2f4b70`). It applies cleanly there and rebases with little effort
  onto nearby releases; the self-contained `lib/scheduler/fapo/`
  module carries the bulk of the code.
* **The adapter is the hardware boundary.** None of this makes a
  handset modem (e.g. an S26 Ultra's) into a programmable gNodeB; the
  capability controls a srsRAN gNB on an SDR, full stop.
* **Runtime tx power control is SDR-specific** and touches RF
  practice; power actions are advisory until measured on the bench.
* **The digital twin is a model, not a simulator.** It validates
  FAPO/safety/loop dynamics (queueing response to PRB allocation), not
  3GPP conformance or channel realism.

## Next step

The gNB side is now real: apply the patch series to a testbed gNB
(`srsran-patch/INTEGRATION.md`), attach a UE, and run the loop at
1 s with the SafetyEnvelope engaged. Compare FAPO behavior between
twin and bench before relaxing the watchdog, and treat power actions
as advisory until measured.

## Handoff (Ava007 → Cybernetic Ava007)

This repository is the handoff state. `docs/TRANSFER_MANIFEST.md`
carries the verification matrix, destination setup steps, and the
architecture invariants that must survive the transfer;
`docs/worklog.md` is the full append-only build history
(Tasks 1–3). On the destination side, only `ava007.capabilities`
and `ran_capability.capability` should ever be imported — everything
below those surfaces is the capability's own business.
