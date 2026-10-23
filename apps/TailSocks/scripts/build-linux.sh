#!/usr/bin/env bash
set -Eeuo pipefail

# Build the upstream TailSocks project for Galaxy S26 Ultra (arm64-v8a).
# Run on a supported Linux x86_64 host; this is not an Android/Termux build.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="$ROOT/upstream"
REPO_URL="https://github.com/bropines/tailsocks.git"
EXPECTED_NDK="28.2.13676358"

for cmd in git java go curl sha256sum patch tar gzip awk find; do
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
export PATH="$(go env GOPATH)/bin:$PATH"

[[ -d "$ANDROID_NDK_HOME" ]] || {
  printf 'ERROR: expected Android NDK not found: %s\n' "$ANDROID_NDK_HOME" >&2
  exit 1
}
[[ -f "$ANDROID_HOME/platforms/android-37/android.jar" ]] || {
  printf 'ERROR: Android SDK platform 37 is missing. Install it with sdkmanager 'platforms;android-37'.\n' >&2
  exit 1
}
[[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]] || {
  printf 'ERROR: upstream NDK script expects a Linux x86_64 build host.\n' >&2
  exit 1
}

if [[ ! -d "$UPSTREAM/.git" ]]; then
  git clone --recurse-submodules "$REPO_URL" "$UPSTREAM"
else
  if [[ -n "$(git -C "$UPSTREAM" status --porcelain)" ]]; then
    printf 'ERROR: upstream checkout has local changes; refusing to overwrite them.\n' >&2
    exit 1
  fi
  git -C "$UPSTREAM" fetch --recurse-submodules origin
  git -C "$UPSTREAM" pull --ff-only --recurse-submodules
fi

printf '\n=== Upstream revision ===\n'
git -C "$UPSTREAM" rev-parse HEAD

# appctr/build.sh calls the gomobile executable. Install the version pinned in
# appctr/go.mod when it is not already available; never use an unpinned latest.
MOBILE_VERSION="$(awk '$1 == "golang.org/x/mobile" { print $2 }' "$UPSTREAM/appctr/go.mod")"
[[ -n "$MOBILE_VERSION" ]] || {
  printf 'ERROR: cannot find golang.org/x/mobile version in appctr/go.mod.\n' >&2
  exit 1
}
for tool in gomobile gobind; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'Installing pinned %s (%s)\n' "$tool" "$MOBILE_VERSION"
    go install "golang.org/x/mobile/cmd/$tool@$MOBILE_VERSION"
  fi
done

printf '\n=== Build native Go bridge (ARM64 only) ===\n'
(
  cd "$UPSTREAM/appctr"
  TS_ABIS=arm64-v8a bash build.sh
)

printf '\n=== Build debug APK ===\n'
(
  cd "$UPSTREAM"
  ./gradlew :app:assembleDebug
)

mapfile -t APKS < <(find "$UPSTREAM/app/build/outputs/apk/debug" -maxdepth 2 -type f -name '*.apk' -print | sort)
if (( ${#APKS[@]} == 0 )); then
  printf 'ERROR: Gradle finished but no debug APK was found.\n' >&2
  exit 1
fi
printf '\n=== APK artifacts ===\n'
printf '%s\n' "${APKS[@]}"

if [[ "${INSTALL:-0}" == "1" ]]; then
  command -v adb >/dev/null 2>&1 || {
    printf 'ERROR: INSTALL=1 requires adb (Android platform-tools).\n' >&2
    exit 1
  }
  mapfile -t DEVICES < <(adb devices | awk 'NR > 1 && $2 == "device" { print $1 }')
  if (( ${#DEVICES[@]} != 1 )); then
    printf 'ERROR: INSTALL=1 requires exactly one authorized adb device; found %s.\n' "${#DEVICES[@]}" >&2
    adb devices -l
    exit 1
  fi
  APK=""
  for candidate in "${APKS[@]}"; do
    if [[ "$candidate" == *"arm64-v8a"* ]]; then APK="$candidate"; break; fi
  done
  [[ -n "$APK" ]] || APK="${APKS[0]}"
  printf '\n=== Install on connected device %s ===\n' "${DEVICES[0]}"
  adb -s "${DEVICES[0]}" install -r "$APK"
fi
