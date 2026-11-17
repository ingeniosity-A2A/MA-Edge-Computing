# rustunnel between the OVH VPS and the Galaxy S26 Ultra

Reverse-proxy transport for exposing a service running on the phone through the
VPS. Companion to the [AVA-007 Edge Connectivity Runbook](../../../docs/AVA007_EDGE_CONNECTIVITY_RUNBOOK.md)
(§12 bootstrap, §13 provider decision) and to Exoskeleton's
`docs/RUSTUNNEL_TRANSPORT_ARCHITECTURE_AUDIT_2026-11-05.md`.

**Status: not deployed, not tested.** Nothing in this directory has been run on
the VPS or the phone. The commands below are derived from the project's own
documentation (`rustunnel.com/docs`, `joaoh82/rustunnel`, AGPL) and the two
hosts' tailnet console exports; the deployment steps themselves are unmeasured
until someone runs them on the hosts.

## Host facts (from the console exports)

| | VPS | S26 Ultra |
|---|---|---|
| Tailscale name | `vps-73b462c2` | `brianqs-s26-ultra-1` |
| Tailscale IPv4 | `100.91.36.108` | `100.121.129.77` |
| MagicDNS | `vps-73b462c2.tail5f91a8.ts.net` | `brianqs-s26-ultra-1.tail5f91a8.ts.net` |
| OS | Linux `7.0.0-42-generic` (Ubuntu) | Android 17 |
| Tailscale | 1.104.5 | 1.104.6 |
| Public endpoint | `40.160.36.228:41641` | none advertised |
| Role | exit node allowed, no subnet routes | subnets approved, **machine not connected** |
| TLS cert on ts.net name | valid ~3 months | valid |
| Live listeners | `:22` ssh, `:53` resolved, `:443` **tailscaled**, `:6768`, `:54422`, `:58983` | none reported |

Two of these decide the design:

1. **`tailscaled` already owns `100.91.36.108:443`** (Tailscale Serve, valid
   ts.net certificate). A rustunnel server configured with `https_port = 443`
   and a default `0.0.0.0` bind will fail to bind, or silently take the port
   from Serve. Check `ss -tlnp | grep -E ':(443|4040|8443|9090)\b'` on the VPS
   before starting anything.
2. **The phone is currently not connected to the tailnet.** Every plan below
   reaches the control plane over the tailnet, so bringing the phone's Tailscale
   client to `Connected` is step zero, not an afterthought.

## Two topologies — pick one before writing config

### A. Tailnet-only (recommended, matches the runbook and the audit)

The VPS control plane and TCP tunnel ports are reachable only over the tailnet;
nothing new is published to the internet.

- `control_port = 4040` bound to the tailnet interface (or firewalled to
  `100.121.129.77` only, never to `0.0.0.0`).
- `dashboard_port = 8443` on loopback; administer over `ssh -L`.
- `:9090` metrics on loopback, no firewall rule.
- TLS: the VPS already has a valid certificate for
  `vps-73b462c2.tail5f91a8.ts.net` (`tailscale cert`). Point `cert_path` /
  `key_path` at it.
- Client: `server: vps-73b462c2.tail5f91a8.ts.net:4040`.
- **Use `rustunnel tcp <port>`, not `rustunnel http`.** HTTP tunnels route by
  subdomain, which needs a wildcard DNS record; `*.tail5f91a8.ts.net` does not
  exist and cannot be created by us, so `--subdomain` cannot resolve.
- Result: `tcp://vps-73b462c2.tail5f91a8.ts.net:<20000-20099>` reachable only
  from tailnet members.

### B. Public ingress (needs an explicit decision, and a domain)

This is what the pasted instructions assumed. It publishes the phone's service
to the internet and requires all of:

- A domain you control with `A` for the base name and `A *.<base>` pointing at
  the VPS public IP `40.160.36.228`.
- Ports 80/443 open publicly; `4040` open **only** to the tailnet, not the
  internet.
- A real certificate for the base name and its wildcard (Certbot DNS-01, or
  `acme_enabled = true` with a Cloudflare token).
- Resolution of the `:443` conflict above: move Tailscale Serve off 443 or run
  rustunnel's edge on different ports behind the existing listener.
- Acceptance of the audit's gate 2: dashboard, metrics, PostgreSQL and the
  request inspector stay private; only the intended edge listeners are exposed.

Nothing in the repo currently authorizes public exposure of this host. The
runbook's posture is private-endpoint ("Keep the control API on loopback or a
private tailnet interface; do not publish port 8080 to the public internet"),
so variant B should be treated as an operator decision recorded somewhere, not
a default.

## Server (VPS, variant A)

```bash
# 1. Build (as a normal user, not root)
apt update && apt install -y pkg-config libssl-dev curl git build-essential
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh && . "$HOME/.cargo/env"
git clone https://github.com/joaoh82/rustunnel.git && cd rustunnel
cargo build --release -p rustunnel-server -p rustunnel-client

# 2. Service user and directories
sudo useradd --system --no-create-home --shell /usr/sbin/nologin rustunnel
sudo mkdir -p /etc/rustunnel /var/lib/rustunnel
sudo chown rustunnel:rustunnel /var/lib/rustunnel && sudo chmod 750 /var/lib/rustunnel
sudo install -Dm755 target/release/rustunnel-server /usr/local/bin/rustunnel-server

# 3. PostgreSQL — required: tokens, tunnel history and audit log live here
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
sudo -u postgres psql <<'SQL'
CREATE USER rustunnel WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE rustunnel OWNER rustunnel;
GRANT ALL PRIVILEGES ON DATABASE rustunnel TO rustunnel;
SQL
```

`/etc/rustunnel/server.toml` — schema migrations run on first start, no manual SQL:

```toml
[server]
domain           = "vps-73b462c2.tail5f91a8.ts.net"
control_port     = 4040
dashboard_port   = 8443
dashboard_origin = "http://localhost:8443"
# Edge ports are unused in variant A (TCP tunnels only); leave them unset or
# point them at a non-conflicting tailnet port, never 443 while Serve owns it.

[tls]
cert_path = "/etc/rustunnel/tls/fullchain.pem"   # from: tailscale cert ...
key_path  = "/etc/rustunnel/tls/privkey.pem"

[auth]
admin_token  = "<openssl rand -hex 32>"
require_auth = true
max_failed_auth_per_minute = 10

[database]
url           = "postgresql://rustunnel:CHANGE_ME@localhost:5432/rustunnel"
captured_path = "/var/lib/rustunnel/captured.db"

[logging]
level  = "info"
format = "json"
audit_log_path = "/var/lib/rustunnel/audit.log"

[limits]
max_tunnels_per_session    = 2
max_connections_per_tunnel = 50
rate_limit_rps             = 50
ip_rate_limit_rps          = 50
request_body_max_bytes     = 10485760
tcp_port_range             = [20000, 20050]
```

```bash
sudo chown root:rustunnel /etc/rustunnel/server.toml && sudo chmod 640 /etc/rustunnel/server.toml
sudo install -Dm644 deploy/rustunnel.service /etc/systemd/system/rustunnel.service
sudo systemctl daemon-reload && sudo systemctl enable --now rustunnel.service

# 4. Verify — status over loopback only
curl -s http://localhost:8443/api/status
ss -tlnp | grep -E ':(4040|8443|9090|200[0-9][0-9])\b'
journalctl -u rustunnel.service --no-pager | tail -30
```

Firewall (variant A): allow `4040` from `100.121.129.77` only; leave 80/443/8443/9090
closed. `:4040` answers plain HTTP with `HTTP/0.9` — that is the WebSocket
control plane, not a fault.

## Client (S26 Ultra, Termux)

Install Termux from F-Droid or the GitHub release, not Google Play.

```bash
pkg update && pkg upgrade -y
pkg install git rust openssl make clang -y
git clone https://github.com/joaoh82/rustunnel.git && cd rustunnel
cargo build --release -p rustunnel-client      # -j 2 if the build gets killed
install -Dm755 target/release/rustunnel "$PREFIX/bin/rustunnel"
rustunnel --version
```

```bash
rustunnel setup
#   Region [auto / eu / us / ap / self-hosted]: self-hosted
#   Tunnel server address: vps-73b462c2.tail5f91a8.ts.net:4040   <- host:port, not an https URL
#   Auth token: <token from the VPS dashboard>

rustunnel tcp 8022            # SSH on the phone, allocated a port in 20000-20050
rustunnel tcp 8080            # or a local web/API service
```

`rustunnel http <port>` will fail to produce a usable URL here: it needs a
wildcard DNS name under `server.domain`, which variant A does not publish.

Android behaviour that breaks long-lived clients: acquire the Termux wakelock
(notification → Acquire wakelock), set Termux battery usage to Unrestricted, and
expect the phantom-process killer to affect parallel `cargo` builds. Reconnect
is automatic with exponential backoff to ~60 s; auth failure is fatal and needs
a new token.

## Doctrine gates (from Exoskeleton's rustunnel audit)

1. One token per tunnel and purpose; rotate and revoke rather than sharing the
   admin token with a phone.
2. `--insecure` is never valid here — the VPS has a real certificate.
3. Dashboard, metrics, PostgreSQL and the request inspector stay private.
4. Destination services keep their own authorization; a tunnel token is not a
   Tailscale identity and is not an Exoskeleton Grant.
5. Do not expose DuckDB, PostgreSQL, a shell, or privileged device control
   through this path. Publishing Termux SSH (8022) over a public variant-B
   ingress is a remote-shell exposure decision, not a convenience.
6. A tunnel can carry an authorized connection; it cannot make replication
   durable, ordered, or replayable.

## Open decisions

- **Variant A or B.** B needs a domain and an explicit record authorizing public
  ingress from this host.
- **Which local service is the actual target** — `8022` (SSH) or a web/API port
  on the phone. Nothing on the phone is currently reachable to confirm either.
- **Token custody.** The token must come from the VPS dashboard and must not be
  committed, pasted into a chat, or written into this repository.

## Verification still required

- [ ] Phone's Tailscale client reports Connected.
- [ ] `curl vps-73b462c2.tail5f91a8.ts.net:8443/api/status` over tailnet only.
- [ ] `ss` shows 4040/8443 on the intended interfaces, nothing on `0.0.0.0:443`.
- [ ] A token authenticates, and a revoked token is rejected.
- [ ] Tunnel survives phone sleep/wake, cellular↔Wi-Fi change, and a VPS
      `systemctl restart rustunnel`.
- [ ] Dashboard, metrics and PostgreSQL are unreachable from outside the tailnet.
