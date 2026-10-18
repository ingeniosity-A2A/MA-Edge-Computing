#!/usr/bin/env bash
# Stores a Telnyx V2 API key in .env without echoing it.
#
#   ./scripts/set-key.sh
#
# Prompts with hidden input (nothing is printed, nothing lands in shell history
# or scrollback), validates the key against the Telnyx API, and only then writes
# it to .env with mode 600. Other .env values are preserved.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
API_BASE="${TELNYX_API_BASE:-https://api.telnyx.com/v2}"

if [ ! -t 0 ]; then
  echo "set-key.sh needs an interactive terminal: run it yourself from a shell." >&2
  exit 2
fi

printf 'Paste your Telnyx V2 API key (input hidden, then Enter): '
IFS= read -rs KEY || true
printf '\n'

# Trim surrounding whitespace and stray quotes from copy/paste.
KEY="$(printf '%s' "$KEY" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')"

if [ -z "$KEY" ]; then
  echo "No key entered; nothing changed." >&2
  exit 1
fi
if [ "${#KEY}" -lt 20 ]; then
  echo "That does not look like a Telnyx key (${#KEY} chars). Aborting; nothing changed." >&2
  exit 1
fi
case "$KEY" in
  KEY_*) ;;
  *) echo "Warning: Telnyx V2 keys usually start with KEY_. Continuing anyway." >&2 ;;
esac

echo "Checking the key against $API_BASE/balance …"
body="$(mktemp)"; trap 'rm -f "$body"' EXIT
status="$(curl -sS --max-time 25 -o "$body" -w '%{http_code}' \
  -H "Authorization: Bearer $KEY" "$API_BASE/balance" || echo 000)"

if [ "$status" != "200" ]; then
  echo "Telnyx rejected the key (HTTP $status). Nothing was written." >&2
  head -c 300 "$body" >&2; echo >&2
  exit 1
fi

balance="$(sed -n 's/.*"balance":"\([^"]*\)".*/\1/p' "$body")"
currency="$(sed -n 's/.*"currency":"\([^"]*\)".*/\1/p' "$body")"

# Rewrite .env: drop any old key line (commented or not), keep everything else.
tmp="$(mktemp)"
if [ -f "$ENV_FILE" ]; then
  grep -v -E '^[[:space:]]*#?[[:space:]]*TELNYX_API_KEY[[:space:]]*=' "$ENV_FILE" > "$tmp" || true
fi
{
  cat "$tmp"
  printf 'TELNYX_API_KEY=%s\n' "$KEY"
} > "$tmp.new"
rm -f "$tmp"
chmod 600 "$tmp.new"
mv "$tmp.new" "$ENV_FILE"
unset KEY

saved_len="$(sed -n 's/^TELNYX_API_KEY=//p' "$ENV_FILE" | tr -d '\n' | wc -c)"
echo "Saved to $ENV_FILE (mode 600, gitignored). Stored key length: $saved_len chars."
echo "Account balance: ${balance:-?} ${currency:-}"
echo
echo "Now run:  node scripts/telnyx-test-call.mjs --to=+14044481708"
