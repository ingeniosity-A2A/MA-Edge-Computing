#!/usr/bin/env python3
"""tsgrant: draft, validate and apply the tailnet policy file.

    tsgrant show                     print the live policy file and its ETag
    tsgrant check                    validate the live policy, change nothing
    tsgrant add '<grant json>'       add one grant (dry run unless --apply)
    tsgrant remove <n>               remove grant n (dry run unless --apply)
    tsgrant undo                     restore the newest local snapshot

    tsgrant "let the phone reach the vps on 8080"
                                     draft a grant from plain English

Why this is not part of tsbot: tsbot's daemon runs unattended as root and is
built so that it cannot reach `tailscale up`, `down` or `login`. Code that
rewrites the whole tailnet's access rules belongs in a different program, run
by a person, so a prompt injection or a bad model answer can never widen the
tailnet on its own. `add` and `remove` do nothing without `--apply`.

What this does about the ways policy changes go wrong:

  * ETag / If-Match   a write is rejected with 412 if anyone else edited the
                      policy since it was read, instead of silently overwriting.
  * /acl/validate     the candidate goes to Tailscale's validator before it is
                      written; a policy that does not parse never reaches the
                      tailnet.
  * snapshot          the previous policy text is saved before every write, so
                      `undo` restores it byte for byte.
  * lockout guard     a change that leaves no grant for operator SSH to the
                      guarded host is refused unless --force is given.
  * text surgery      the edit is an insertion or deletion in the HuJSON text,
                      so comments, ordering and formatting survive; the file is
                      never re-serialised from a parsed dict.

Configuration (environment):
    TS_API_KEY          tskey-api-… access token (user scoped)
    TS_OAUTH_CLIENT_ID  …or an OAuth client with the policy_file scope
    TS_OAUTH_CLIENT_SECRET
    TS_OAUTH_SCOPES     requested scope          (default policy_file)
    TS_TAILNET          tailnet name             (default -, the key's own)
    TS_API_BASE         API root (default https://api.tailscale.com/api/v2)
    TS_SNAPSHOT_DIR     where undo snapshots go  (default /var/lib/tsgrant)
    TS_GUARD_DST        host whose SSH must survive edits (default vps)
    TS_GUARD_IP         port that must survive  (default tcp:22)
    OPENROUTER_API      needed only for the plain-English mode
    TS_MODEL            model id (default xiaomi/mimo-v2.6-pro)
    TS_LLM_BASE         model API root (default https://openrouter.ai/api/v1)

Exit codes: 0 ok · 1 usage or configuration · 2 refused (invalid policy, 412,
failed validation) · 3 nothing to do (the grant already exists) · 4 refused by
the lockout guard.
"""

from __future__ import annotations

import base64
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = os.getenv("TS_API_BASE", "https://api.tailscale.com/api/v2").rstrip("/")
TAILNET = os.getenv("TS_TAILNET", "-")
API_KEY = os.getenv("TS_API_KEY", "")
CLIENT_ID = os.getenv("TS_OAUTH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("TS_OAUTH_CLIENT_SECRET", "")
SCOPES = os.getenv("TS_OAUTH_SCOPES", "policy_file")
SNAPSHOT_DIR = Path(os.getenv("TS_SNAPSHOT_DIR", "/var/lib/tsgrant"))
GUARD_DST = os.getenv("TS_GUARD_DST", "vps")
GUARD_IPS = {"tcp:22", "22", "*"}

MODEL = os.getenv("TS_MODEL", "xiaomi/mimo-v2.6-pro")
LLM_BASE = os.getenv("TS_LLM_BASE", "https://openrouter.ai/api/v1").rstrip("/")
LLM_KEY = os.getenv("OPENROUTER_API") or os.getenv("OPENROUTER_API_KEY") or ""

_AUTH: str | None = None


# ---------- auth ----------
def auth_header() -> str:
    """Basic auth with the token as username, or an OAuth-exchanged bearer."""
    global _AUTH
    if _AUTH:
        return _AUTH
    if API_KEY:
        _AUTH = "Basic " + base64.b64encode(f"{API_KEY}:".encode()).decode()
        return _AUTH
    if CLIENT_ID and CLIENT_SECRET:
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPES}).encode()
        request = urllib.request.Request(f"{API_BASE}/oauth/token", data=body, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        request.add_header(
            "Authorization",
            "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode(),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                token = json.load(response).get("access_token")
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"oauth token request failed: HTTP {exc.code}: "
                             f"{exc.read().decode('utf-8', 'replace')[:300]}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"oauth token request failed: {exc.reason}") from exc
        if not token:
            raise SystemExit("oauth token request returned no access_token")
        _AUTH = f"Bearer {token}"
        return _AUTH
    raise SystemExit("set TS_API_KEY (tskey-api-…) or TS_OAUTH_CLIENT_ID/TS_OAUTH_CLIENT_SECRET")


# ---------- api ----------
def api(method: str, path: str, body: str | None = None, headers: dict | None = None) -> tuple[int, dict, str]:
    url = f"{API_BASE}/{path.lstrip('/')}"
    data = body.encode("utf-8") if isinstance(body, str) else None
    request = urllib.request.Request(url, data=data, method=method)
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    if data is not None and not any(k.lower() == "content-type" for k in (headers or {})):
        request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", auth_header())
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        return 0, {}, f"connection failed: {exc.reason}"


def acl_path() -> str:
    return f"tailnet/{TAILNET}/acl"


def get_policy() -> tuple[str, str]:
    status, headers, body = api("GET", acl_path(), headers={"Accept": "application/hujson"})
    if status != 200:
        raise SystemExit(f"get policy failed: HTTP {status}: {body[:300]}")
    etag = next((v for k, v in headers.items() if k.lower() == "etag"), "")
    return body, etag


def validate_policy(text: str) -> tuple[bool, str]:
    status, _, body = api("POST", f"{acl_path()}/validate", body=text,
                          headers={"Content-Type": "application/hujson"})
    if status == 200:
        return True, body.strip() or "{}"
    return False, f"HTTP {status}: {body.strip()[:600]}"


def put_policy(text: str, etag: str) -> tuple[int, str, str]:
    headers = {"Content-Type": "application/hujson", "Accept": "application/hujson"}
    if etag:
        headers["If-Match"] = etag if etag.startswith('"') else f'"{etag}"'
    status, response_headers, body = api("POST", acl_path(), body=text, headers=headers)
    new_etag = next((v for k, v in response_headers.items() if k.lower() == "etag"), "")
    return status, new_etag, body


# ---------- HuJSON scanning ----------
def _skip_gap(text: str, i: int) -> int:
    """Advance past whitespace, // comments and /* */ comments."""
    n = len(text)
    while i < n:
        char = text[i]
        if char in " \t\r\n":
            i += 1
        elif text.startswith("//", i):
            newline = text.find("\n", i)
            i = n if newline < 0 else newline + 1
        elif text.startswith("/*", i):
            close = text.find("*/", i + 2)
            i = n if close < 0 else close + 2
        else:
            break
    return i


def _string_end(text: str, i: int) -> int:
    """i points at an opening quote; return the index just past the closing one."""
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return len(text)


def _matching(text: str, i: int) -> int:
    """i points at '[' or '{'; return the index of the matching closer."""
    opener = text[i]
    closer = "]" if opener == "[" else "}"
    depth = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            i = _string_end(text, i)
            continue
        if text.startswith("//", i) or text.startswith("/*", i):
            i = _skip_gap(text, i)
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text) - 1


def locate_grants(text: str) -> tuple[int, int, list[tuple[int, int]]] | None:
    """Find the top-level "grants" array: (open bracket, close bracket, objects)."""
    depth = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            end = _string_end(text, i)
            if depth == 1:
                name = text[i + 1:end - 1]
                after = _skip_gap(text, end)
                if name == "grants" and after < len(text) and text[after] == ":":
                    value = _skip_gap(text, after + 1)
                    if value < len(text) and text[value] == "[":
                        return value, _matching(text, value), _objects(text, value)
            i = end
            continue
        if text.startswith("//", i) or text.startswith("/*", i):
            i = _skip_gap(text, i)
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        i += 1
    return None


def _objects(text: str, open_bracket: int) -> list[tuple[int, int]]:
    """Spans of the objects directly inside the array that starts at open_bracket."""
    spans: list[tuple[int, int]] = []
    i = open_bracket + 1
    while i < len(text):
        i = _skip_gap(text, i)
        if i >= len(text) or text[i] == "]":
            break
        if text[i] == "{":
            end = _matching(text, i)
            spans.append((i, end + 1))
            i = end + 1
            continue
        i += 1
    return spans


def _indent(grant_json: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in grant_json.splitlines())


def insert_grant(text: str, grant_json: str) -> tuple[str, int]:
    """Insert one grant object after the last element, leaving the rest untouched.

    Inserting here rather than before the closing bracket keeps whatever
    whitespace and comments the author left around that bracket, so the diff of
    a one-grant change is one grant wide.
    """
    element = _indent(grant_json)
    found = locate_grants(text)
    if found is None:
        root = _skip_gap(text, 0)
        if root >= len(text) or text[root] != "{":
            raise SystemExit("policy file does not start with a JSON object; refusing to edit")
        close = _matching(text, root)
        comma = "," if _skip_gap(text[root + 1:close], 0) < len(text[root + 1:close]) else ""
        block = f'{comma}\n  "grants": [\n{element}\n  ]'
        return text[:close].rstrip() + block + text[close:], 0
    open_bracket, _, spans = found
    if not spans:
        return text[:open_bracket + 1] + "\n" + element + "\n  " + text[open_bracket + 1:], 0
    last_end = spans[-1][1]
    return text[:last_end] + ",\n" + element + text[last_end:], len(spans)


def remove_grant(text: str, index: int) -> str:
    found = locate_grants(text)
    if found is None:
        raise SystemExit("policy file has no grants array")
    _, _, spans = found
    if not spans:
        raise SystemExit("policy file has no grants to remove")
    if not 1 <= index <= len(spans):
        raise SystemExit(f"grant index {index} out of range 1..{len(spans)}")
    start, end = spans[index - 1]
    if index < len(spans):
        return text[:start] + text[spans[index][0]:]
    if index > 1:
        return text[:spans[index - 2][1]] + text[end:]
    return text[:start] + text[end:]


def to_json(text: str) -> dict:
    """Parse HuJSON into a dict: strip comments, then tolerate trailing commas."""
    out: list[str] = []
    i, quoted = 0, False
    while i < len(text):
        char = text[i]
        if quoted:
            out.append(char)
            if char == "\\":
                out.append(text[i + 1])
                i += 2
                continue
            if char == '"':
                quoted = False
            i += 1
            continue
        if char == '"':
            quoted = True
            out.append(char)
            i += 1
            continue
        if text.startswith("//", i) or text.startswith("/*", i):
            i = _skip_gap(text, i)
            continue
        out.append(char)
        i += 1
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    return json.loads(cleaned)


# ---------- guards ----------
def grant_problem(grant) -> str:
    if not isinstance(grant, dict):
        return "grant must be a JSON object"
    for field in ("src", "dst"):
        value = grant.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
            return f"grant needs {field} as a non-empty array of strings"
    if "ip" not in grant and "app" not in grant:
        return "grant needs an ip array, an app map, or both"
    if "ip" in grant and (not isinstance(grant["ip"], list) or not all(isinstance(x, str) for x in grant["ip"])):
        return "ip must be an array of strings such as tcp:22"
    if "app" in grant and not isinstance(grant["app"], dict):
        return "app must be an object"
    return ""


def same_grant(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def ssh_guard(policy_text: str) -> tuple[bool, str]:
    """A policy edit must not remove the last path for operator SSH to GUARD_DST."""
    try:
        policy = to_json(policy_text)
    except (ValueError, json.JSONDecodeError) as exc:
        return False, f"candidate policy is not parseable ({exc}); cannot prove SSH survives"
    hosts = policy.get("hosts") or {}
    targets = {GUARD_DST}
    if isinstance(hosts.get(GUARD_DST), str):
        targets.add(hosts[GUARD_DST])
    for grant in policy.get("grants") or []:
        if not isinstance(grant, dict):
            continue
        destinations = grant.get("dst") or []
        if not any(d in targets for d in destinations if isinstance(d, str)):
            continue
        if any(port in GUARD_IPS for port in grant.get("ip") or []):
            return True, ""
    return False, f"no grant left for tcp:22 to {GUARD_DST}; that can lock you out"


def diff(before: str, after: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        fromfile="live", tofile="candidate", n=3))


# ---------- snapshots ----------
def snapshot(text: str, operation: str) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = SNAPSHOT_DIR / f"policy-{stamp}-{operation}.hujson"
    path.write_text(text, encoding="utf-8")
    return path


def newest_snapshot() -> Path:
    if not SNAPSHOT_DIR.exists():
        raise SystemExit(f"no snapshots in {SNAPSHOT_DIR}")
    files = sorted(SNAPSHOT_DIR.glob("policy-*.hujson"))
    if not files:
        raise SystemExit(f"no snapshots in {SNAPSHOT_DIR}")
    return files[-1]


# ---------- commands ----------
def cmd_show() -> int:
    text, etag = get_policy()
    print(text.rstrip("\n"))
    print(f"\n# etag {etag or '(none returned)'}", file=sys.stderr)
    return 0


def cmd_check() -> int:
    text, _ = get_policy()
    ok, detail = validate_policy(text)
    print(f"valid: {ok}\n{detail}")
    return 0 if ok else 2


def apply_change(before: str, after: str, operation: str, etag: str, do_apply: bool, force: bool) -> int:
    print(diff(before, after) or "(no textual change)")

    try:
        current_grants = to_json(before).get("grants") or []
    except Exception:
        current_grants = []

    ok, detail = validate_policy(after)
    if not ok:
        print(f"\nvalidation refused the candidate, nothing written:\n{detail}", file=sys.stderr)
        return 2
    print(f"\nvalidation: ok {detail}")

    safe, why = ssh_guard(after)
    if not safe and not force:
        print(f"\nlockout guard refused the candidate: {why}\n"
              f"(override with --force only if you have another way into {GUARD_DST})", file=sys.stderr)
        return 4
    if not safe:
        print(f"\nlockout guard: overridden by --force ({why})", file=sys.stderr)

    if len(current_grants) > 200:
        print(f"\nnote: the policy already has {len(current_grants)} grants; grants are additive, "
              f"so this edit cannot narrow anything another grant allows", file=sys.stderr)

    if not do_apply:
        print("\ndry run: nothing written. Re-run with --apply to write this policy.")
        return 0

    saved = snapshot(before, operation)
    status, new_etag, body = put_policy(after, etag)
    if status == 412:
        print(f"\npolicy changed since it was read (HTTP 412); nothing written.\n"
              f"Re-run to pick up the new policy. Snapshot kept at {saved}", file=sys.stderr)
        return 2
    if status != 200:
        print(f"\nwrite failed: HTTP {status}: {body[:400]}\nSnapshot kept at {saved}", file=sys.stderr)
        return 2
    print(f"\napplied. new etag: {new_etag or '(none returned)'}\nprevious policy saved: {saved}\n"
          f"undo: tsgrant undo --apply")
    return 0


def cmd_add(raw: str, do_apply: bool, force: bool) -> int:
    try:
        grant = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"grant is not JSON: {exc}") from exc
    problem = grant_problem(grant)
    if problem:
        raise SystemExit(problem)

    before, etag = get_policy()
    try:
        existing = to_json(before).get("grants") or []
    except Exception as exc:
        print(f"cannot parse the live policy ({exc}); add anyway?", file=sys.stderr)
        return 2
    for current in existing:
        if same_grant(current, grant):
            print("that grant is already in the policy; nothing to do")
            return 3

    after, _ = insert_grant(before, json.dumps(grant, indent=2))
    return apply_change(before, after, "add", etag, do_apply, force)


def cmd_remove(index: int, do_apply: bool, force: bool) -> int:
    before, etag = get_policy()
    after = remove_grant(before, index)
    return apply_change(before, after, "remove", etag, do_apply, force)


def cmd_undo(do_apply: bool) -> int:
    path = newest_snapshot()
    text = path.read_text(encoding="utf-8")
    live, etag = get_policy()
    if live == text:
        print(f"live policy already matches {path.name}; nothing to do")
        return 3
    ok, detail = validate_policy(text)
    if not ok:
        print(f"snapshot {path.name} no longer validates, not applied:\n{detail}", file=sys.stderr)
        return 2
    print(diff(live, text))
    if not do_apply:
        print(f"\ndry run: would restore {path.name}. Re-run with --apply.")
        return 0
    snapshot(live, "pre-undo")
    status, new_etag, body = put_policy(text, etag)
    if status != 200:
        print(f"restore failed: HTTP {status}: {body[:400]}", file=sys.stderr)
        return 2
    print(f"restored {path.name}. new etag: {new_etag or '(none returned)'}")
    return 0


# ---------- plain English ----------
SYSTEM_PROMPT = (
    "You write tailnet policy grants for a small estate. You are given the live policy file and one request. "
    "Reply with exactly one grant as JSON, matching the grants syntax: src and dst are non-empty arrays of "
    "selectors that already exist in the policy (host aliases, tags, groups, autogroups, or addresses), ip is an "
    "array such as [\"tcp:22\"] taken from the request, and app is omitted unless a capability was asked for. "
    "Do not invent host aliases, tags or groups that the policy does not define. Do not write a grant from "
    "src [\"*\"] to dst [\"*\"] on all ports. If the request needs no new grant, reply with the word NONE."
)


def draft(request: str) -> str:
    if not LLM_KEY:
        raise SystemExit("OPENROUTER_API is not set; the plain-English mode needs it")
    policy, _ = get_policy()
    excerpt = policy if len(policy) <= 20000 else policy[:20000] + "\n// [truncated for the model]"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Live policy file:\n{excerpt}\n\nRequest: {request}"},
        ],
        "temperature": 0,
    }
    body = json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(f"{LLM_BASE}/chat/completions", data=body, method="POST")
    http_request.add_header("Content-Type", "application/json")
    http_request.add_header("Authorization", f"Bearer {LLM_KEY}")
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"model http {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}") from exc
    return (reply["choices"][0]["message"].get("content") or "").strip()


def cmd_natural(request: str, do_apply: bool, force: bool) -> int:
    answer = draft(request)
    print(f"model draft:\n{answer}\n")
    if answer.strip().upper().startswith("NONE"):
        print("the model says no new grant is needed; nothing written")
        return 3
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        print("no JSON grant in the draft; nothing written", file=sys.stderr)
        return 2
    return cmd_add(match.group(0), do_apply, force)


# ---------- entry point ----------
USAGE = """usage: tsgrant [--apply] [--force] <command>

  show                    print the live policy file and its ETag
  check                   validate the live policy, change nothing
  add '<grant json>'      add one grant            (dry run unless --apply)
  remove <n>              remove grant n           (dry run unless --apply)
  undo                    restore the newest snapshot (dry run unless --apply)
  "<request>"             draft a grant from plain English

  --apply     write the change (otherwise print the diff and stop)
  --force     proceed even if the lockout guard says SSH would be lost
"""


def main(argv: list[str]) -> int:
    args = [a for a in argv]
    if not args or args[0] in {"-h", "--help"}:
        print(USAGE)
        return 0 if args else 1
    do_apply = "--apply" in args
    force = "--force" in args
    words = [a for a in args if a not in {"--apply", "--force"}]
    command, rest = words[0], words[1:]

    if command == "show":
        return cmd_show()
    if command == "check":
        return cmd_check()
    if command == "add":
        if not rest:
            raise SystemExit("add needs a grant: tsgrant add '{\"src\": [...], \"dst\": [...], \"ip\": [...]}'")
        return cmd_add(rest[0], do_apply, force)
    if command == "remove":
        if not rest or not rest[0].isdigit():
            raise SystemExit("remove needs a grant number: tsgrant remove 2")
        return cmd_remove(int(rest[0]), do_apply, force)
    if command == "undo":
        return cmd_undo(do_apply)
    return cmd_natural(" ".join(words), do_apply, force)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(130)
