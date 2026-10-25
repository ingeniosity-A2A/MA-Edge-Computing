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
