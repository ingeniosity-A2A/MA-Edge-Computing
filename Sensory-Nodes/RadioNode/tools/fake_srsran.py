#!/usr/bin/env python3
"""Fake patched-gNB control server (FAPO control protocol v1).

Serves the same JSON-Lines protocol as the srsRAN patch (see
srsran-patch/INTEGRATION.md) with synthetic random-walk telemetry, so
the real SRSRANAdapter can be integration-tested over the wire without
an SDR. Also handy as a smoke target for the C++ server's client.

Usage:
    python tools/fake_srsran.py --endpoint tcp://127.0.0.1:9001
    python tools/fake_srsran.py --endpoint unix:///tmp/fapo-gnb.sock
"""

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ran_capability.config import DEFAULT_CELL_PRBS, default_slice_policies
from ran_capability.protocol import (
    CAPABILITIES,
    ERR_UNKNOWN_OP,
    ERR_VERSION_MISMATCH,
    PROTOCOL_VERSION,
    SERVER_NAME,
    parse_endpoint,
)

log = logging.getLogger("fake_srsran")


class FakeGNB:
    def __init__(self, cell_prbs: int, seed: int):
        self.policies = default_slice_policies()
        self.cell_prbs = cell_prbs
        self.rng = random.Random(seed)
        self.queue = {sid: 10.0 + 40.0 * self.rng.random() for sid in self.policies}
        self.allocated = {sid: p.min_prbs for sid, p in self.policies.items()}
        self.power = {sid: p.max_power_dbm for sid, p in self.policies.items()}
        self.apply_count = 0

    # -- protocol ops -------------------------------------------------

    def _telemetry_payload(self) -> dict:
        # Random walk on queue occupancy, perturbed by recent applies.
        for sid in self.queue:
            pull_to_target = 0.0
            if self.allocated[sid] > self.policies[sid].min_prbs:
                pull_to_target = -1.5 * (
                    self.allocated[sid] - self.policies[sid].min_prbs
                ) / max(1, self.policies[sid].max_prbs)
            self.queue[sid] = min(
                96.0,
                max(2.0, self.queue[sid] + self.rng.uniform(-6.0, 8.0) + pull_to_target),
            )

        slices, used = {}, 0
        worst_latency = 0.0
        for sid, p in self.policies.items():
            q = self.queue[sid]
            latency = 4.0 + 0.4 * q
            slices[sid] = {
                "queue_depth": round(q, 2),
                "latency_ms": round(latency, 2),
                "prbs_used": self.allocated[sid],
                "packet_loss": round(max(0.0, (q - 80.0) / 5000.0), 5),
            }
            used += self.allocated[sid]
            worst_latency = max(worst_latency, latency)

        used = sum(self.allocated.values())
        weighted_power = (
            sum(self.power[sid] * self.allocated[sid] for sid in self.policies)
            / max(1, used)
        )
        return {
            "ok": True,
            "ts": time.time(),
            "cell": {
                "prbs_total": self.cell_prbs,
                "available_prbs": max(0, self.cell_prbs - used),
                "throughput_mbps": round(2.0 * used * (0.9 + 0.2 * self.rng.random()), 2),
                "latency_ms": round(worst_latency, 2),
                "packet_loss": 0.001,
                "tx_power_dbm": round(weighted_power, 2),
                "spectral_efficiency": 3.5,
            },
            "slices": slices,
            "policies": {
                sid: {
                    "slice_type": p.slice_type.value,
                    "min_prbs": p.min_prbs,
                    "max_prbs": p.max_prbs,
                    "max_latency_ms": p.max_latency_ms,
                    "max_power_dbm": p.max_power_dbm,
                    "priority": p.priority,
                }
                for sid, p in self.policies.items()
            },
        }

    def _apply(self, actions: list) -> dict:
        applied, rejected = [], []
        requested: dict[str, int] = {}
        powers: dict[str, float] = {}
        for act in actions:
            sid = act.get("slice_id")
            policy = self.policies.get(sid)
            if policy is None:
                rejected.append({"slice_id": sid, "reason": "unknown_slice"})
                continue
            try:
                prbs = int(act["prbs"])
                power = float(act["tx_power_dbm"])
            except (KeyError, TypeError, ValueError):
                rejected.append({"slice_id": sid, "reason": "malformed_action"})
                continue
            requested[sid] = min(max(prbs, policy.min_prbs), policy.max_prbs)
            powers[sid] = min(max(power, 0.0), policy.max_power_dbm)

        # Cell budget arbitration, same rule as the twin.
        total = sum(requested.values())
        if total > self.cell_prbs:
            excess = total - self.cell_prbs
            headroom = {
                sid: requested[sid] - self.policies[sid].min_prbs for sid in requested
            }
            reducible = sum(headroom.values())
            if reducible > 0:
                remaining = excess
                for sid, hr in headroom.items():
                    cut = min(
                        int(round(excess * hr / reducible)), hr, remaining
                    )
                    remaining -= cut
                    requested[sid] -= cut

        for sid, prbs in requested.items():
            self.allocated[sid] = prbs
            self.power[sid] = powers[sid]
            applied.append(
                {"slice_id": sid, "prbs": prbs, "tx_power_dbm": round(powers[sid], 2)}
            )
        self.apply_count += 1
        log.info("apply #%d: %s", self.apply_count, applied)
        return {"ok": True, "applied": applied, "rejected": rejected}

    def _reset(self) -> dict:
        for sid, p in self.policies.items():
            self.allocated[sid] = p.min_prbs
            self.power[sid] = p.max_power_dbm
        log.info("reset to baseline policy")
        return {"ok": True, "mode": "baseline"}

    def handle(self, req: dict) -> dict:
        req_id = req.get("id")
        if req.get("v") != PROTOCOL_VERSION:
            return self._error(req_id, ERR_VERSION_MISMATCH, "unsupported protocol version")
        op = req.get("op")

        def reply(payload: dict) -> dict:
            payload.update({"v": PROTOCOL_VERSION, "id": req_id})
            return payload

        if op == "hello":
            return reply(
                {
                    "ok": True,
                    "server": SERVER_NAME,
                    "protocol": PROTOCOL_VERSION,
                    "capabilities": list(CAPABILITIES),
                }
            )
        if op == "ping":
            return reply({"ok": True, "pong": True})
        if op == "get_telemetry":
            return reply(self._telemetry_payload())
        if op == "apply":
            return reply(self._apply(req.get("actions") or []))
        if op == "reset":
            return reply(self._reset())
        return self._error(req_id, ERR_UNKNOWN_OP, f"unknown op {op!r}")

    @staticmethod
    def _error(req_id, code: str, message: str) -> dict:
        return {
            "v": PROTOCOL_VERSION,
            "id": req_id,
            "ok": False,
            "error": {"code": code, "message": message},
        }


async def _serve(gnb: FakeGNB, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    log.info("client connected: %s", peer)
    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            try:
                req = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                resp = gnb._error(None, "bad_request", "line is not valid JSON")
            else:
                resp = gnb.handle(req)
            writer.write((json.dumps(resp, separators=(",", ":")) + "\n").encode("utf-8"))
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass
        log.info("client disconnected: %s", peer)


async def main_async(args) -> None:
    gnb = FakeGNB(cell_prbs=args.cell_prbs, seed=args.seed)
    kind, target = parse_endpoint(args.endpoint)
    if kind == "tcp":
        host, port = target
        server = await asyncio.start_server(lambda r, w: _serve(gnb, r, w), host, port)
        log.info("fake gNB listening on tcp://%s:%d", host, port)
    else:
        server = await asyncio.start_unix_server(lambda r, w: _serve(gnb, r, w), path=target)
        log.info("fake gNB listening on unix://%s", target)
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--endpoint", default="tcp://127.0.0.1:9001",
        help="tcp://host:port or unix:///path (default: tcp://127.0.0.1:9001)",
    )
    parser.add_argument("--cell-prbs", type=int, default=DEFAULT_CELL_PRBS)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
