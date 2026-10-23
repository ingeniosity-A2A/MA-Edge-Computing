# TailSocks — Galaxy S26 Ultra

TailSocks is an independent Android Tailscale client by [bropines](https://github.com/bropines/tailsocks). This directory contains the Ingeniosity integration/build instructions; it does **not** copy, fork, or claim ownership of the upstream application's source.

- Upstream source: https://github.com/bropines/tailsocks
- Upstream guide: https://bropines.github.io/tailsocks/
- Latest upstream APK: https://github.com/bropines/tailsocks/releases/latest
- Target device: Samsung Galaxy S26 Ultra (ARM64 / `arm64-v8a`)
- Minimum Android API of upstream app: 24
- Current upstream build configuration declares compile SDK 37 and NDK 28.2.13676358. Confirm upstream requirements before building.

## Device deployment choice

For the quickest install, download the upstream release APK on the S26 Ultra and install it after reviewing the release and permissions. To build from source, use the steps below on a supported Linux build host. An Android SDK installed in Termux does not by itself guarantee that the upstream native Go/NDK build will work inside Android/Termux.

## Build from source (Linux host)

Prerequisites:

- Git, JDK 17, Go, Android SDK command-line tools
- Android platform 37 and build tools accepted by the upstream project
- Android NDK `28.2.13676358`
- Android SDK licenses accepted
- Network access to fetch upstream Git submodules and Go dependencies

```bash
git clone --recurse-submodules https://github.com/bropines/tailsocks.git
cd tailsocks
```

Set SDK/NDK paths for your host (adjust paths to your installation):

```bash
export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/28.2.13676358"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/build-tools/37.0.0:$PATH"
```

Build the native Go bridge and daemon binaries first, then the debug APK:

```bash
cd appctr
bash build.sh
cd ..
./gradlew :app:assembleDebug
```

The upstream debug build uses application ID `io.github.bropines.tailscaled.dev` and is designed to coexist with the release app. Look for the ARM64 APK under `app/build/outputs/apk/debug/` (usually the `app-arm64-v8a-debug.apk` split). Verify the exact output filename with:

```bash
find app/build/outputs/apk/debug -maxdepth 1 -type f -name '*.apk' -print
```

Install over USB with Android platform-tools enabled and USB debugging authorized:

```bash
adb devices
adb install -r app/build/outputs/apk/debug/app-arm64-v8a-debug.apk
```

If the actual output filename differs, use the path printed by `find`. Alternatively transfer the APK to the phone and install it locally.

## Select the correct networking mode

1. **Proxy mode** — best first test; does not require Android VPN permission or root. Only apps explicitly configured to use the local proxy are routed through TailSocks.
2. **VPN/TUN mode** — requests Android's VPN permission and can route device traffic through the tailnet/selected exit node.
3. **Root mode** — experimental system routing requiring a supported root solution. Do not enable it on a non-rooted S26 Ultra.

An exit node is not a source of mobile data: the phone still needs some working upstream connection (Wi-Fi, cellular, or tethering) to reach the tailnet. TailSocks cannot provide internet service where the phone has no underlying connectivity.

## Security and provenance

- Use upstream release notes and verify the source before installing.
- Never commit signing keystores, passwords, auth keys, device state, proxy credentials, or private tailnet configuration.
- Do not publish debug APKs as production releases or imply that Ingeniosity signed upstream artifacts.
- This integration has not been device-tested by this repository change. Record build logs and test Proxy mode before claiming success.
- Upstream project and trademark remain with their respective owners; TailSocks is not an official Tailscale product.
