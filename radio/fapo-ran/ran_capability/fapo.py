"""FAPO — Lyapunov drift-plus-penalty policy optimizer (LDPTRLQ).

Fast Autonomous Policy Optimizer. Operates on RAN telemetry and
produces a bounded radio-resource policy. It does not own AVA007
state or orchestration.

Framework
---------
LDPTRLQ: per-slice virtual queues track accumulated constraint
violation (the Lyapunov drift), and each cycle the optimizer picks
the policy that minimizes the drift-plus-penalty objective — the
penalty term carries weight V on radio power/resource cost:

    y[s,t]  backlog vs service deficit (queue-stability drift):
            y <- clamp(y + a(s,t) - served(s,t), 0, Y_MAX)
            a = backlog_norm * occupancy, served = last allocation
    z[s,t]  latency-budget violation budget (ms):
            z <- clamp(z + (latency - max_latency - slack), 0, Z_MAX)
    F[s,t]  guaranteed-share isolation deficit (PRBs):
            F <- clamp(F + iso_gain * max(0, min_prbs - used), 0, F_MAX)
            `used` is the scheduler's *actual* grant from per-slice
            telemetry, so F reacts to real starvation by the gNB.

Decision (drift-plus-penalty, smooth relaxation):

    w     = queue_weight * y + latency_weight * z + F     # pressure
    w'    = w * V_REF / V                                 # V-scaled
    rho   = 0 | w'/W_SAT | 1          piecewise: 0, linear band, sat
    prbs  = round(min_prbs + rho * (max_prbs - min_prbs))
    gamma = gamma_min + rho * (1 - gamma_min)             # power gain
    power = max_power_dbm + 20 * log10(gamma)

The [O(1/V), O(V)] tradeoff of the Lyapunov bound shows up directly:
larger V discounts accumulated pressure, so the engine spends fewer
resources (less transmit power, smaller allocations) and tolerates
more queueing delay; smaller V chases zero drift (max allocations,
max power). V_REF = 100 is the reference operating point, so V=100
behaves like the tuned production setting.

The old constructor signature (queue_weight, latency_weight,
power_weight) is preserved: the weights map onto the drift recursion
above, with power_weight setting the maximum power backoff
(12 dB * power_weight, i.e. 3 dB at the 0.25 default).
"""

import logging
import math

from .models import RANState

logger = logging.getLogger(__name__)

#: Reference operating point: V == V_REF behaves like the tuned
#: production setting; the pressure seen by the decision scales as
#: V_REF / V.
V_REF = 100.0


class FAPOAction:
    __slots__ = ("slice_id", "prbs", "tx_power_dbm")

    def __init__(self, slice_id: str, prbs: int, tx_power_dbm: float):
        self.slice_id = slice_id
        self.prbs = int(prbs)
        self.tx_power_dbm = float(tx_power_dbm)

    def __eq__(self, other) -> bool:
        if not isinstance(other, FAPOAction):
            return NotImplemented
        return (
            self.slice_id == other.slice_id
            and self.prbs == other.prbs
            and self.tx_power_dbm == other.tx_power_dbm
        )

    def __repr__(self) -> str:
        return (
            f"FAPOAction(slice_id={self.slice_id!r}, prbs={self.prbs}, "
            f"tx_power_dbm={self.tx_power_dbm:.2f})"
        )


class FAPO:
    """Lyapunov drift-plus-penalty optimizer (same contract as before).

    optimize(RANState) -> list[FAPOAction], fully deterministic and
    bounded by the gNB-reported slice policies.
    """

    def __init__(
        self,
        V: float = 100.0,
        queue_weight: float = 1.0,
        latency_weight: float = 2.0,
        power_weight: float = 0.25,
        backlog_norm: float = 100.0,
        slack_ms: float = 0.5,
        iso_gain: float = 10.0,
        w_sat: float = 200.0,
    ):
        if not (V > 0.0) or not math.isfinite(V):
            raise ValueError(f"V must be a positive finite number, got {V!r}")

        self.V = float(V)
        self.queue_weight = float(queue_weight)
        self.latency_weight = float(latency_weight)
        self.power_weight = float(power_weight)
        self.backlog_norm = float(backlog_norm)
        self.slack_ms = float(slack_ms)
        self.iso_gain = float(iso_gain)
        self.w_sat = float(w_sat)

        # Power backoff ceiling: 12 dB * power_weight (3 dB at the
        # 0.25 default, matching the original heuristic's backoff).
        self.max_backoff_db = 12.0 * self.power_weight
        self._gamma_min = 10.0 ** (-self.max_backoff_db / 20.0)

        # Per-slice virtual queues: y (backlog/service), z (latency
        # budget), F (guaranteed-share isolation).
        self._y: dict[str, float] = {}
        self._z: dict[str, float] = {}
        self._f: dict[str, float] = {}
        self._served: dict[str, float] = {}

        Y_MAX = 1.0e4
        Z_MAX = 1.0e3
        F_MAX = 5.0e2
        self._y_max, self._z_max, self._f_max = Y_MAX, Z_MAX, F_MAX

    # -- public API ----------------------------------------------------

    def optimize(self, state: RANState) -> list[FAPOAction]:
        if state.telemetry is None:
            return []

        t = state.telemetry
        actions = []

        for policy in state.slices.values():
            sid = policy.slice_id

            # Per-slice scheduler metrics when the gNB reports them;
            # fall back to the flat worst-slice view otherwise.
            st = t.slices.get(sid)
            q = self._finite(st.queue_depth if st is not None else t.queue_depth, 0.0)
            lat = self._finite(
                st.latency_ms if st is not None else t.latency_ms, 0.0
            )
            used: float | None = None if st is None else float(st.prbs_used)

            served = self._served.get(sid, float(policy.min_prbs))

            # -- virtual queue updates (Lyapunov drift recursion) -----
            occupancy = min(1.0, max(0.0, q / 100.0))
            arrivals = self.backlog_norm * occupancy
            y = max(0.0, self._y.get(sid, 0.0) + arrivals - served)
            self._y[sid] = min(self._y_max, y)

            z = self._z.get(sid, 0.0) + (lat - policy.max_latency_ms - self.slack_ms)
            self._z[sid] = min(self._z_max, max(0.0, z))

            guarantee = float(policy.min_prbs)
            observed = used if used is not None else served
            f = self._f.get(sid, 0.0) + self.iso_gain * max(0.0, guarantee - observed)
            self._f[sid] = min(self._f_max, max(0.0, f))

            # -- drift-plus-penalty decision ---------------------------
            w = (
                self.queue_weight * self._y[sid]
                + self.latency_weight * self._z[sid]
                + self._f[sid]
            )
            w_scaled = w * (V_REF / self.V)

            if w_scaled <= 0.0:
                rho = 0.0
            elif w_scaled >= self.w_sat:
                rho = 1.0
            else:
                rho = w_scaled / self.w_sat

            prbs = int(round(policy.min_prbs + rho * (policy.max_prbs - policy.min_prbs)))
            prbs = max(policy.min_prbs, min(prbs, policy.max_prbs))

            gamma = self._gamma_min + rho * (1.0 - self._gamma_min)
            power = policy.max_power_dbm + 20.0 * math.log10(gamma)

            self._served[sid] = float(prbs)
            actions.append(
                FAPOAction(slice_id=sid, prbs=prbs, tx_power_dbm=power)
            )

        return actions

    def reset(self) -> None:
        """Clear all virtual queues (e.g. after a reconnect)."""
        self._y.clear()
        self._z.clear()
        self._f.clear()
        self._served.clear()

    def snapshot(self) -> dict[str, dict[str, float]]:
        """Observability: current virtual-queue state per slice."""
        sids = set(self._y) | set(self._z) | set(self._f) | set(self._served)
        return {
            sid: {
                "y": self._y.get(sid, 0.0),
                "z": self._z.get(sid, 0.0),
                "F": self._f.get(sid, 0.0),
                "served": self._served.get(sid, 0.0),
            }
            for sid in sorted(sids)
        }

    # -- internals -----------------------------------------------------

    @staticmethod
    def _finite(value, default: float) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return default
        return v if math.isfinite(v) else default
