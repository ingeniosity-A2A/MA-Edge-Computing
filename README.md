# MA Edge Computing

Edge runtime projects for the Samsung Galaxy S26 Ultra and Ingeniosity's on-device execution stack.

## Architecture and deployment

- [AVA-007 Edge Connectivity Runbook](docs/AVA007_EDGE_CONNECTIVITY_RUNBOOK.md) — S26 Ultra/eSIM boundaries, embedded Tailscale Android SDK, private tunnel to OVH VPS, Aperture, OpenSandbox, and acceptance tests.
- [Distributed coordination research integration](docs/DISTRIBUTED_COORDINATION_ARXIV_2401_18030.md) — Rust coordination primitives with explicit limits on convergence and physical OTA-C claims.
- [Deep Fusion Memory integration](docs/DEEP_FUSION_MEMORY_ARXIV_2610_25100.md) — DFM governance scaffold; no claim of trained hidden-state fusion.
- [24/16 Intelligence Coupling and execution integration](docs/INTELLIGENCE_COUPLING_24_16.md) — executable Rust evidence coupling, candidate registry, AVA-007 authority boundary, and NVIDIA Aerial research mapping.

## Android apps

- [Ava007 Dialer](apps/Ava007-Dialer/README.md) — self-managed Android VoIP dialer and Telnyx integration.
- [Ava007 GenieX Edge Runtime](apps/Ava007-GenieX/README.md) — isolated Android build using Qualcomm's GenieX on-device LLM SDK from Maven Central.
- [TailSocks for Galaxy S26 Ultra](apps/TailSocks/README.md) — upstream Tailscale client integration, ARM64 build instructions, and deployment/security notes.
- [Tailscale Android SDK](apps/Tailscale-Android-SDK/README.md) — isolated build of the upstream Android client and reusable libtailscale AAR.

Each app owns its Android/Gradle build configuration. Do not merge app-specific dependencies into another app just to share a build.

## RAN and radio stack

- [FAPO RAN Capability](radio/fapo-ran/README.md) — Lyapunov drift-plus-penalty optimizer, safety envelope, srsRAN adapter, digital twin, interoperability tooling, and pinned patch series.
- [Hardware-free RAN profile](radio/fapo-ran/docs/HARDWARE_FREE_RAN_PROFILE.md) and [machine-readable profile](packages/csn/ran-5g.yaml) — VPS-hosted FAPO twin for software-only clients, with synthetic provenance and explicit hardware boundaries.

FAPO does not turn the Galaxy S26 Ultra handset modem into a programmable gNodeB. Real RAN operation requires supported SDR/RF hardware, a compatible srsRAN build, and an authorized test network. Start with the digital twin.

## Authority and execution contract

AVA-007 owns objectives, interpretation, Source Truth acceptance, curation, promotion, and action authorization. Exoskeleton owns runtime execution, persistence mechanics, synchronization, scheduling, transport, and resource governance. REV.IKE is read-only interpretation and candidate generation; it cannot accept proposals, write Source Truth, authorize promotion, or execute actions.

The air-coupling crate coordinates evidence only. It does not merge weights, promote models, or execute actions. Hardware-dependent capabilities remain disabled until prerequisites and tests are verified.
