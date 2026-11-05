# Hardware-free 5G/RAN profile

## Decision

The S26 Ultra is treated as a software-only edge client for this profile. It
does not provide RF, SDR, a programmable gNB, an eUICC replacement, or real
carrier/modem telemetry. All RAN policy execution and the existing digital
twin run on the VPS.

## What runs now

The repository already contains an executable FAPO path:

```bash
cd radio/fapo-ran
pip install -e '.[dev]'
python bootstrap.py --twin --period 1.0
python -m pytest tests/ -q
```

The in-process `SimulatedSRSRANAdapter` supports closed-loop FAPO and
SafetyEnvelope testing without SDR hardware. It is a software model, not a
full 5G gNB, RF channel simulator, or 3GPP conformance environment.

## Hardware substitution boundary

| Hardware function | Software-only treatment | Status |
|---|---|---|
| Radio unit / RF | Existing in-process FAPO digital twin | Implemented for policy testing only |
| RF IQ input | srsRAN file replay candidate | Not integrated in this profile |
| gNB | Existing FAPO twin | Not a full gNB |
| UE | srsRAN virtual UE candidate | Not integrated |
| Modem telemetry | Synthetic telemetry generator | Planned; must be labelled synthetic |
| eSIM/eUICC | Virtual profile-state model only | Planned; cannot provision or activate a real eSIM |
| GPU RAN | NVIDIA Aerial candidate | Disabled; supported GPU/runtime not established |

The profile deliberately does not claim that lpac replaces an eUICC or that
srsRAN file replay creates a complete RAN. NVIDIA Aerial cuPHY/cuMAC is not
enabled: execution requires a supported NVIDIA GPU and compatible stack,
which have not been established on the current VPS.

## Data provenance

Every generated observation must carry:

- `source: simulation`
- `is_synthetic: true`
- a timestamp and deterministic input/test-vector identity where applicable

Synthetic values must never be displayed or stored as carrier registration,
real signal strength, real RF measurements, or actual UE network telemetry.

## Control and timing

FAPO policy authority remains on the VPS. The handset is a policy consumer and
telemetry client only. The current FAPO CLI uses a 1-second control period by
default. A 5 ms policy or network round-trip guarantee is not implemented or
measured. Compute latency and transport latency must be benchmarked separately.

The existing SafetyEnvelope remains in the control path. Stale telemetry or
optimizer failure must revert to baseline according to the existing safety
implementation.

## Device boundary

The handset application must not invoke `mmcli`, `lpac`, `srsue`, raw modem
interfaces, AT commands, or direct RIL control. This is an application/repo
boundary; it does not claim to remove Android's own internal telephony stack.

## Acceptance criteria before enabling external integrations

1. Run the existing FAPO test suite and record the exact result.
2. Implement and test the synthetic telemetry generator with provenance
   assertions at serialization and ingestion boundaries.
3. Implement authenticated phone-to-VPS transport; verify the actual listener,
   identity, replay protection, and failure behavior.
4. Integrate IQ replay only after confirming the exact srsRAN driver, sample
   format, rate, and reproducible test vectors.
5. Integrate virtual UE only after confirming the supported srsRAN UE mode and
   proving an end-to-end test against the selected gNB/twin.
6. Enable Aerial only after confirming GPU model, driver/CUDA compatibility,
   supported Aerial release, and a runnable vendor example on the VPS.
7. Measure all performance targets. A YAML target or placeholder hash is not
   test evidence.

The machine-readable profile is
[`packages/csn/ran-5g.yaml`](../packages/csn/ran-5g.yaml).
