#!/usr/bin/env python3
"""tsbot: dual-mode Tailscale agent for the edge estate.

    tsbot --daemon              watch and repair, forever (systemd unit)
    tsbot --once                one health pass, JSON to stdout (cron/timer)
    tsbot "why is nas-box slow" one natural-language request, then exit
    tsbot                       interactive terminal session

The model is MiMo through an OpenRouter-compatible endpoint, and it has no way
to call `tailscale up`, `down`, `logout` or `login`: those are connectivity
actions for the operator, so the agent can only propose them. What it may do
autonomously is the reversible half — clearing a broken exit node with
`tailscale set --exit-node=`, after two consecutive probes of the exit node
itself fail, at most once per cooldown window.

Configuration (environment):
    OPENROUTER_API     required for the natural-language modes
    TS_MODEL           model id                    (default xiaomi/mimo-v2.6-pro)
    TS_API_BASE        API root       (default https://openrouter.ai/api/v1)
    TS_INTERVAL        seconds between daemon passes (default 60)
    TS_COOLDOWN        seconds between repairs        (default 600)
    TS_MAX_CYCLES      stop the daemon after N passes  (default 0 = forever)
    TS_LOG             also append JSON lines here    (default stdout only)
    TS_STATE_DIR       lock and state directory      (default /var/lib/tsbot)
    TS_DRY_RUN=1       report what would be repaired, change nothing

Exit codes: 0 ok · 1 usage/configuration · 3 another instance holds the lock.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODEL = os.getenv("TS_MODEL", "xiaomi/mimo-v2.6-pro")
API_BASE = os.getenv("TS_API_BASE", "https://openrouter.ai/api/v1")
API_KEY = os.getenv("OPENROUTER_API") or os.getenv("OPENROUTER_API_KEY") or ""
INTERVAL = int(os.getenv("TS_INTERVAL", "60"))
COOLDOWN = int(os.getenv("TS_COOLDOWN", "600"))
MAX_CYCLES = int(os.getenv("TS_MAX_CYCLES", "0"))
LOG_FILE = os.getenv("TS_LOG", "")
STATE_DIR = Path(os.getenv("TS_STATE_DIR", "/var/lib/tsbot"))
DRY_RUN = os.getenv("TS_DRY_RUN") == "1"
MAX_ROUNDS = int(os.getenv("TS_MAX_ROUNDS", "6"))
FAILURES_BEFORE_REPAIR = 2

# Everything the agent is allowed to execute. `up`, `down`, `logout`, `login`,
# `serve`, `funnel`, `cert` and `debug` are absent on purpose: no path in this
# program can run them, so the refusal cannot be talked around.
ALLOWED = [
    ("status", "--json"),
    ("status",),
    ("netcheck", "--format=json"),
    ("netcheck",),
    ("ip", "-4"),
    ("ip",),
    ("version",),
    ("dns", "status", "--json"),
    ("ping",),
    ("set", "--exit-node="),
    ("set", "--accept-routes"),
    ("set", "--accept-routes=false"),
    ("set", "--advertise-exit-node"),
    ("set", "--advertise-exit-node=false"),
    ("set", "--shields-up"),
    ("set", "--shields-up=false"),
]

NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


# ---------- plumbing ----------
def log(level: str, message: str, **fields) -> dict:
    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": level,
        "component": "tsbot",
        "msg": message,
        **fields,
    }
    line = json.dumps(record, ensure_ascii=False)
    print(line, flush=True)
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as exc:  # the daemon may run without write access there
            print(json.dumps({"level": "warn", "msg": "log file unwritable", "error": str(exc)}), flush=True)
    return record


def allowed(argv: list[str]) -> bool:
    return any(tuple(argv[: len(rule)]) == rule for rule in ALLOWED)


def run_ts(args: list[str], timeout: int = 15) -> dict:
    if not allowed(args):
        return {"argv": args, "code": 126, "out": "", "err": "refused: not on the tsbot allowlist"}
    try:
        done = subprocess.run(["tailscale", *args], capture_output=True, text=True, timeout=timeout)
        return {"argv": args, "code": done.returncode, "out": done.stdout.strip(), "err": done.stderr.strip()}
    except FileNotFoundError:
        return {"argv": args, "code": 127, "out": "", "err": "tailscale not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"argv": args, "code": 124, "out": "", "err": f"timed out after {timeout}s"}


def clip(text: str, limit: int = 1500) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


# ---------- observation ----------
def status() -> dict | None:
    result = run_ts(["status", "--json"], timeout=20)
    if not result["out"].startswith("{"):
        return None
    try:
        return json.loads(result["out"])
    except json.JSONDecodeError:
        return None


def diagnose() -> dict:
    raw = status()
    if raw is None:
        return {"reachable": False, "detail": "tailscale status --json returned no JSON (daemon down or not logged in)"}

    exit_node = raw.get("ExitNodeStatus") or None
    if exit_node:
        exit_node = {
            "id": exit_node.get("ID"),
            "online": bool(exit_node.get("Online")),
            "ips": [str(ip).split("/")[0] for ip in exit_node.get("TailscaleIPs") or []],
        }
    peers = raw.get("Peer") or {}
    online = sum(1 for peer in peers.values() if peer.get("Online"))
    return {
        "reachable": True,
        "backend_state": raw.get("BackendState"),
        "health": raw.get("Health") or [],
        "auth_url": raw.get("AuthURL") or "",
        "self_ips": [str(ip).split("/")[0] for ip in raw.get("TailscaleIPs") or []],
        "exit_node": exit_node,
        "peers_online": online,
        "peers_total": len(peers),
    }


def probe_exit_node(node: dict) -> dict:
    """Reach the exit node over Tailscale, without requiring a direct path.

    `--until-direct=false` matters: it defaults to true, and with it a healthy
    node reached through DERP exits non-zero, which would look like an outage.
    """
    if not node.get("ips"):
        return {"ok": False, "detail": "exit node has no Tailscale IP in status"}
    result = run_ts(["ping", "--until-direct=false", "-c", "2", "--timeout=3s", node["ips"][0]], timeout=25)
    return {"ok": result["code"] == 0, "detail": clip(f"exit {result['code']}: {result['out'] or result['err']}", 400)}


def clear_exit_node() -> dict:
    if DRY_RUN:
        return {"argv": ["set", "--exit-node="], "code": 0, "out": "dry run: not executed", "err": ""}
    return run_ts(["set", "--exit-node="], timeout=20)


# ---------- daemon ----------
def acquire_lock():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(STATE_DIR / "tsbot.lock", "w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another tsbot instance holds the lock", file=sys.stderr)
        sys.exit(3)
    return handle


def daemon_cycle(state: dict) -> None:
    health = diagnose()
    if not health.get("reachable"):
        state["failures"] = 0
        log("warn", "tailscale not observable", detail=health.get("detail"),
            proposal="operator: sudo tailscale up (connectivity actions are never taken by this daemon)")
        return

    if health["backend_state"] != "Running":
        state["failures"] = 0
        log("warn", "tailscale not running", backend_state=health["backend_state"],
            auth_url=health["auth_url"],
            proposal="operator: sudo tailscale up (auth keys are not handled by this daemon)")
        return

    node = health.get("exit_node")
    if not node:
        state["failures"] = 0
        log("info", "healthy", peers_online=health["peers_online"], peers_total=health["peers_total"])
        return

    probe = probe_exit_node(node) if node["online"] else {"ok": False, "detail": "exit node reports offline"}
    if probe["ok"]:
        state["failures"] = 0
        log("info", "healthy via exit node", exit_node=node["id"])
        return

    state["failures"] += 1
    elapsed = time.time() - state.get("last_repair", 0)
    if state["failures"] < FAILURES_BEFORE_REPAIR:
        log("warn", "exit node probe failed", exit_node=node["id"], failures=state["failures"], detail=probe["detail"])
        return
    if elapsed < COOLDOWN:
        log("warn", "repair suppressed by cooldown", exit_node=node["id"], retry_in=int(COOLDOWN - elapsed))
        return

    result = clear_exit_node()
    state["last_repair"] = time.time()
    state["failures"] = 0
    # --exit-node= takes a hostname or IP, not the stable node id, so the undo
    # hint has to name the address that was in use.
    target = node["ips"][0] if node.get("ips") else node["id"]
    if result["code"] == 0:
        log("info", "cleared unresponsive exit node", exit_node=node["id"],
            undo=f"tailscale set --exit-node={target}", dry_run=DRY_RUN)
    else:
        log("error", "clearing exit node failed", exit_node=node["id"], err=clip(result["err"], 300))


def run_daemon() -> int:
    lock = acquire_lock()
    log("info", "watchdog started", interval=INTERVAL, model=MODEL, dry_run=DRY_RUN)
    state: dict = {"failures": 0, "last_repair": 0.0}
    cycle = 0
    try:
        while True:
            cycle += 1
            try:
                daemon_cycle(state)
            except Exception as exc:  # a bad pass must not kill the watchdog
                log("error", "cycle raised", error=repr(exc))
            if MAX_CYCLES and cycle >= MAX_CYCLES:
                log("info", "cycle budget reached", cycles=cycle)
                return 0
            time.sleep(INTERVAL)
    finally:
        lock.close()


# ---------- natural language ----------
SYSTEM_PROMPT = (
    "You are the Tailscale technician for this host. Answer from tool output only; never invent node names, "
    "IPs or flags. You cannot bring the tunnel up, down, log out or log in — those are operator actions, so when "
    "one is needed, say exactly which command the operator should run and why. Be brief: 2-4 sentences, and name "
    "the command or node you used."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "tailnet_status",
        "description": "Backend state, health warnings, exit node and peer counts for this host.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "tailnet_netcheck",
        "description": "UDP, IPv4/IPv6, DERP and NAT verdicts for this host's network.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "tailnet_ping",
        "description": "Ping a tailnet node over Tailscale and report whether it answered.",
        "parameters": {"type": "object", "properties": {
            "node": {"type": "string", "description": "hostname or 100.x.y.z address"}}, "required": ["node"]}}},
    {"type": "function", "function": {
        "name": "tailnet_route",
        "description": "Route outbound traffic through an exit node, or clear the exit node.",
        "parameters": {"type": "object", "properties": {
            "node": {"type": "string", "description": "exit node hostname/IP, or 'none' to clear"}},
            "required": ["node"]}}},
    {"type": "function", "function": {
        "name": "tailnet_preferences",
        "description": "Set reversible node preferences: accept subnet routes, advertise as exit node, or block incoming.",
        "parameters": {"type": "object", "properties": {
            "accept_routes": {"type": "boolean"},
            "advertise_exit_node": {"type": "boolean"},
            "shields_up": {"type": "boolean"}}}}},
    {"type": "function", "function": {
        "name": "repair_log",
        "description": "Recent automatic repairs this watchdog performed.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "how many lines, default 20"}}}}},
]


def tool_status() -> str:
    return json.dumps(diagnose())


def tool_netcheck() -> str:
    result = run_ts(["netcheck", "--format=json"], timeout=45)
    return clip(result["out"] or result["err"], 2000)


def tool_ping(node: str = "") -> str:
    if not isinstance(node, str) or not (NODE_RE.fullmatch(node) or node.startswith("100.")):
        return "refused: node must be a hostname or a 100.x.y.z address"
    result = run_ts(["ping", "-c", "3", "--timeout=3s", node], timeout=30)
    # Name the node that was pinged: relayed pongs print the peer's own address,
    # and without this the answer can be attributed to the wrong device.
    return clip(f"pinged {node}\nexit {result['code']}\n{result['out'] or result['err']}", 1200)


def tool_route(node: str = "") -> str:
    if not isinstance(node, str) or not node.strip():
        return "refused: node is required (hostname, 100.x.y.z, or 'none')"
    if node.lower() in {"none", "off", "clear", "disable"}:
        result = clear_exit_node()
        return f"exit {result['code']}: exit node cleared (undo: set --exit-node=<previous>)\n{clip(result['err'], 200)}"
    if not (NODE_RE.fullmatch(node) or node.startswith("100.")):
        return "refused: node must be a hostname or a 100.x.y.z address"
    result = run_ts(["set", f"--exit-node={node}"], timeout=25)
    return f"exit {result['code']}: routed through {node} (undo: set --exit-node=)\n{clip(result['err'], 200)}"


def tool_preferences(accept_routes=None, advertise_exit_node=None, shields_up=None) -> str:
    args: list[str] = []
    if isinstance(accept_routes, bool):
        args.append(f"--accept-routes={str(accept_routes).lower()}")
    if isinstance(advertise_exit_node, bool):
        args.append(f"--advertise-exit-node={str(advertise_exit_node).lower()}")
    if isinstance(shields_up, bool):
        args.append(f"--shields-up={str(shields_up).lower()}")
    if not args:
        return "refused: nothing to change"
    result = run_ts(["set", *args], timeout=25)
    undo = "set " + " ".join(f"{a.split('=')[0]}={str(not a.endswith('true')).lower()}" for a in args)
    return f"exit {result['code']}: {', '.join(args)} (undo: tailscale {undo})\n{clip(result['err'], 200)}"


def tool_repair_log(limit: int = 20) -> str:
    if not LOG_FILE or not os.path.exists(LOG_FILE):
        return "no repair log file configured (TS_LOG unset)"
    with open(LOG_FILE, "r", encoding="utf-8") as handle:
        lines = [line for line in handle if '"msg"' in line]
    repairs = [line for line in lines if "cleared unresponsive exit node" in line or "repair" in line]
    return "".join((repairs or lines)[-max(1, min(int(limit or 20), 100)):])


TOOL_MAP = {
    "tailnet_status": tool_status,
    "tailnet_netcheck": tool_netcheck,
    "tailnet_ping": tool_ping,
    "tailnet_route": tool_route,
    "tailnet_preferences": tool_preferences,
    "repair_log": tool_repair_log,
}


def chat(messages: list[dict], use_tools: bool = True) -> dict:
    if not API_KEY:
        raise SystemExit("OPENROUTER_API is not set; the natural-language modes need it")
    payload = {"model": MODEL, "messages": messages}
    if use_tools:
        payload["tools"] = TOOLS
        payload["tool_choice"] = "auto"
    request = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"model http {exc.code}: {body}") from exc


def ask(prompt: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    for _ in range(MAX_ROUNDS):
        reply = chat(messages)
        message = reply["choices"][0]["message"]
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            return message.get("content") or "(no answer)"
        for call in calls:
            name = call.get("function", {}).get("name", "")
            handler = TOOL_MAP.get(name)
            try:
                args = json.loads(call.get("function", {}).get("arguments") or "{}")
                output = handler(**args) if handler else f"refused: unknown tool {name}"
            except Exception as exc:
                output = f"tool error: {exc!r}"
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": str(output)})
    return "(tool budget exhausted without a final answer)"


# ---------- entry point ----------
USAGE = "usage: tsbot [--daemon | --once | \"plain-English request\"]"


def main(argv: list[str]) -> int:
    if argv and argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    if argv and argv[0] == "--daemon":
        return run_daemon()
    if argv and argv[0] == "--once":
        health = diagnose()
        log("info" if health.get("backend_state") == "Running" else "warn", "one-shot", **health)
        return 0 if health.get("backend_state") == "Running" else 1
    if argv and argv[0] == "--allowlist":
        print(json.dumps([" ".join(rule) for rule in ALLOWED], indent=2))
        return 0
    if argv:
        print(ask(" ".join(argv)))
        return 0

    print(f"tsbot — model {MODEL}. Type 'exit' to quit.")
    while True:
        try:
            line = input("you > ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if line.lower() in {"exit", "quit"}:
            return 0
        if line:
            try:
                print(ask(line))
            except SystemExit as exc:
                print(f"error: {exc}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
