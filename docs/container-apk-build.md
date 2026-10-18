# Container APK build (B) — draft only, not executed

**No paid container job started. No GitHub Actions required for acceptance.**

## Goal

Build `apps/Ava007-Dialer` debug (or release) APK in a disposable container, copy the artifact out, verify checksum.

## Image requirements

| Component | Version |
|-----------|--------|
| JDK | 17 |
| Android SDK platform | 36 |
| Android build-tools | 36.x |
| Gradle | 8.11.1 (via project wrapper) |

## Example Dockerfile (draft)

```dockerfile
FROM eclipse-temurin:17-jdk-jammy

ENV ANDROID_HOME=/opt/android-sdk
ENV PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget unzip git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install command-line tools + platform 36 (pin versions when locking the image)
RUN mkdir -p $ANDROID_HOME/cmdline-tools \
 && cd /tmp \
 && wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O cmdtools.zip \
 && unzip -q cmdtools.zip -d $ANDROID_HOME/cmdline-tools \
 && mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest \
 && yes | sdkmanager --licenses \
 && sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"

WORKDIR /workspace/apps/Ava007-Dialer
```

## Build sequence (operator host)

```bash
# from repo root, after clone
cd apps/Ava007-Dialer
bash scripts/bootstrap-wrapper.sh

# run container with SDK + mount
docker build -t mec-dialer-build -f ../../docs/Dockerfile.apk ../../
docker run --rm \
  -v "$PWD":/workspace/apps/Ava007-Dialer \
  -v mec-gradle-cache:/root/.gradle \
  mec-dialer-build \
  ./gradlew :app:assembleDebug --no-daemon

# persist artifact
mkdir -p ../../artifacts/apk
cp app/build/outputs/apk/debug/app-debug.apk ../../artifacts/apk/
sha256sum ../../artifacts/apk/app-debug.apk | tee ../../artifacts/apk/app-debug.apk.sha256
```

## Notes

- Wrapper jar is not in git; `bootstrap-wrapper.sh` is mandatory on fresh clones.
- Debug APK ~54 MB (WebRTC natives).
- Do not use Termux as the project layout for this module.
- Optional Node scripts for Telnyx are independent of the APK build.
