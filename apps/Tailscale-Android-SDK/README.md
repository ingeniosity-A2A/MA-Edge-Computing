# Tailscale Android SDK build

This project builds the upstream Tailscale Android client and the reusable
`libtailscale.aar` library in an isolated workspace. It does not depend on the
GenieX or NovaDial Gradle projects and does not modify Omni OS.

## Outputs

- `dist/libtailscale.aar` — Android library artifact for app integration.
- `dist/tailscale-debug.apk` — debug APK for manual installation/testing.
- `dist/SHA256SUMS` — checksums for both artifacts.

## Build on Linux

Requirements: Git, Go, Java/JDK 17, Make, curl, unzip, and enough disk space
for the Android SDK/NDK and Go build cache. The upstream Makefile installs the
required Android SDK components through `make androidsdk`.

From this directory:

```bash
bash build.sh
```

The build uses the official source at https://github.com/tailscale/tailscale-android.
The upstream Android Gradle project and wrapper are used from the cloned source
tree at `.work/tailscale-android/android/`; this avoids maintaining a divergent
copy of Tailscale's Android app configuration.

To choose another workspace or artifact directory:

```bash
TAILSCALE_WORK_DIR=/path/to/tailscale-android \
TAILSCALE_OUTPUT_DIR=/path/to/output \
bash build.sh
```

## Important distinction

The AAR is a library, not an installable Android app. The APK is installable,
but is an unsigned/debug build intended for testing. The script does not sign a
production release or install anything on a device. Android VPN permission and
Tailscale account authentication still require user interaction.
