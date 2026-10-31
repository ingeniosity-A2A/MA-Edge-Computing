"""Wire-level tests: the real SRSRANAdapter against in-process servers."""

import asyncio
import json

import pytest

from ran_capability.fapo import FAPOAction
from ran_capability.protocol import (
    ERR_UNKNOWN_SLICE,
    AdapterUnavailable,
    ProtocolError,
)
from ran_capability.srsran.control_socket_adapter import SRSRANAdapter

POLICIES = {
    "rll": {
        "slice_type": "rll", "min_prbs": 2, "max_prbs": 12,
        "max_latency_ms": 10.0, "max_power_dbm": 21.0, "priority": 1,
    },
    "high_capacity": {
        "slice_type": "high_capacity", "min_prbs": 4, "max_prbs": 24,
        "max_latency_ms": 20.0, "max_power_dbm": 23.0, "priority": 2,
    },
}

TELEMETRY = {
    "ok": True,
    "ts": 1730000000.5,
    "cell": {
        "prbs_total": 51, "available_prbs": 39, "throughput_mbps": 18.4,
        "latency_ms": 12.3, "packet_loss": 0.001, "tx_power_dbm": 21.5,
        "spectral_efficiency": 3.5,
    },
    "slices": {
        "rll": {"queue_depth": 42.0, "latency_ms": 23.3, "prbs_used": 4,
                "packet_loss": 0.0},
        "high_capacity": {"queue_depth": 30.0, "latency_ms": 12.1,
                          "prbs_used": 8, "packet_loss": 0.001},
    },
    "policies": POLICIES,
}


class MiniGNB:
    """Speaks just enough protocol v1 for adapter tests."""

    def __init__(self, reply_telemetry=None):
        self.reply_telemetry = reply_telemetry or TELEMETRY
        self.applies = []

    async def handle(self, reader, writer):
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                req = json.loads(raw.decode())
                if req.get("op") == "get_telemetry":
                    resp = dict(self.reply_telemetry)
                elif req.get("op") == "apply":
                    actions = req.get("actions", [])
                    if any(a.get("slice_id") not in POLICIES for a in actions):
                        resp = {"v": 1, "ok": False,
                                "error": {"code": ERR_UNKNOWN_SLICE,
                                          "message": "no such slice"}}
                    else:
                        self.applies = actions
                        resp = {"v": 1, "ok": True, "applied": self.applies,
                                "rejected": []}
                elif req.get("op") == "hello":
                    resp = {"v": 1, "ok": True, "server": "mini",
                            "protocol": 1, "capabilities": ["telemetry"]}
                else:
                    resp = {"v": 1, "ok": False,
                            "error": {"code": ERR_UNKNOWN_SLICE,
                                      "message": "nope"}}
                resp["id"] = req.get("id")
                writer.write((json.dumps(resp) + "\n").encode())
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


class SilentGNB:
    """Accepts connections and never answers (timeout path)."""

    async def handle(self, reader, writer):
        await asyncio.sleep(30)


async def _start(server_handler):
    server = await asyncio.start_server(server_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


def test_telemetry_mapping_and_aggregation():
    async def _main():
        gnb = MiniGNB()
        server, port = await _start(gnb.handle)
        adapter = SRSRANAdapter(f"tcp://127.0.0.1:{port}", request_timeout_s=2.0)
        try:
            state = await adapter.telemetry()
        finally:
            await adapter.close()
            server.close()

        t = state.telemetry
        assert t.timestamp == pytest.approx(1730000000.5)
        assert t.throughput_mbps == pytest.approx(18.4)
        assert t.available_prbs == 39
        assert t.tx_power_dbm == pytest.approx(21.5)
        # aggregation: worst slice drives latency and queue depth
        assert t.latency_ms == pytest.approx(23.3)
        assert t.queue_depth == pytest.approx(42.0)

        # policies come from the gNB, radio is source of truth
        assert set(state.slices) == {"rll", "high_capacity"}
        rll = state.slices["rll"]
        assert rll.min_prbs == 2 and rll.max_prbs == 12
        assert rll.max_power_dbm == pytest.approx(21.0)

    asyncio.run(_main())


def test_apply_round_trip_records_actions():
    async def _main():
        gnb = MiniGNB()
        server, port = await _start(gnb.handle)
        adapter = SRSRANAdapter(f"tcp://127.0.0.1:{port}", request_timeout_s=2.0)
        try:
            await adapter.apply([
                FAPOAction("rll", prbs=8, tx_power_dbm=19.5),
                FAPOAction("high_capacity", prbs=20, tx_power_dbm=22.0),
            ])
        finally:
            await adapter.close()
            server.close()

        assert gnb.applies == [
            {"slice_id": "rll", "prbs": 8, "tx_power_dbm": 19.5},
            {"slice_id": "high_capacity", "prbs": 20, "tx_power_dbm": 22.0},
        ]

    asyncio.run(_main())


def test_error_response_raises_protocol_error():
    async def _main():
        gnb = MiniGNB()
        server, port = await _start(gnb.handle)
        adapter = SRSRANAdapter(f"tcp://127.0.0.1:{port}", request_timeout_s=2.0)
        try:
            with pytest.raises(ProtocolError):
                await adapter.apply([FAPOAction("ghost", prbs=1, tx_power_dbm=1.0)])
        finally:
            await adapter.close()
            server.close()

    asyncio.run(_main())


def test_silent_server_times_out_as_unavailable():
    async def _main():
        server, port = await _start(SilentGNB().handle)
        adapter = SRSRANAdapter(
            f"tcp://127.0.0.1:{port}", connect_timeout_s=1.0, request_timeout_s=0.2
        )
        try:
            with pytest.raises(AdapterUnavailable):
                await adapter.telemetry()
        finally:
            await adapter.close()
            server.close()

    asyncio.run(_main())


def test_unreachable_endpoint_raises_immediately():
    async def _main():
        adapter = SRSRANAdapter("tcp://127.0.0.1:1", connect_timeout_s=0.5)
        with pytest.raises(AdapterUnavailable):
            await adapter.telemetry()

    asyncio.run(_main())


def test_hello_reports_server_identity():
    async def _main():
        gnb = MiniGNB()
        server, port = await _start(gnb.handle)
        adapter = SRSRANAdapter(f"tcp://127.0.0.1:{port}", request_timeout_s=2.0)
        try:
            info = await adapter.hello()
            assert info["server"] == "mini"
            assert info["protocol"] == 1
        finally:
            await adapter.close()
            server.close()

    asyncio.run(_main())
