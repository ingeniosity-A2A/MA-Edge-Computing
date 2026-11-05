# MA Edge Computing

Edge runtime projects for the Samsung Galaxy S26 Ultra and Ingeniosity's on-device execution stack.

## Architecture and deployment

- [AVA-007 Edge Connectivity Runbook](docs/AVA007_EDGE_CONNECTIVITY_RUNBOOK.md) — S26 Ultra/eSIM boundaries, embedded Tailscale Android SDK, private tunnel to OVH VPS, Aperture, OpenSandbox, and acceptance tests.

## Android apps

- [Ava007 Dialer](apps/Ava007-Dialer/README.md) — self-managed Android VoIP dialer and Telnyx integration.
- [Ava007 GenieX Edge Runtime](apps/Ava007-GenieX/README.md) — isolated Android build using Qualcomm's GenieX on-device LLM SDK from Maven Central.
- [TailSocks for Galaxy S26 Ultra](apps/TailSocks/README.md) — upstream Tailscale client integration, ARM64 build instructions, and deployment/security notes.
- [Tailscale Android SDK](apps/Tailscale-Android-SDK/README.md) — isolated build of the upstream Android client and reusable libtailscale AAR.

Each app owns its Android/Gradle build configuration. Do not merge app-specific dependencies into another app just to share a build.

## RAN and radio stack

- [FAPO RAN Capability](radio/fapo-ran/README.md) — Lyapunov drift-plus-penalty radio policy optimizer, isolated RAN capability API, safety envelope, srsRAN JSON-Lines control adapter, digital twin, interoperability tooling, and the pinned srsRAN Project patch series.

- [Hardware-free RAN profile](radio/fapo-ran/docs/HARDWARE_FREE_RAN_PROFILE.md) and [machine-readable profile](packages/csn/ran-5g.yaml) — VPS-hosted FAPO digital-twin mode for software-only edge clients, with synthetic-data provenance and explicit unintegrated-hardware boundaries.

FAPO controls a separately deployed srsRAN gNB through its adapter. It does not turn the Galaxy S26 Ultra's Qualcomm handset modem into a programmable gNodeB. The handset remains a UE; real RAN operation requires a supported SDR/RF front end, the patched srsRAN Project build, and a properly authorized test network. Start with the digital twin before connecting radio hardware.
