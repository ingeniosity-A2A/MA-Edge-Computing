# tsgrant — the tailnet policy file, edited on purpose

`tsgrant.py` reads, validates and writes the tailnet policy file through the
Tailscale API. It is a separate program from [`../tsbot`](../tsbot) on purpose:
`tsbot` runs unattended as root and cannot reach `tailscale up`, `down` or
`login`, and code that can rewrite every access rule in the tailnet does not
belong inside it. A prompt injection or a bad model answer must not be able to
widen the tailnet while nobody is watching, so `tsgrant` writes only when a
person passes `--apply`.

```bash
tsgrant show                      # live policy + ETag
tsgrant check                     # validate the live policy, write nothing
tsgrant add '{"src": ["s26-ultra"], "dst": ["vps"], "ip": ["tcp:8080"]}'
tsgrant add '…' --apply           # validate, snapshot, write with If-Match
tsgrant remove 3 --apply          # 1-based index into the grants array
tsgrant undo --apply              # restore the newest snapshot
tsgrant "let the phone reach the vps on 8080"   # draft, then dry run
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `TS_API_KEY` | `tskey-api-…` access token; used as Basic auth with an empty password |
| `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_CLIENT_SECRET` | OAuth client instead of a token; exchanges for a bearer token per run |
| `TS_OAUTH_SCOPES` | requested scope, default `policy_file` |
| `TS_TAILNET` | tailnet name, default `-` (the token's own) |
| `TS_SNAPSHOT_DIR` | where `undo` snapshots are kept, default `/var/lib/tsgrant` |
| `TS_GUARD_DST` / `TS_GUARD_IP` | the path that must survive an edit, default `vps` / `tcp:22` |
| `OPENROUTER_API`, `TS_MODEL`, `TS_LLM_BASE` | only for the plain-English mode |

Scopes, from Tailscale's own docs: `policy_file:read` covers `GET /acl`,
`/acl/preview` and `/acl/validate`; `policy_file` additionally covers
`POST /acl`. An OAuth client with `policy_file` also needs
`devices:core:read` and `devices:posture_attributes` for these calls. A user
access token carries the permissions of the user who made it.

## What it does about the ways a policy change goes wrong

| Failure | What `tsgrant` does |
| --- | --- |
| Someone else edited the policy after you read it | reads the `ETag`, sends `If-Match`; a stale write returns 412 and nothing is written |
| The candidate does not parse, or names a tag/group/alias that does not exist | sends the whole candidate to `POST /acl/validate` first; a refusal stops the run |
| The edit removes your own way in | refuses when no grant is left for `TS_GUARD_IP` to `TS_GUARD_DST`; `--force` overrides after printing why |
| A change needs undoing | saves the previous policy text before every write; `undo` posts it back verbatim |
| Comments, ordering or one-line grants get flattened | the edit is an insertion or deletion in the HuJSON text, never a re-serialisation of a parsed dict |
| The same request twice | an identical grant (same keys, same values) is detected and reported as nothing to do, exit 3 |

Grants are additive: no rule can narrow another. That is why `remove` exists —
appending grants can only ever widen access, so "is anything too permissive"
is answered by reading `show` and removing rules, not by adding one.

## Corrections to the generated design this replaces

The pasted `tsgrant-bot` could not have worked as written. Each row is a defect
in that code, not a matter of taste:

| In the pasted script | Result |
| --- | --- |
| `f"https://tailscale.com{TS_TAILNET}/{endpoint}"` | with the default tailnet `-` the URL is `https://tailscale.com-/acl`; the API lives at `https://api.tailscale.com/api/v2/tailnet/{tailnet}/acl` |
| `response.choices.message` | `choices` is a list; every answer raises `AttributeError` |
| `json.loads()` on the `GET /acl` body | the policy file is HuJSON; comments make it unparsable, so the "live state" step returns an error dict instead of the policy |
| `json.dumps(...)[:8000]` | truncates the policy mid-object before handing it to the model, which then writes against half a file |
| no `If-Match` | documentedly silent lost updates when the console or another tool writes between read and write |
| `replace_all_grants` chosen by the model | one tool call replaces the whole tailnet policy |
| append-only, no dedupe, no removal | repeated requests grow the file forever, and nothing can ever be narrowed |
| `ping 1.1.1.1` for exit-node health | tests the internet, not the tunnel; a healthy DERP-relayed exit node fails it |
| autonomous `tailscale up --authkey=…` | a connectivity action taken without a person, with a reusable credential on disk |
| `http://localhost:8080/v1`, key `aperture-tailscale-auth`, `gpt-4o-mini` | a gateway that this estate has no measured endpoint for, a placeholder credential, and a model that is not the estate's |
| tools without `parameters` | the two zero-argument tools have no schema, which strict endpoints reject |

What the pasted design got right is the shape of the idea: fetch live state,
validate before writing, and keep the watchdog for node health. `tsgrant`
keeps the first two and leaves the third to `tsbot`.

## Measured, and how

There is no tailnet and no API key in this workspace, so `tsgrant` was measured
against a local stub that mirrors the documented API shapes: `GET /acl` with an
`ETag`, `POST /acl` honouring `If-Match`, `POST /acl/validate` returning `{}` or
a 400 with `message`/`data`. The stub is not in the repository; it was a
throwaway in `/tmp`.

| Case | Result |
| --- | --- |
| `show`, `check` on a valid policy | exit 0, policy printed, `valid: True {}` |
| `add` without `--apply` | diff printed, "dry run", live policy byte-identical afterwards |
| `add --apply` | written with `If-Match`, ETag advanced, comments and one-line grants preserved, snapshot saved |
| `add` the same grant again | exit 3, nothing written |
| `remove` the only grant carrying `tcp:22` to `vps` | exit 4 from the lockout guard, live policy byte-identical |
| the same removal with `--force` | written, guard override printed |
| concurrent edit between read and write (stub returns 412) | exit 2, "policy changed since it was read", nothing written, snapshot kept |
| candidate naming `tag:unknown` | exit 2 with Tailscale's own error body, nothing written |
| `undo --apply` | policy restored byte for byte (sha1 compared before and after) |
| policy with no `grants` key, only `acls` | `grants` array created at the top level, valid JSON, comments untouched |
| policy with an empty `grants` array | grant inserted as the first element |
| plain English: "let the phone reach the vps on 8080" | MiMo drafted `{"src": ["s26-ultra"], "dst": ["vps"], "ip": ["tcp:8080"]}`, validated, dry run |

Not measured: a real tailnet, a real API key or OAuth exchange, Tailscale's
actual validator messages, and anything to do with `via`, `app` capabilities or
policy `tests` — `tsgrant` neither writes nor checks those fields.

## Keeping the repository honest

[`../tailnet-policy.hujson`](../tailnet-policy.hujson) is the reviewed desired
state for this estate. Once `tsgrant` is used against the live tailnet, that
file is a stale copy until it is refreshed:

```bash
tsgrant show > ops/network/tailnet-policy.hujson   # then review and commit the diff
```

Committing the exported file is the change log; `tsgrant` does not write into
the repository itself.
