#!/usr/bin/env bash
# Build Ava007 Dialer APK inside a container; copy artifact out; verify.
# Run on an operator host with Docker.
#
# From MA-Edge-Computing repo root:
#   bash apps/Ava007-Dialer/scripts/build-apk-container.sh
#
# Policy: no GitHub Actions, no Termux project setup.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIALER="$(cd "$SCRIPT_DIR/.." && pwd)"
MEC_ROOT="$(cd "$DIALER/../.." && pwd)"
DOCKERFILE="$DIALER/container/Dockerfile"
OUT_DIR="$DIALER/artifacts/apk"
IMAGE_TAG="${IMAGE_TAG:-mec-ava007-dialer-build:local}"

if [ ! -f "$DOCKERFILE" ]; then
  echo "Missing Dockerfile: $DOCKERFILE" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker, then re-run." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

echo "==> Building image $IMAGE_TAG (context: $MEC_ROOT)"
docker build -t "$IMAGE_TAG" -f "$DOCKERFILE" "$MEC_ROOT"

echo "==> Running assembleDebug"
docker run --rm \
  -v "$DIALER:/workspace/apps/Ava007-Dialer" \
  -v "mec-ava007-gradle-cache:/root/.gradle" \
  -e "ANDROID_HOME=/opt/android-sdk" \
  "$IMAGE_TAG" \
  bash -lc 'bash scripts/bootstrap-wrapper.sh && ./gradlew :app:assembleDebug --no-daemon'

APK_SRC="$DIALER/app/build/outputs/apk/debug/app-debug.apk"
if [ ! -f "$APK_SRC" ]; then
  echo "FAIL: APK not found at $APK_SRC" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
APK_DST="$OUT_DIR/app-debug-${STAMP}.apk"
cp -f "$APK_SRC" "$APK_DST"
cp -f "$APK_SRC" "$OUT_DIR/app-debug.apk"
sha256sum "$APK_DST" | tee "$APK_DST.sha256"
sha256sum "$OUT_DIR/app-debug.apk" > "$OUT_DIR/app-debug.apk.sha256"

BYTES="$(wc -c < "$APK_DST" | tr -d ' ')"
echo "==> OK: $APK_DST ($BYTES bytes)"
echo "==> sha256: $(cut -d' ' -f1 "$APK_DST.sha256")"
