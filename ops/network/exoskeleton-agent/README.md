# Exoskeleton agent networking

Network topology for the headless GitHub CLI Agent in `ingeniosity-A2A/Exoskeleton`.

It lives here, not in the Exoskeleton repository, because transport and edge
exposure are Edge Computing's concern, alongside the rest of `ops/network/`
(Tailscale install, edge preflight, grants). The Exoskeleton repository keeps
the agent process and nothing network-facing: its `compose.yaml` publishes no
port and defines no network.

## Contents

| File | Role |
|---|---|
| `compose.override.yaml` | bridge network `exoskeleton`, `dev.kiri.domain` labels, published ports 9090/8080, nginx dashboard serving the rendered `INDEX.md` |

## Apply

The override is merged onto the Exoskeleton compose file. `--project-directory`
must point at the Exoskeleton checkout so the dashboard's `./INDEX.md` and
`./Dependencies` mounts resolve there:

```sh
export EXOSKELETON_DIR=/path/to/Exoskeleton
export GH_TOKEN=...            # the base file fails closed without it

docker compose \
  --project-directory "$EXOSKELETON_DIR" \
  -f "$EXOSKELETON_DIR/compose.yaml" \
  -f ops/network/exoskeleton-agent/compose.override.yaml \
  up -d
```

On Kiri the same command works unchanged (`kiri compose` uses the Docker Engine
API); services then answer at:

- `http://agent.exoskeleton.kiri.local` — `/health`, `/status`, `/audit`
- `http://dashboard.exoskeleton.kiri.local` — rendered `INDEX.md`

Override without updating the file: `COMPOSE_FILE` plus
`COMPOSE_PROJECT_DIRECTORY` in the environment, or a `.env` in this directory.

## Scope

Moved here: network definition, hostname/label policy, published ports, the
dashboard service and its mounts.

Stays in Exoskeleton: the agent image and code, the DuckDB index and schema,
`INDEX.md` rendering, `Dependencies/host_profiles/*.yaml` (dependency routing
profiles, not network topology).

## Verification

`docker compose ... config` resolves both files and shows the merge: the agent
gains the `exoskeleton` network, the `dev.kiri.domain` label and the 9090 port;
`dashboard` appears with `depends_on: condition: service_healthy`.

Not verified from the authoring environment: no Docker daemon and no `kiri`
binary were available, so the image was never built and the merged stack was
never started. Treat `up` on Kiri as unmeasured until someone runs it on a host
with a daemon.
