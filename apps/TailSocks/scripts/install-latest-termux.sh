#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Download the upstream TailSocks ARM64 release, verify GitHub's published
# SHA-256 asset digest, and open Android's package installer. Does not rebuild
# the Android SDK, compile TailSocks, or install silently.
for cmd in curl python3 sha256sum termux-open; do
  command -v "$cmd" >/dev/null 2>&1 || {
    printf 'ERROR: required Termux command missing: %s\n' "$cmd" >&2
    exit 1
  }
done

API_JSON="$(curl -fsSL -H 'Accept: application/vnd.github+json' \
  https://api.github.com/repos/bropines/tailsocks/releases/latest)"

mapfile -t RELEASE < <(printf '%s' "$API_JSON" | python3 -c '
import json, sys
release = json.load(sys.stdin)
assets = release.get("assets", [])
matches = [a for a in assets if a.get("name", "").endswith("-arm64-v8a-release.apk")]
if len(matches) != 1:
    raise SystemExit("Expected exactly one ARM64 release APK")
asset = matches[0]
digest = asset.get("digest", "")
if not digest.startswith("sha256:"):
    raise SystemExit("GitHub release does not publish a SHA-256 asset digest")
print(release["tag_name"])
print(asset["name"])
print(asset["browser_download_url"])
print(digest.removeprefix("sha256:"))
print(asset["size"])
')

if (( ${#RELEASE[@]} != 5 )); then
  printf 'ERROR: could not parse verified ARM64 release metadata.\n' >&2
  exit 1
fi

TAG="${RELEASE[0]}"
NAME="${RELEASE[1]}"
URL="${RELEASE[2]}"
EXPECTED_SHA="${RELEASE[3]}"
EXPECTED_SIZE="${RELEASE[4]}"
OUT_DIR="$HOME/downloads"
APK="$OUT_DIR/$NAME"
TMP="$APK.part"

mkdir -p "$OUT_DIR"
rm -f "$TMP"
printf 'Downloading TailSocks %s for ARM64...\n' "$TAG"
curl --fail --location --retry 3 --output "$TMP" "$URL"

ACTUAL_SIZE="$(wc -c < "$TMP" | tr -d ' ')"
if [[ "$ACTUAL_SIZE" != "$EXPECTED_SIZE" ]]; then
  rm -f "$TMP"
  printf 'ERROR: APK size mismatch (expected %s, got %s).\n' "$EXPECTED_SIZE" "$ACTUAL_SIZE" >&2
  exit 1
fi

ACTUAL_SHA="$(sha256sum "$TMP" | awk '{print $1}')"
if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  rm -f "$TMP"
  printf 'ERROR: APK SHA-256 mismatch; refusing to open installer.\n' >&2
  exit 1
fi

mv "$TMP" "$APK"
printf 'Verified: %s\nSHA-256: %s\n' "$APK" "$ACTUAL_SHA"
printf 'Opening Android package installer. Approve installation on the phone.\n'
termux-open "$APK"
