# Edge Computing

Edge runtime projects for the Samsung Galaxy S26 Ultra and Ingeniosity's distributed execution stack.

## Network and edge-node architecture

**The Tailscale CLI bot is host-only.** It runs on the Ubuntu VPS beside that host's
`tailscaled` daemon and CLI. It is not deployed to the S26 Ultra, Termux, or other
Android edge clients. The bot observes the S26 as a tailnet peer from the VPS and may
perform only its explicitly allowlisted, reversible changes to the VPS node's local
Tailscale preferences. It cannot sign in, reconnect, or change the Android app's VPN
state. The Android Tailscale app owns that lifecycle.

The S26 is an edge client/sensory node: Android owns its network attachment and VPN;
Termux hosts user-space diagnostics and client-side services. Rustunnel is a separate
transport option for reaching phone-hosted services; it does not relocate the VPS
Tailscale bot or replace Tailscale identity and grants. See the
[Tailscale bot host-placement and authority contract](ops/network/tsbot/README.md)
and [AVA-007 Edge Connectivity Runbook](docs/AVA007_EDGE_CONNECTIVITY_RUNBOOK.md).

## Architecture and deployment

- [Tailscale host agent (tsbot)](ops/network/tsbot/README.md) — VPS-only daemon and MiMo operator assistant, host-local Tailscale CLI access, allowlisted repairs, and explicit Android boundary.
- [Rustunnel transport runbook](ops/network/rustunnel/README.md) — optional VPS↔S26 service transport; deployment status and private/public topology gates.
- [AVA-007 Edge Connectivity Runbook](docs/AVA007_EDGE_CONNECTIVITY_RUNBOOK.md) — S26 Ultra/eSIM boundaries, Android Tailscale ownership, private VPS reachability, Aperture, OpenSandbox, and acceptance tests.
- [Distributed coordination research integration](docs/DISTRIBUTED_COORDINATION_ARXIV_2401_18030.md) — Rust coordination primitives with explicit limits on convergence and physical OTA-C claims.
- [Deep Fusion Memory integration](docs/DEEP_FUSION_MEMORY_ARXIV_2610_25100.md) — DFM governance scaffold; no claim of trained hidden-state fusion.
- [24/16 Intelligence Coupling and execution integration](docs/INTELLIGENCE_COUPLING_24_16.md) — executable Rust evidence coupling, candidate registry, AVA-007 authority boundary, and NVIDIA Aerial research mapping.

## Sensory Nodes

Node implementations live in `Sensory-Nodes/`. No nodes are defined in this repository yet.

## RAN and radio stack

- [FAPO RAN Capability](Sensory-Nodes/RadioNode/README.md) — Lyapunov drift-plus-penalty optimizer, safety envelope, srsRAN adapter, digital twin, interoperability tooling, and pinned patch series.
- [Hardware-free RAN profile](Sensory-Nodes/RadioNode/docs/HARDWARE_FREE_RAN_PROFILE.md) and [machine-readable profile](packages/csn/ran-5g.yaml) — VPS-hosted FAPO twin for software-only clients, with synthetic provenance and explicit hardware boundaries.

FAPO does not turn the Galaxy S26 Ultra handset modem into a programmable gNodeB. Real RAN operation requires supported SDR/RF hardware, a compatible srsRAN build, and an authorized test network. Start with the digital twin.

## Authority and execution contract

AVA-007 owns objectives, interpretation, Source Truth acceptance, curation, promotion, and action authorization. Exoskeleton owns runtime execution, persistence mechanics, synchronization, scheduling, transport, and resource governance. REV.IKE is read-only interpretation and candidate generation; it cannot accept proposals, write Source Truth, authorize promotion, or execute actions.

Hardware-dependent capabilities remain disabled until prerequisites and tests are verified.
