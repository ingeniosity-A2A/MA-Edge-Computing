# MA Edge Computing

Edge runtime projects for the Samsung Galaxy S26 Ultra and Ingeniosity's on-device execution stack.

## Android apps

- [Ava007 Dialer](apps/Ava007-Dialer/README.md) — self-managed Android VoIP dialer and Telnyx integration.
- [Ava007 GenieX Edge Runtime](apps/Ava007-GenieX/README.md) — isolated Android build using Qualcomm's GenieX on-device LLM SDK from Maven Central.

Each app owns its Android/Gradle build configuration. Do not merge app-specific dependencies into another app just to share a build.
