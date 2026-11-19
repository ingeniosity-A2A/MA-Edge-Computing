# tsbot — the Tailscale agent, dual mode

One program, two faces, both executing **on the VPS host that owns the local
Tailscale daemon**:

- `tsbot --daemon` — a watchdog under systemd. Every `TS_INTERVAL` seconds it reads
  `tailscale status --json`, and if the host is running behind an exit node that stops
  answering, it clears that exit node with `tailscale set --exit-node=`. Repairs are JSON
  log lines with the exact undo.
- `tsbot "why can't I reach nas-box"` — plain English, answered by MiMo through an
  OpenRouter-compatible endpoint, with tools that can only run what the allowlist holds.
  `tsbot` alone opens an interactive session; `tsbot --once` prints one health pass as JSON.

**Execution placement is host-only.** Install and run the bot on the Ubuntu VPS (or another
Linux host whose local `tailscaled` it is authorized to inspect). Do not install or run
`tsbot` in Termux, Android, or on the S26 Ultra. The bot invokes the local `tailscale`
executable and talks to that host's local `tailscaled` socket; it is not a remote Android
VPN controller and does not migrate onto edge clients.

**Status: implemented and tested against a stub, not against a live tailnet.** There is no
`tailscale` binary and no tailnet in the environment that built this, so every call below was
exercised with a stub `tailscale` on `PATH` that returns documented-shaped JSON and records the
argv it received. The tailnet behaviour itself is unmeasured until it runs on the VPS. What
*was* measured is in [Verification](#verification).

## Edge-computing placement and responsibility boundary

The VPS is the network-control host. Its `tsbot` process monitors and, within its allowlist,
changes only the VPS node's local Tailscale preferences. Set
`TS_WATCH_PEERS=100.121.129.77` (or the verified current S26 MagicDNS name) to probe
the S26 on every watchdog cycle. Probes accept direct or DERP responses and record
the peer, reachability, and transport output in the journal. A failed peer probe is
reported; it does not change the phone, grants, or Rustunnel.

The S26 Ultra is an edge client/sensory node. Android's official Tailscale app owns the
phone's VPN lifecycle, authentication, and network attachment. Termux is a user-space
environment for diagnostics and client-side applications; a standalone `tailscale`
binary in Termux does not prove that Android's VPN is connected and must not be treated
as the owner of that VPN.

If the phone-side Tailscale connection is down, `tsbot` can report that the VPS cannot
reach the peer and provide evidence, but it cannot remotely execute Android VPN actions
such as sign-in, reconnect, or changing the phone's VPN settings. Those actions require
the Android client/user flow or a separately designed, explicitly authorized Android
management integration.

Rustunnel is a separate transport/client service that may provide an additional path for
phone-hosted services. It does not change `tsbot`'s host-only execution placement and is
not currently invoked or managed by this bot. Nginx or another reverse proxy is an
application-ingress component, not a substitute for the Android VPN owner or the VPS
Tailscale daemon.

## Why this is not the plan it replaces

The generated plan this replaces would have run `tailscale up --accept-routes --authkey=…` on a
timer, decided the exit node was broken by pinging `1.1.1.1` with ICMP, and put the OpenAI key
inline in the systemd unit. Four of those do not hold up:

| The plan | What this does | Why |
|---|---|---|
| `tailscale up` autonomously, with a reusable auth key in the unit | Never. `up`, `down`, `logout`, `login` are not in the allowlist, so no code path can run them; the daemon logs the exact operator command instead | `up` rewrites the node's whole preference set, and a reusable `tskey-auth-` in a unit file is a credential that outlives the fix. This repo's own rule, in `MiMo-Agent/workorder.ts`, is that connectivity-breaking commands are never on an allowlist |
| Health = `ping 1.1.1.1` | `tailscale ping --until-direct=false -c 2 --timeout=3s <exit node IP>` | ICMP to a public resolver tests the internet, not the tunnel, and many hosts drop ICMP. `--until-direct=false` is essential: it defaults to true, and a healthy exit node reached over DERP would then exit non-zero and look like an outage |
| One failed probe clears the route | Two consecutive failures, then at most one repair per `TS_COOLDOWN` (default 600 s) | A single dropped packet should not change where all traffic goes |
| `OpenAI` + `gpt-4o-mini` | MiMo (`TS_MODEL`, default `xiaomi/mimo-v2.6-pro`) over OpenRouter, stdlib `urllib` only | This estate runs MiMo. No `pip install` and no SDK are needed, so the unit has no Python dependency to drift |
| Errors swallowed into a log file | JSON lines to stdout (journal) plus optional `TS_LOG`; an unwritable log is reported, not hidden | Measurement stays separate from the report |
| `manage_exit_node` / `configure_node` free-form | Each tool builds its own argv from validated parameters, then the argv is checked against the allowlist again | Two independent checks, and `--exit-node=` gets a hostname or `100.x` address, never a stable node id |

## Allowlist

The command boundary allows the exact read-only probes plus validated parameterized `ping` and `set` forms:

```
status --json · status · netcheck --format=json · netcheck · ip -4 · ip · version
dns status --json · ping --until-direct=false -c 2 --timeout=3s <validated-node>
set --exit-node=<empty-or-validated-node>
set --accept-routes=true|false · set --advertise-exit-node=true|false · set --shields-up=true|false
```

Absent by design: `up`, `down`, `logout`, `login`, `serve`, `funnel`, `cert`, `ssh`, `debug`.
The autonomous repair is exactly one of these: `set --exit-node=`.

## Install (VPS, systemd)

Run these commands on the Ubuntu VPS, not on the S26:

```bash
sudo install -Dm755 tsbot.py /usr/local/bin/tsbot
sudo install -Dm644 tsbot.service /etc/systemd/system/tsbot.service
sudo install -d -m750 /etc/tsbot
sudo install -d -m750 /var/log
# Key and model go here, never in the unit file:
sudo install -m600 /dev/null /etc/tsbot/tsbot.env
sudo tee /etc/tsbot/tsbot.env >/dev/null <<'EOF'
OPENROUTER_API=sk-or-...
TS_MODEL=xiaomi/mimo-v2.6-pro
TS_WATCH_PEERS=100.121.129.77
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now tsbot
journalctl -u tsbot -f --output=cat
```

Ask it something, or take a health pass:

```bash
tsbot "what did you fix while I was away"     # reads the repair log
tsbot --once                                  # one JSON health pass, exit 1 if not Running
sudo TS_DRY_RUN=1 tsbot --daemon              # decide, log, change nothing
```

`tsbot --daemon` holds an exclusive lock in `TS_STATE_DIR` (default `/var/lib/tsbot`), so a second
instance exits 3 instead of racing the first. `ProtectSystem=strict` in the unit means only
`/var/lib/tsbot` and `/var/log` are writable.

## S26 Ultra / Termux boundary

**There is no S26/Termux installation procedure for tsbot.** Do not run the daemon on
Android. Use the repository's `edge-preflight.sh` and phone-side checks to collect
diagnostics, and use the Android Tailscale app to confirm VPN permission, sign-in, and
Connected status. A Termux `tailscale` executable, if present, is not proof that the
Android VPN service is active.

The supported control direction is:

```text
Ubuntu VPS host
  ├─ tailscaled + tailscale CLI
  └─ tsbot (local host watchdog and operator assistant)
       └─ observes S26 as a tailnet peer; does not administer Android VPN

S26 Ultra
  ├─ Android Tailscale app (owns VPN lifecycle)
  └─ Termux (edge diagnostics and client-side services)
```

## Verification

Measured with a stub `tailscale` on `PATH` (recorded argv, canned `status --json`), 2026-11-17:

- `--once` on a healthy node → `backend_state: Running`, exit node and peer counts parsed, rc 0.
- Exit node unreachable, 2 cycles → `exit node probe failed` (failures 1), then
  `cleared unresponsive exit node` with `undo: tailscale set --exit-node=100.9.9.9`; argv seen:
  `status --json`, `ping --until-direct=false -c 2 --timeout=3s 100.9.9.9`, `set --exit-node=`.
- One extra cycle inside the cooldown → `repair suppressed by cooldown`, no second `set`.
- `BackendState: NeedsLogin` → only `status --json` executed, proposal logged with the auth URL,
  nothing brought up.
- Natural language, MiMo `xiaomi/mimo-v2.6-pro`: "why can't I reach nas-box" called
  `tailnet_status` and `tailnet_ping nas-box`; "bring it back up and log me in" executed no tool
  that changes state and named the operator command. Zero `up`/`login` argv reached the stub.
- `python3 -m py_compile` clean; no third-party imports.

Not measured: a real `tailscale`, a real exit node, DERP vs direct paths, `netcheck` output
parsing at scale, and behaviour when `tailscaled` is stopped rather than logged out (the daemon
treats an unparseable `status --json` as "not observable" and proposes `tailscale up`).

## Doctrine

- A tailnet identity is not an authorization: `tailscale set` changes this device's preferences,
  and nothing here writes the ACL policy. The policy lives in
  [`../tailnet-policy.hujson`](../tailnet-policy.hujson) and is changed by
  [`../tsgrant`](../tsgrant), which is a separate program precisely so this daemon cannot
  rewrite access while it runs unattended; `tsbot` reads the policy only through the access
  it already has.
- No public exposure: no `serve`, `funnel` or `cert` in the allowlist.
- Repairs are reversible and recorded with their undo. Anything that is not reversible is a
  proposal in the log, for the operator.
