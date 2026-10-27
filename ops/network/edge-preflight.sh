#!/usr/bin/env bash
# Read-only network preflight for Termux / Android edge nodes.
# Usage: VPS_TAILNET_IP=100.x.y.z ./edge-preflight.sh [health-url]
set -u

section() { printf '\n=== %s ===\n' "$1"; }
run() {
  printf '\n$'
  printf ' %q' "$@"
  printf '\n'
  "$@" 2>&1 || true
}

section "Device"
for prop in ro.product.model ro.build.version.release ro.build.version.sdk; do
  if command -v getprop >/dev/null 2>&1; then printf '%s=' "$prop"; getprop "$prop"; fi
done
uname -a
date -Is 2>/dev/null || date

section "Network interfaces and routes"
if command -v ip >/dev/null 2>&1; then
  run ip -brief address
  run ip route
  run ip -6 route
else
  echo "ip command unavailable"
fi

section "DNS"
if command -v getprop >/dev/null 2>&1; then
  getprop | grep -E '\[net\.dns[0-9]*\]' || true
fi
if command -v nslookup >/dev/null 2>&1; then run nslookup controlplane.tailscale.com; fi
if command -v curl >/dev/null 2>&1; then
  run curl --silent --show-error --location --max-time 8 --output /dev/null --write-out 'HTTPS control-plane reachability: HTTP %{http_code}; remote=%{remote_ip}; time=%{time_total}s\n' https://controlplane.tailscale.com
fi

section "Android Tailscale client boundary"
echo "A Termux CLI is not proof that Android's Tailscale VPN service is active."
echo "Confirm VPN permission, signed-in account, and connected status in the Android client."
if command -v tailscale >/dev/null 2>&1; then
  run tailscale version
  run tailscale status
  run tailscale ip -4
else
  echo "No tailscale CLI found in this shell; inspect the Android VPN client instead."
fi

section "Private VPS reachability"
if [ -n "${VPS_TAILNET_IP:-}" ] && command -v ping >/dev/null 2>&1; then
  run ping -c 3 -W 2 "$VPS_TAILNET_IP"
else
  echo "Set VPS_TAILNET_IP to the verified VPS tailnet IP to test ICMP reachability."
fi
if [ -n "${1:-}" ] && command -v curl >/dev/null 2>&1; then
  run curl --fail --silent --show-error --connect-timeout 4 --max-time 8 "$1"
else
  echo "Optional: pass a private service health URL as the first argument."
fi

section "Result"
echo "This script is diagnostic only: it does not change routes, VPN settings, DNS, eSIM profiles, or firewall rules."
