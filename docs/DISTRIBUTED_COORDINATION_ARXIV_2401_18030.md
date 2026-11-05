# Distributed coordination layer — research integration

**Reference:** Navneet Agrawal, Renato L. G. Cavalcante, Sławomir Stańczak,
“Distributed fixed-point algorithms for dynamic convex optimization over
decentralized and unbalanced wireless networks,” arXiv:2401.18030 (2024).
https://arxiv.org/abs/2401.18030

## Architectural placement

This layer coordinates Capability Sensory Nodes over authenticated Rustunnel
peer links. It sits between local sensing/capability execution and the AVA-007
reasoning/authorization gate. It may produce estimates and policy candidates;
it does not authorize actions or promote observations into Source Truth.

## Integrated in this commit

The air-consensus crate provides a bounded superiorization-inspired candidate
selector, a validated local weighted-mixing step, packet-level digital
telemetry aggregation (weighted mean/min/max/generation), and unit tests.
These are primitives, not a reproduction of the paper's full distributed
algorithm, OTA-C protocol, or convergence proof.

## Mathematical and systems boundaries

1. **Quasi-Fejér convergence is not implied by averaging.** The paper's
   almost-sure convergence result depends on its stated operator,
   perturbation, stochastic communication, and existence assumptions. The
   current mixing function is one weighted update only. It does not prove
   convergence for arbitrary directed, unbalanced, time-varying Rustunnel
   graphs. Implement the paper's exact equations, graph assumptions,
   step-size conditions, and proof-linked conformance tests before claiming it.
2. **Superiorization is more than a safety clamp.** The selector is a small
   feasibility-preserving improvement primitive, not the full construction
   or convergence analysis from the paper.
3. **OTA-C is physical-layer computation.** The paper's OTA-C uses wireless
   multiple-access-channel superposition. Rustunnel is packet transport;
   digital aggregation decodes and aggregates packets in software. It is not
   OTA-C, does not provide O(1) network traffic, and does not remove the need
   to transmit contributions to an aggregation point.
4. **Unbalanced tunnels do not automatically satisfy theorem assumptions.**
   Bandwidth asymmetry, delay, loss, churn, and directed reachability must be
   modeled and measured.
5. **15 Hz is a requirement, not a result.** FAPO currently documents a 1 s
   default control period. Timing scope and missed-update behavior require
   measurement before claiming 15 Hz tracking or a 5 ms loop.

## Integration sequence

1. Add authenticated peer identity, monotonic generation checks, freshness
   bounds, replay rejection, and explicit graph snapshots at Rustunnel.
2. Implement the exact decentralized update and physical OTA-C behind a
   separate MAC interface only when compatible radio hardware exists.
3. Simulate directed/unbalanced time-varying graphs, bounded loss/delay,
   node churn, and time-varying local objectives.
4. Compare centralized and standard digital-consensus baselines.
5. Record seeds, graph traces, input hashes, compiler/runtime, and measured
   convergence/communication/latency results.

## Verification

Run from air-ava007/: cargo fmt --all -- --check;
cargo test --workspace --all-targets; cargo clippy --workspace --all-targets
-- -D warnings.

Crate tests validate local primitives only. They do not validate the paper's
convergence theorem, OTA-C, Rustunnel mesh behavior, live RAN safety, or
production performance.
