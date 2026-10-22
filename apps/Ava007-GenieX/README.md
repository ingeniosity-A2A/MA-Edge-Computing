# Ava007 GenieX Edge Runtime

A standalone Android app workspace for validating Qualcomm's official GenieX Android binding on the Samsung S26 Ultra edge node. This is a clean, isolated Android build—not a dependency added to Ava007 Dialer.

## SDK source

- Maven coordinate: `com.qualcomm.qti:geniex-android:0.8.0`
- Official source: https://github.com/qualcomm/GenieX
- Official Android chat sample: https://github.com/qualcomm/ai-hub-apps/tree/release/geniex_chat_android
- Install guide: https://geniex.aihub.qualcomm.com/en/run/android/install
- Quickstart: https://geniex.aihub.qualcomm.com/en/run/android/quickstart

Version note: the supplied brief named 0.7.0, but the official GenieX release page lists 0.8.0 as the newer release (2 Oct 2026). This project pins 0.8.0 rather than the superseded version.

## Isolated Gradle

This project has its own wrapper configuration under `gradle/wrapper/` and uses Gradle 8.13.0 with Android Gradle Plugin 8.13.0. It does not use the global Termux Gradle installation or the Ava007 Dialer wrapper.

The GitHub contents API cannot store the wrapper JAR as a binary file. Bootstrap it once, then build:

```bash
cd apps/Ava007-GenieX
bash scripts/bootstrap-wrapper.sh
./gradlew --version
./gradlew :app:assembleDebug
```

Requirements: JDK 17, Android SDK platform/build-tools 36, internet access for Maven Central and the first model download. The build output is `app/build/outputs/apk/debug/app-debug.apk`.

## Runtime behavior

1. Initializes GenieX.
2. Downloads `unsloth/Qwen3-0.6B-GGUF` from Hugging Face when the model is not already available.
3. Loads it with the `llama_cpp` runtime and streams a local response.
4. Keeps model weights outside the APK; no NDK or CMake project setup is required.

GenieX is in developer preview. Device/backend capability determines whether NPU, GPU, or CPU execution is available; this starter leaves `compute_unit` unset per the official quickstart's recommended Snapdragon default.

## Transfer to the phone

After a successful build, copy `app/build/outputs/apk/debug/app-debug.apk` to the S26 Ultra and install it. The APK is not committed to GitHub.
