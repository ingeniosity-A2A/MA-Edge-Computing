#!/usr/bin/env bash
set -Eeuo pipefail

# Build helper for a Linux host. Keeps upstream sources and generated artifacts
# inside this app directory, which is git-ignored. Does not install to a device.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="$ROOT/upstream"
REPO_URL="https://github.com/bropines/tailsocks.git"
EXPECTED_NDK="28.2.13676358"

for cmd in git java go; do
  command -v "$cmd" >/dev/null 2>&1 || {
    printf 'ERROR: required command not found: %s\n' "$cmd" >&2
    exit 1
  }
done

if [[ -z "${ANDROID_HOME:-}" && -n "${ANDROID_SDK_ROOT:-}" ]]; then
  export ANDROID_HOME="$ANDROID_SDK_ROOT"
fi
if [[ -z "${ANDROID_HOME:-}" ]]; then
  printf 'ERROR: set ANDROID_HOME to your Android SDK directory.\n' >&2
  exit 1
fi
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk/$EXPECTED_NDK}"

[[ -d "$ANDROID_NDK_HOME" ]] || {
  printf 'ERROR: expected Android NDK not found: %s\n' "$ANDROID_NDK_HOME" >&2
  exit 1
}

if [[ ! -d "$UPSTREAM/.git" ]]; then
  git clone --recurse-submodules "$REPO_URL" "$UPSTREAM"
else
  git -C "$UPSTREAM" status --short
  printf '\nExisting upstream checkout found. Fetching updates without overwriting local changes.\n'
  git -C "$UPSTREAM" fetch --recurse-submodules origin
  if [[ -n "$(git -C "$UPSTREAM" status --porcelain)" ]]; then
    printf 'ERROR: upstream checkout has local changes; refusing to reset or overwrite them.\n' >&2
    exit 1
  fi
  git -C "$UPSTREAM" pull --ff-only --recurse-submodules
fi

printf '\n=== Upstream revision ===\n'
git -C "$UPSTREAM" rev-parse HEAD
printf '\n=== Build native Go bridge ===\n'
(
  cd "$UPSTREAM/appctr"
  bash build.sh
)
printf '\n=== Build debug APK ===\n'
(
  cd "$UPSTREAM"
  ./gradlew :app:assembleDebug
)
printf '\n=== APK artifacts ===\n'
find "$UPSTREAM/app/build/outputs/apk/debug" -maxdepth 1 -type f -name '*.apk' -print
