"""Digital twin of the patched srsRAN gNB.

A closed-loop, in-process radio model implementing the RANAdapter
interface, so FAPO + SafetyEnvelope + RANCapability can be exercised
end-to-end without SDR hardware:

* each slice has a synthetic arrival process and a finite queue;
* served bits scale with allocated PRBs (and slightly with tx power);
* overflow is counted as packet loss;
* latency is a function of queue occupancy.

`telemetry()` advances the model by real elapsed time (capped at 2 s),
so the control loop, the staleness watchdog, and FAPO dynamics all
behave like the real thing. `age_clock()` simulates a frozen telemetry
feed for watchdog testing.

Scales used are the same as the wire protocol: queue_depth is a
normalized 0..100 congestion percentage.
"""

import random
import time

from ..config import DEFAULT_CELL_PRBS
from ..adapter import RANAdapter
from ..fapo import FAPOAction
from ..models import (
    RANState,
    RANTelemetry,
    SlicePolicy,
    SliceTelemetry,
)

DEFAULT_ARRIVALS_MBPS = {
    "rll": 0.8,
    "high_capacity": 12.0,
    "best_effort": 9.0,
}

DEFAULT_QUEUE_CAP_BITS = {
    "rll": 1_500_000,
    "high_capacity": 4_000_000,
    "best_effort": 2_500_000,
}


def _telemetry_from_snapshots(cell: dict, slices: dict, ts: float) -> RANTelemetry:
    """Flatten the wire-schema dicts into the frozen RANTelemetry model.

    Same aggregation as SRSRANAdapter: the worst slice drives latency
    and queue_depth. Kept local to the twin so both paths stay readable.
    """
    queue_depth = max((s["queue_depth"] for s in slices.values()), default=0.0)
    return RANTelemetry(
        timestamp=ts,
        throughput_mbps=float(cell["throughput_mbps"]),
        latency_ms=float(cell["latency_ms"]),
        packet_loss=float(cell["packet_loss"]),
        queue_depth=float(queue_depth),
        available_prbs=int(cell["available_prbs"]),
        tx_power_dbm=float(cell["tx_power_dbm"]),
        spectral_efficiency=float(cell["spectral_efficiency"]),
    )


class SimulatedSRSRANAdapter(RANAdapter):
    def __init__(
        self,
        policies: dict[str, SlicePolicy],
        cell_prbs: int = DEFAULT_CELL_PRBS,
        seed: int = 7,
        service_mbps_per_prb: float = 2.0,
        arrival_mbps: dict[str, float] | None = None,
        queue_capacity_bits: dict[str, float] | None = None,
        base_spectral_efficiency: float = 3.5,
    ):
        self._policies = dict(policies)
        self._cell_prbs = int(cell_prbs)
        self._rng = random.Random(seed)
        self._service_mbps_per_prb = float(service_mbps_per_prb)
        self._base_se = float(base_spectral_efficiency)
        self._arrival_mbps = dict(arrival_mbps or DEFAULT_ARRIVALS_MBPS)
        self._queue_cap = dict(queue_capacity_bits or DEFAULT_QUEUE_CAP_BITS)

        self._allocated = {sid: p.min_prbs for sid, p in self._policies.items()}
        self._power = {sid: p.max_power_dbm for sid, p in self._policies.items()}
        self._queue = {sid: 0.0 for sid in self._policies}
        self._last_ts: float | None = None
        self._clock_offset = 0.0
        self._last_drops = {sid: 0.0 for sid in self._policies}
        self._last_arrivals = {sid: 0.0 for sid in self._policies}
        self._last_served_bits = 0.0
        self.applied_history: list[dict] = []

    # -- diagnostics / test hooks ------------------------------------

    def age_clock(self, seconds: float) -> None:
        """Make the next telemetry timestamps look `seconds` older."""
        self._clock_offset -= float(seconds)

    def restore_clock(self) -> None:
        self._clock_offset = 0.0

    def set_backlog(self, slice_id: str, pct: float) -> None:
        """Pre-load a slice queue to a given congestion percentage."""
        if slice_id not in self._queue:
            raise KeyError(f"unknown slice {slice_id!r}")
        pct = min(100.0, max(0.0, float(pct)))
        self._queue[slice_id] = pct / 100.0 * self._queue_cap[slice_id]

    def queue_depths(self) -> dict[str, float]:
        return {
            sid: (q / self._queue_cap[sid]) * 100.0
            for sid, q in self._queue.items()
        }

    # -- model internals ----------------------------------------------

    def _time(self) -> float:
        return time.time() + self._clock_offset

    @staticmethod
    def _power_factor(power_dbm: float) -> float:
        # Subtle SINR coupling: ~2% service-rate change per dB around an
        # 18 dBm reference, clamped. Keeps the power action meaningful
        # but second-order next to the PRB action.
        return min(1.15, max(0.70, 1.0 + 0.02 * (power_dbm - 18.0)))

    def _advance(self, dt: float) -> None:
        served_total = 0.0
        for sid in self._policies:
            jitter = 0.7 + 0.6 * self._rng.random()
            arrivals = self._arrival_mbps.get(sid, 1.0) * 1e6 * jitter * dt
            se_mult = self._power_factor(self._power[sid])
            service = (
                self._allocated[sid]
                * self._service_mbps_per_prb
                * 1e6
                * se_mult
                * dt
            )
            inflow = self._queue[sid] + arrivals
            served = min(inflow, service)
            new_q = inflow - served
            overflow = max(0.0, new_q - self._queue_cap[sid])
            new_q = min(new_q, self._queue_cap[sid])

            self._queue[sid] = new_q
            self._last_drops[sid] = overflow
            self._last_arrivals[sid] = arrivals
            served_total += served
        self._last_served_bits = served_total

    # -- RANAdapter interface -----------------------------------------

    async def telemetry(self) -> RANState:
        now = self._time()
        dt = 0.0 if self._last_ts is None else min(2.0, max(0.0, now - self._last_ts))
        self._last_ts = now
        if dt > 0:
            self._advance(dt)

        slices = {}
        worst_latency = 0.0
        for sid, policy in self._policies.items():
            q_pct = (self._queue[sid] / self._queue_cap[sid]) * 100.0
            latency = 4.0 + 0.46 * q_pct
            arrivals = self._last_arrivals[sid]
            loss = (self._last_drops[sid] / arrivals) if arrivals > 0 else 0.0
            slices[sid] = {
                "queue_depth": round(q_pct, 2),
                "latency_ms": round(latency, 2),
                "prbs_used": self._allocated[sid],
                "packet_loss": round(loss, 5),
            }
            worst_latency = max(worst_latency, latency)

        used = sum(self._allocated.values())
        available = max(0, self._cell_prbs - used)
        weighted_power = (
            sum(self._power[sid] * self._allocated[sid] for sid in self._policies)
            / max(1, used)
        )

        cell = {
            "prbs_total": self._cell_prbs,
            "available_prbs": available,
            "throughput_mbps": round(self._last_served_bits / 1e6 / dt, 2) if dt > 0 else 0.0,
            "latency_ms": round(worst_latency, 2),
            "packet_loss": round(
                sum(self._last_drops.values())
                / max(1e-9, sum(self._last_arrivals.values())),
                5,
            ),
            "tx_power_dbm": round(weighted_power, 2),
            "spectral_efficiency": round(
                self._base_se * self._power_factor(weighted_power), 2
            ),
        }

        telemetry = _telemetry_from_snapshots(cell, slices, now)
        # Same per-slice view the real adapter surfaces from the
        # patched scheduler, so the Lyapunov virtual queues behave
        # identically against the twin and against hardware.
        telemetry.slices = {
            sid: SliceTelemetry(
                queue_depth=float(s["queue_depth"]),
                latency_ms=float(s["latency_ms"]),
                prbs_used=int(s["prbs_used"]),
                packet_loss=float(s["packet_loss"]),
            )
            for sid, s in slices.items()
        }
        return RANState(telemetry=telemetry, slices=dict(self._policies))

    async def apply(self, actions: list[FAPOAction]) -> None:
        if not actions:
            return
        applied, rejected = [], []
        valid: dict[str, tuple[int, float]] = {}

        for act in actions:
            policy = self._policies.get(act.slice_id)
            if policy is None:
                rejected.append({"slice_id": act.slice_id, "reason": "unknown_slice"})
                continue
            prbs = int(min(max(int(act.prbs), policy.min_prbs), policy.max_prbs))
            power = float(
                min(max(float(act.tx_power_dbm), 0.0), policy.max_power_dbm)
            )
            valid[act.slice_id] = (prbs, power)

        # Cell budget arbitration: shave excess headroom proportionally,
        # mirroring what the patched scheduler does server-side.
        total = sum(prbs for prbs, _ in valid.values())
        if total > self._cell_prbs:
            excess = total - self._cell_prbs
            mins = {sid: self._policies[sid].min_prbs for sid in valid}
            headroom = {sid: valid[sid][0] - mins[sid] for sid in valid}
            reducible = sum(headroom.values())
            if reducible > 0:
                scaled = {}
                remaining = excess
                for sid, (prbs, power) in valid.items():
                    cut = min(
                        int(round(excess * headroom[sid] / reducible)),
                        headroom[sid],
                        remaining,
                    )
                    remaining -= cut
                    scaled[sid] = (prbs - cut, power)
                valid = scaled

        for sid, (prbs, power) in valid.items():
            self._allocated[sid] = prbs
            self._power[sid] = power
            applied.append(
                {"slice_id": sid, "prbs": prbs, "tx_power_dbm": round(power, 2)}
            )
        self.applied_history.append({"ts": self._time(), "applied": applied})

    # expose the wire-schema pieces for parity with the fake gNB
    def cell_snapshot(self) -> dict:
        """Best-effort snapshot without advancing the model."""
        depths = self.queue_depths()
        used = sum(self._allocated.values())
        return {
            "prbs_total": self._cell_prbs,
            "available_prbs": max(0, self._cell_prbs - used),
            "queue_depth_pct": depths,
            "allocated_prbs": dict(self._allocated),
        }
