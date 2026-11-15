"""Real srsRAN adapter: FAPO control protocol over a JSON-Lines socket.

This replaces the original `NotImplementedError` stub. The peer is the
small control server patched into the srsRAN Project gNB (see
srsran-patch/INTEGRATION.md) or, for testing, tools/fake_srsran.py.

Telemetry mapping
-----------------
The patched scheduler feed is per-slice. The frozen flat
RANTelemetry fields keep the worst-slice aggregation (the original
contract), while the full per-slice view is preserved on
`RANTelemetry.slices` for the Lyapunov virtual queues:

    latency_ms   = max over slices (worst slice drives policy)
    queue_depth  = max over slices of the 0..100 congestion percentage
    slices[sid]  = SliceTelemetry(queue_depth, latency_ms,
                                  prbs_used, packet_loss)
    everything else comes from the cell block

RANState.slices is populated from the gNB-reported static slice
policies, so the radio remains the source of truth for bounds.
"""

import logging
import time

from ..adapter import RANAdapter
from ..fapo import FAPOAction
from ..models import (
    RANState,
    RANTelemetry,
    SlicePolicy,
    SliceTelemetry,
    SliceType,
)
from ..protocol import OP_APPLY, OP_HELLO, OP_TELEMETRY, ProtocolError
from .json_socket import JsonSocketClient

logger = logging.getLogger(__name__)


def _raise_for_error(msg: dict, context: str) -> None:
    if msg.get("ok") is not True:
        err = msg.get("error") or {}
        raise ProtocolError(
            f"gNB rejected {context}: {err.get('code', 'unknown')}: "
            f"{err.get('message', msg)!r}"
        )


def _state_from_telemetry(msg: dict) -> RANState:
    cell = msg.get("cell") or {}
    slices = msg.get("slices") or {}
    policies_raw = msg.get("policies") or {}

    policies: dict[str, SlicePolicy] = {}
    for sid, p in policies_raw.items():
        try:
            policies[sid] = SlicePolicy(
                slice_id=sid,
                slice_type=SliceType(p.get("slice_type", "best_effort")),
                min_prbs=int(p["min_prbs"]),
                max_prbs=int(p["max_prbs"]),
                max_latency_ms=float(p["max_latency_ms"]),
                max_power_dbm=float(p["max_power_dbm"]),
                priority=int(p.get("priority", 10)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("ignoring malformed policy for slice %r: %s", sid, exc)

    def _max_over_slices(field: str) -> float | None:
        values = []
        for s in slices.values():
            try:
                values.append(float(s[field]))
            except (KeyError, TypeError, ValueError):
                continue
        return max(values) if values else None

    # Preserve the full per-slice scheduler view for the Lyapunov
    # virtual queues (y: backlog/service, z: latency budget, F:
    # guaranteed-share isolation). Malformed entries degrade to the
    # flat view rather than failing the cycle.
    per_slice: dict[str, SliceTelemetry] = {}
    for sid, s in slices.items():
        try:
            per_slice[sid] = SliceTelemetry(
                queue_depth=float(s.get("queue_depth", 0.0)),
                latency_ms=float(s.get("latency_ms", 0.0)),
                prbs_used=int(s.get("prbs_used", 0)),
                packet_loss=float(s.get("packet_loss", 0.0)),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            logger.warning("ignoring malformed telemetry for slice %r: %s", sid, exc)

    latency = _max_over_slices("latency_ms")
    if latency is None:
        latency = float(cell.get("latency_ms", 0.0))
    queue_depth = _max_over_slices("queue_depth")
    if queue_depth is None:
        queue_depth = float(cell.get("queue_depth", 0.0))

    telemetry = RANTelemetry(
        timestamp=float(msg.get("ts", time.time())),
        throughput_mbps=float(cell.get("throughput_mbps", 0.0)),
        latency_ms=latency,
        packet_loss=float(cell.get("packet_loss", 0.0)),
        queue_depth=queue_depth,
        available_prbs=int(cell.get("available_prbs", 0)),
        tx_power_dbm=float(cell.get("tx_power_dbm", 0.0)),
        spectral_efficiency=float(cell.get("spectral_efficiency", 0.0)),
        slices=per_slice,
    )
    return RANState(telemetry=telemetry, slices=policies)


class SRSRANAdapter(RANAdapter):
    """Boundary between the Exoskeleton RAN Capability and srsRAN.

    All srsRAN specifics live behind this class: the capability, FAPO,
    and AVA007 never see the wire protocol.
    """

    def __init__(
        self,
        endpoint: str,
        connect_timeout_s: float = 2.0,
        request_timeout_s: float = 1.5,
    ):
        self.endpoint = endpoint
        self._client = JsonSocketClient(
            endpoint,
            connect_timeout_s=connect_timeout_s,
            request_timeout_s=request_timeout_s,
        )

    async def hello(self) -> dict:
        """Probe the gNB control server (diagnostics; not used by FAPO)."""
        msg = await self._client.request(OP_HELLO)
        _raise_for_error(msg, "hello")
        return msg

    async def telemetry(self) -> RANState:
        msg = await self._client.request(OP_TELEMETRY)
        _raise_for_error(msg, "get_telemetry")
        return _state_from_telemetry(msg)

    async def apply(self, actions: list[FAPOAction]) -> None:
        if not actions:
            return
        payload = [
            {
                "slice_id": a.slice_id,
                "prbs": int(a.prbs),
                "tx_power_dbm": float(a.tx_power_dbm),
            }
            for a in actions
        ]
        msg = await self._client.request(OP_APPLY, {"actions": payload})
        _raise_for_error(msg, "apply")
        for rejected in msg.get("rejected") or []:
            logger.warning("gNB rejected action: %s", rejected)

    async def close(self) -> None:
        await self._client.close()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SRSRANAdapter(endpoint={self.endpoint!r})"
