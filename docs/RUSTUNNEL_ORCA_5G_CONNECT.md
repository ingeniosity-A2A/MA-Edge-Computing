# Rustunnel + Tailscale + Orca + 5G connectivity

**Repository:** `ingeniosity-A2A/MA-Edge-Computing`  
**Status:** Integration specification; deployment and live connectivity are not asserted.

## Authority and transport boundaries

- Tailscale grants are the tailnet authorization source of truth.
- Tailscale route advertisement and admin approval inject routes; grants authorize traffic but do not create routes.
- Rustunnel is an application tunnel. It does not replace Tailscale identity, route advertisement, Android cellular service, or modem firmware.
- Orca owns remote agent sessions and mobile pairing. Its pairing link/token is a credential.
- Android cellular data is the 5G/LTE upstream. Tailscale and Rustunnel operate over the IP connectivity Android already has.
- FAPO's hardware-free RAN profile remains a software twin. It is not a 5G gNodeB, modem, or carrier connection.

## Current known endpoints

| Component | Known value | Evidence status |
|---|---|---|
| S26 Ultra tailnet IPv4 | `100.121.129.77` | Admin-console snapshot supplied 2026-11-05 |
| VPS tailnet IPv4 | `100.91.36.108` | Previously reported; re-check before deployment |
| Orca server port | `6768/tcp` | Previously configured; listener and pairing must be re-verified |
| Rustunnel control plane | `4040/tcp` | Upstream documented default |
| Rustunnel HTTPS ingress | `443/tcp` | Upstream documented default |
| Rustunnel TCP forwarding range | `20000-20099/tcp` | Upstream example; configurable |
| RAN profile endpoint | `tcp://vps:9100` | Existing placeholder only; not a verified Rustunnel endpoint |

Do not substitute the historical VPS address or placeholder hostname without checking the current VPS Tailscale state.

## Tailscale grants

The companion file `ops/network/tailscale-grants.json` contains a complete `grants` section for full tailnet mesh access:

- all tailnet sources, including sources on approved subnet routes;
- all tailnet destinations, including approved subnet routes;
- all destination ports and IP protocols (including TCP, UDP, and ICMP).

This is intentionally broad. It is not least-privilege. Use it only if full-mesh access is the explicit policy decision. It does **not** authorize use of an exit node: that requires a separate grant to `autogroup:internet` and the selected exit node must also be advertised and permitted in the admin console and client.

The policy does not advertise routes, approve routes, enable IP forwarding, configure DNS, open host firewalls, or start listeners. Those are separate control planes.

Current S26 Ultra routes supplied by the admin console:
- `172.20.20.0/32` — one host route, not a /24 network.
- `192.168.1.0/24`.

Do not widen the first route to `/24` without confirming that the phone can actually route that network.

## Rustunnel deployment design

Rustunnel upstream documents a self-hosted Ubuntu server with:
- TCP 80 and 443 for HTTP/HTTPS edge traffic;
- TCP 4040 for the control-plane WebSocket;
- TCP 8443 for dashboard/API in the documented example;
- TCP 20000-20099 for the example TCP tunnel range;
- PostgreSQL for shared state and audit data;
- a domain and TLS certificate (the guide uses a wildcard DNS record and Let's Encrypt).

The published self-hosting guide is an **internet-edge deployment**. Do not open these ports publicly merely to make a private phone-to-VPS link work. First decide whether Rustunnel is intended to be:
1. a public ingress service, with DNS/TLS, authentication, rate limits, audit logs, and a reviewed public firewall policy; or
2. a private tailnet-only transport, with listeners bound/restricted to the private interface and tested from tailnet peers.

Do not assume that a public-edge configuration is private just because Tailscale is also installed. Do not put the Rustunnel admin token, database password, or Cloudflare API token in Git.

### Build and verify the Rustunnel binaries

On the Ubuntu VPS, after reviewing upstream source and selecting a deployment mode:

```bash
rustc --version
cargo --version
git clone https://github.com/joaoh82/rustunnel.git
cd rustunnel
cargo build --release -p rustunnel-server -p rustunnel-client
./target/release/rustunnel-server --help
./target/release/rustunnel --help
```

The documented build requires Rust 1.76+ and system dependencies including `pkg-config` and `libssl-dev`. The commands above build and inspect binaries; they do not configure a production service.

Before installation, confirm the exact server config schema for the pinned source revision, choose the domain and bind exposure, create PostgreSQL and secret files, and review the service unit. Never copy sample secrets into the repository.

### Required Rustunnel acceptance tests

- [ ] Server binary version and source commit recorded.
- [ ] Server starts under a dedicated unprivileged service account.
- [ ] PostgreSQL connection and migrations succeed.
- [ ] TLS certificate and hostname validation succeed (if public HTTPS mode).
- [ ] Control-plane WebSocket authentication succeeds.
- [ ] A test HTTP tunnel and a test TCP tunnel pass end-to-end.
- [ ] Unauthorized token is rejected.
- [ ] Tunnel survives client reconnect and server restart.
- [ ] Publicly reachable ports match the selected exposure mode; no dashboard/metrics/admin surface is unintentionally public.
- [ ] Phone-to-VPS test succeeds over cellular data with Tailscale status and path recorded.

## Orca headless server and mobile pairing

The current Orca documentation supports a headless Linux host using `orca serve`. The prior AppImage command should be treated as an older invocation until the installed binary's CLI is checked.

On the VPS, inspect first:

```bash
command -v orca || true
/opt/orca/orca-linux.AppImage --appimage-version 2>&1 || true
/opt/orca/orca-linux.AppImage --help 2>&1 | head -80
/opt/orca/orca-linux.AppImage serve --help 2>&1
sudo ss -ltnp 'sport = :6768'
pgrep -af 'orcad-server.js|orca.*serve' || true
```

If the installed version supports the documented CLI, run one host mode only:

```bash
orca serve --port 6768 --pairing-address 100.91.36.108 --mobile-pairing
```

Pair the phone on the same tailnet by scanning the terminal QR code or pasting the printed mobile pairing link. Treat that link as a password. For persistence, use the documented service commands after validating the installed version:

```bash
orca serve service install --port 6768
orca serve service status
loginctl enable-linger ubuntu
```

Do not start a second `orca serve` if the desktop app is already sharing that same host. Do not expose TCP 6768 to the public internet. Tailscale grants authorize the path; the Orca daemon must still be running and listening.

### Orca acceptance tests

- [ ] Installed Orca version and CLI help captured.
- [ ] Exactly one host mode is active.
- [ ] VPS listener is bound on the intended interface and TCP 6768 is reachable from the S26 over Tailscale.
- [ ] Mobile-scoped pairing QR/link generated by the live server.
- [ ] S26 pairs successfully and lists the host/workspaces.
- [ ] Restart and reconnect test succeeds.
- [ ] No public port-forward exists for 6768.

## 5G Connect: phone uplink → tailnet → service

The S26 Ultra's carrier connection is the upstream. Tailscale must be tested after Android has working cellular data; Rustunnel and Orca are higher-layer services. No software-only component in this repository can replace the Qualcomm modem/baseband, activate a carrier plan, or manufacture a 5G radio connection.

### Device preflight (Termux)

Run on the S26 Ultra while Wi-Fi is disabled and mobile data is enabled:

```bash
echo '=== DEVICE ==='
getprop ro.product.model
getprop ro.build.version.release
getprop ro.build.version.sdk
echo '=== CONNECTIVITY ==='
ip route
echo '=== DNS PROPERTIES ==='
getprop | grep -i 'net.dns'
echo '=== PUBLIC IP REACHABILITY ==='
curl -4 --connect-timeout 5 -sS https://1.1.1.1/cdn-cgi/trace | head
echo '=== TAILSCALE CLI (IF INSTALLED) ==='
command -v tailscale || true
tailscale status 2>&1 || true
```

The public IP test is only a basic IP reachability probe; it is not a carrier 5G proof. Confirm radio technology and registered data network in Android Settings or through permitted Android Telephony APIs. Do not infer 5G solely from a marketing icon or a successful internet request.

### VPS preflight

```bash
echo '=== TAILSCALE ==='
tailscale version
tailscale status
tailscale ip -4
echo '=== ORCA ==='
sudo ss -ltnp 'sport = :6768'
echo '=== RUSTUNNEL ==='
sudo systemctl status rustunnel --no-pager 2>&1 || true
sudo ss -ltnp | grep -E ':(80|443|4040|8443|200[0-9][0-9])\\b' || true
```

### End-to-end acceptance sequence

1. Prove cellular internet works on the phone with Wi-Fi off.
2. Confirm Tailscale reports the S26 and VPS online.
3. From the phone, test `tailscale ping 100.91.36.108` (replace with the freshly checked VPS IP).
4. Test a real TCP service, not ping alone: `nc -vz -w 5 100.91.36.108 6768`.
5. Pair Orca Mobile and verify a live host/session list.
6. Test Rustunnel separately using its authenticated client and a known test service.
7. Toggle Wi-Fi/cellular and verify recovery without changing the grants or route table.
8. Record timestamps, carrier/connection type, Tailscale path (direct/DERP), endpoint, and test results.

A pass at one layer does not imply a pass at another. Mark each layer independently: cellular upstream, tailnet peer, subnet route, Rustunnel control plane, Rustunnel data plane, Orca pairing, and application service.

## Sources

- Rustunnel docs: https://www.rustunnel.com/docs
- Rustunnel quickstart: https://www.rustunnel.com/docs/quickstart
- Rustunnel self-hosting: https://www.rustunnel.com/docs/guides/self-hosting
- Rustunnel architecture: https://www.rustunnel.com/docs/guides/architecture
- Tailscale grants syntax: https://tailscale.com/docs/reference/syntax/grants
- Orca mobile companion: https://www.onorca.dev/docs/mobile
- Orca remote servers: https://www.onorca.dev/docs/remote-servers
- MA Edge Computing 5G/RAN profile: ../packages/csn/ran-5g.yaml
