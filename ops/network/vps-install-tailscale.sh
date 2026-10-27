#!/usr/bin/env bash
# Install/start the official Tailscale Linux package on Ubuntu.
# This intentionally does NOT authenticate the node, enable forwarding, advertise
# an exit node, alter firewall rules, or expose services.
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [[ ! -r /etc/os-release ]]; then
  echo "Cannot identify OS: /etc/os-release missing." >&2
  exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "Unsupported OS ID='${ID:-unknown}'. This bootstrap currently targets Ubuntu only." >&2
  exit 1
fi

echo "== Pre-install state =="
printf 'OS: %s\n' "${PRETTY_NAME:-Ubuntu}"
uname -m
if command -v tailscale >/dev/null 2>&1; then
  tailscale version || true
  echo "Tailscale is already installed; leaving package state unchanged."
else
  command -v curl >/dev/null 2>&1 || { apt-get update; apt-get install -y curl; }
  echo "Installing from the official Tailscale Linux package bootstrap."
  curl -fsSL https://tailscale.com/install.sh | sh
fi

systemctl enable --now tailscaled
echo
echo "== Service state =="
systemctl --no-pager --full status tailscaled || true
echo
echo "== Tailscale state =="
tailscale status || true
tailscale ip -4 || true
echo
cat <<'NEXT'
NEXT STEP (interactive; run only after reviewing the target tailnet):
  sudo tailscale up

Authenticate using the URL shown by Tailscale. Do not paste auth keys into
shell history or commit them. Then confirm the VPS appears in the correct
tailnet and record its current 100.x tailnet IP.

This script does NOT enable exit-node routing, IP forwarding, subnet routes,
or public service ports. Do not expose OpenSandbox until authentication,
tailnet reachability, and service authorization have been verified.
NEXT
