# Ava007 Dialer APK builder — JDK 17 + Android SDK 36 + Gradle via project wrapper
# Build context: repository root (MA-Edge-Computing)
# No GitHub Actions. No Termux project layout.

FROM eclipse-temurin:17-jdk-jammy

ENV ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    DEBIAN_FRONTEND=noninteractive

ENV PATH="${PATH}:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates unzip git \
    && rm -rf /var/lib/apt/lists/*

# Android command-line tools (pinned zip); platform 36 + build-tools 36.0.0
ARG CMDTOOLS_ZIP=commandlinetools-linux-11076708_latest.zip
RUN mkdir -p ${ANDROID_HOME}/cmdline-tools \
    && cd /tmp \
    && curl -fsSL -o cmdtools.zip \
        "https://dl.google.com/android/repository/${CMDTOOLS_ZIP}" \
    && unzip -q cmdtools.zip -d ${ANDROID_HOME}/cmdline-tools \
    && mv ${ANDROID_HOME}/cmdline-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest \
    && rm -f cmdtools.zip \
    && yes | sdkmanager --licenses >/dev/null \
    && sdkmanager \
        "platform-tools" \
        "platforms;android-36" \
        "build-tools;36.0.0"

WORKDIR /workspace/apps/Ava007-Dialer

CMD ["bash", "-lc", "bash scripts/bootstrap-wrapper.sh && ./gradlew :app:assembleDebug --no-daemon"]
