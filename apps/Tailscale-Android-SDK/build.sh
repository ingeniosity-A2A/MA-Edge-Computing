#!/usr/bin/env bash
set -Eeuo pipefail

# Builds the upstream Tailscale Android client and libtailscale AAR in an isolated
# workspace. No changes are made to GenieX, NovaDial, or Omni OS.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORK="${TAILSCALE_WORK_DIR:-"$ROOT/.work/tailscale-android"}"
OUT="${TAILSCALE_OUTPUT_DIR:-"$ROOT/dist"}"
REPO="https://github.com/tailscale/tailscale-android.git"

for bin in git make go java; do
  command -v "$bin" >/dev/null 2>&1 || {
    echo "Missing required tool: $bin" >&2
    exit 2
  }
done

mkdir -p "$(dirname "$WORK")" "$OUT"
if [[ ! -d "$WORK/.git" ]]; then
  git clone --depth 1 "$REPO" "$WORK"
else
  git -C "$WORK" fetch --depth 1 origin
  git -C "$WORK" checkout --detach FETCH_HEAD
fi

cd "$WORK"
make androidsdk
make libtailscale
make apk

mkdir -p "$OUT"
install -m 0644 android/libs/libtailscale.aar "$OUT/libtailscale.aar"
install -m 0644 tailscale-debug.apk "$OUT/tailscale-debug.apk"
sha256sum "$OUT/libtailscale.aar" "$OUT/tailscale-debug.apk" | tee "$OUT/SHA256SUMS"
printf '\nArtifacts built successfully:\n  %s\n  %s\n' "$OUT/libtailscale.aar" "$OUT/tailscale-debug.apk"
