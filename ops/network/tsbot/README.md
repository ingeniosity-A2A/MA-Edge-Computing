# tsbot — the Tailscale agent, dual mode

One program, two faces:

- `tsbot --daemon` — a watchdog under systemd. Every `TS_INTERVAL` seconds it reads
  `tailscale status --json`, and if the host is running behind an exit node that stops
  answering, it clears that exit node with `tailscale set --exit-node=`. Repairs are JSON
  log lines with the exact undo.
- `tsbot "why can't I reach nas-box"` — plain English, answered by MiMo through an
  OpenRouter-compatible endpoint, with tools that can only run what the allowlist holds.
  `tsbot` alone opens an interactive session; `tsbot --once` prints one health pass as JSON.

**Status: implemented and tested against a stub, not against a live tailnet.** There is no
`tailscale` binary and no tailnet in the environment that built this, so every call below was
exercised with a stub `tailscale` on `PATH` that returns documented-shaped JSON and records the
argv it received. The tailnet behaviour itself is unmeasured until it runs on the VPS or the
phone. What *was* measured is in [Verification](#verification).

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

Everything `tsbot` may execute, printed by `tsbot --allowlist`:

```
status --json · status · netcheck --format=json · netcheck · ip -4 · ip · version
dns status --json · ping * · set --exit-node=* · set --accept-routes[=false]
set --advertise-exit-node[=false] · set --shields-up[=false]
```

Absent by design: `up`, `down`, `logout`, `login`, `serve`, `funnel`, `cert`, `ssh`, `debug`.
The autonomous repair is exactly one of these: `set --exit-node=`.

## Install (VPS, systemd)

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

## Termux / S26 Ultra

There is no systemd on Android, so the unit above does not apply. Termux has `termux-services`, or
plain `nohup tsbot --daemon &` with the wakelock acquired — the same requirement the rustunnel
runbook records, because Android's phantom-process killer will otherwise take the loop. More
importantly, on the phone the **Android Tailscale app owns the VPN**, so a Termux `tailscale` CLI is
not proof the tunnel is up; treat this as a diagnostics and preference surface there, not a healer.

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
  [`../tailnet-policy.hujson`](../tailnet-policy.hujson); `tsbot` reads it only through the
  access it already has.
- No public exposure: no `serve`, `funnel` or `cert` in the allowlist.
- Repairs are reversible and recorded with their undo. Anything that is not reversible is a
  proposal in the log, for the operator.
