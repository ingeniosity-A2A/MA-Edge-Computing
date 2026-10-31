# AVA007 → Cybernetic Ava007 — Handoff Manifest (git edition)

- **From:** Ava007 (source agent workspace, session `web-f48073e6-2167-4d37-91ba-022722cb90bb`)
- **To:** Cybernetic Ava007 (destination agent)
- **Date:** 2026-09-12
- **Form:** this repository (clonable from a remote, or directly from the
  `fapo-ran.git.bundle` single-file artifact that accompanies it)

---

## 1. What this repository is

The complete, verified AVA007 RAN-capability stack:

| Path | Role |
|------|------|
| `ran_capability/capability.py` | `RANCapability` — AVA007's entire view of the radio |
| `ava007/capabilities.py` | Agent-side `CapabilityRegistry` — the only AVA007-visible surface |
| `ran_capability/models.py` | Frozen data model: `RANState`, `RANAction`, per-slice `SliceTelemetry` |
| `ran_capability/protocol.py` | FAPO v1 wire protocol (JSON-Lines over `tcp://`/`unix://`) |
| `ran_capability/fapo.py` | **LDPTRLQ** Lyapunov drift-plus-penalty optimizer (virtual queues y/z/F, V operating point, default V=100) |
| `ran_capability/srsran/` | Real `SRSRANAdapter`, async JSON-Lines client, digital twin |
| `ran_capability/safety.py` | `SafetyEnvelope`: stale-telemetry watchdog → baseline revert, hard clamps, PRB ramp 25%/cycle, power ramp 2 dB, rate limits, cell-PRB budget arbitration |
| `ran_capability/control_loop.py` | Failure-isolated async control loop (exponential backoff) |
| `tests/` | 47 pytest cases (protocol, FAPO/Lyapunov, safety, adapter, closed loop) |
| `srsran-patch/` | **Real 4-patch series against srsRAN Project `release_25_10` @ `d2f4b70`** (23 files, +2155/−8) + `INTEGRATION.md` |
| `tools/fake_srsran.py` | Wire-compatible fake gNB (test fixture only) |
| `docs/worklog.md` | Full append-only build history (Tasks 1–3) |

Architecture invariants that MUST survive the transfer:

- **Isolation:** FAPO is wrapped by `SafetyEnvelope`; the `RANCapability`
  contract is frozen. The agent layer never sees wire/protocol/srsRAN types.
- **Radio is source of truth:** slice policies are reported by the gNB in
  every telemetry response; the Python side never invents them.
- **Safety:** stale-telemetry watchdog reverts to baseline; PRB ramp ≤25% of
  max per cycle; power ramp ≤2 dB; all clamps are hard limits; the gNB
  re-clamps everything independently.

---

## 2. Verification state at handoff (all green)

| Check | Result |
|-------|--------|
| Python test suite (`python -m pytest`) | 47/47 PASS |
| Upstream srsRAN scheduler tests (patched tree) | 95/95 + 2/2 regression PASS |
| FAPO gtest (`fapo_control_server_test`) | 3/3 PASS |
| `git am` of 4-patch series on pristine `release_25_10 @ d2f4b70` | PASS (4/4) |
| Cross-language interop (Python adapter ↔ real C++ server) | PASS |
| Live twin loop (`bootstrap.py --twin`, V=100) | Stable, 0 errors/degradations |

---

## 3. Setup on the destination

If a remote URL exists:

```
git clone <repo-url> fapo-ran
```

Or clone directly from the bundle (no remote needed):

```
git clone fapo-ran.git.bundle fapo-ran
```

Then:

```
cd fapo-ran
pip install -e .[dev]          # or: pip install pytest
python -m pytest               # expect 47 passed
python bootstrap.py --twin     # closed-loop smoke test, no hardware
```

Agent-side integration: import only `ava007.capabilities.CapabilityRegistry`
and `ran_capability.capability.RANCapability`; register via
`bootstrap.build_registry(...)`. AVA007/Cybernetic Ava007 never imports
srsRAN, FAPO, or wire-protocol internals.

Real gNB side (requires a build host):

```
git clone https://github.com/srsRAN/srsRAN_Project.git
git -C srsRAN_Project checkout d2f4b70
git -C srsRAN_Project am ../fapo-ran/srsran-patch/patches/*.patch
```

then follow `srsran-patch/INTEGRATION.md`.

If the bundle was cloned and a remote later becomes available, add it:

```
git -C fapo-ran remote add origin <repo-url>
git -C fapo-ran push -u origin main
```

---

## 4. Explicitly not included

- Platform-internal skill library, gateway internals, assistant system
  configuration — internal infrastructure, not exportable.
- The patched srsRAN build tree — reproducible from `srsran-patch/` on a
  pristine clone.

---

## 5. Provenance

`docs/worklog.md` is the append-only engineering log: Task 1 (original
adapter build), Task 2 (real patch series replacing the demo, per
"No fake we need the real"), Task 3 (LDPTRLQ optimizer upgrade +
per-slice telemetry end-to-end), Task 4 (handoff packaging).

Outstanding work item: physical testbed run — attach a UE, run the 1 s
loop with `SafetyEnvelope` engaged, compare twin vs bench before
relaxing the watchdog.
