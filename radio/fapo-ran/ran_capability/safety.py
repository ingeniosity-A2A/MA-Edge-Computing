"""Safety envelope between FAPO and the radio.

Drop-in decorator with the same contract as FAPO:

    optimize(RANState) -> list[FAPOAction]

so `RANCapability` needs no changes at all:

    optimizer=SafetyEnvelope(FAPO(), SafetyLimits(...))

Enforcement layers, outermost first:

1. Telemetry watchdog. If the newest RANTelemetry is older than
   `telemetry_max_age_s`, the envelope stops forwarding optimizer
   output entirely and returns the *baseline* policy (min PRBs, max
   power per configured slice) so the radio falls back to its static
   config-file behaviour. This deliberately bypasses the rate limiter:
   safety wins over smoothing.

2. Apply rate limiter. At most one optimization application per
   `min_apply_interval_s`; between applies the previous policy holds.

3. Optimizer failure containment. If the inner optimizer raises, the
   envelope logs, marks the report degraded, and returns baseline
   actions rather than letting the exception hit the control loop.

4. Hard clamps. PRBs are forced into [min_prbs, max_prbs] of the
   slice's configured policy (defense in depth — FAPO already clamps)
   and power into [min_tx_power_dbm, max_power_dbm].

5. Ramp limits. Per cycle, PRBs may move at most
   `max_prb_step_frac * max_prbs` from the previously applied value,
   and power at most `max_power_step_db`. From a cold start the
   previously applied value is the slice baseline, so allocation ramps
   up gradually instead of jumping.

6. Cell budget. If the sum of requested PRBs exceeds `cell_prb_cap`,
   the excess is shaved proportionally from each slice's headroom
   above its minimum.

Actions referencing unknown slices are dropped, never forwarded.

The latest decision trail is available as `.last_report` (the control
loop logs it when degraded).
"""

import logging
import time
from dataclasses import dataclass, field

from .fapo import FAPOAction
from .models import RANState

logger = logging.getLogger(__name__)


@dataclass
class SafetyLimits:
    max_prb_step_frac: float = 0.25      # of the slice's max_prbs, per cycle
    max_power_step_db: float = 2.0       # dB per cycle
    min_tx_power_dbm: float = 0.0        # hard floor
    telemetry_max_age_s: float = 3.0     # watchdog threshold (3 cycles @ 1 s)
    min_apply_interval_s: float = 0.5    # apply rate limit
    cell_prb_cap: int | None = None      # cell-wide PRB budget


@dataclass
class SafetyReport:
    degraded: bool = False
    rate_limited: bool = False
    stale_age_s: float | None = None
    clamped: int = 0
    dropped: int = 0
    scaled: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "degraded": self.degraded,
            "rate_limited": self.rate_limited,
            "stale_age_s": self.stale_age_s,
            "clamped": self.clamped,
            "dropped": self.dropped,
            "scaled": self.scaled,
            "reasons": list(self.reasons),
        }


class SafetyEnvelope:
    """Same optimize() contract as FAPO; wraps any FAPO-like optimizer."""

    def __init__(self, optimizer, limits: SafetyLimits | None = None):
        self._optimizer = optimizer
        self._limits = limits or SafetyLimits()
        self._last_prbs: dict[str, int] = {}
        self._last_power: dict[str, float] = {}
        self._last_apply_mono: float | None = None
        self.last_report = SafetyReport()

    # -- public API ---------------------------------------------------

    def optimize(self, state: RANState) -> list[FAPOAction]:
        report = SafetyReport()
        self.last_report = report

        if state.telemetry is None:
            report.reasons.append("no telemetry — holding previous policy")
            return []

        age = time.time() - float(state.telemetry.timestamp)
        if age > self._limits.telemetry_max_age_s:
            report.degraded = True
            report.stale_age_s = age
            report.reasons.append(
                f"stale telemetry ({age:.1f}s old > "
                f"{self._limits.telemetry_max_age_s:.1f}s) — reverting to baseline"
            )
            logger.warning("safety watchdog: %s", report.reasons[-1])
            return self._baseline_actions(state, report)

        now = time.monotonic()
        if (
            self._last_apply_mono is not None
            and (now - self._last_apply_mono) < self._limits.min_apply_interval_s
        ):
            report.rate_limited = True
            report.reasons.append("apply rate limit — holding previous policy")
            return []

        try:
            raw = self._optimizer.optimize(state)
        except Exception as exc:  # containment: never propagate into the loop
            report.degraded = True
            report.reasons.append(f"optimizer failure: {exc!r} — reverting to baseline")
            logger.exception("safety envelope: optimizer raised")
            return self._baseline_actions(state, report)

        actions = self._bound_actions(raw, state, report)
        actions = self._apply_cell_budget(actions, state, report)

        if actions:
            self._remember(actions)
            self._last_apply_mono = now
        return actions

    # -- internals ----------------------------------------------------

    def _bound_actions(
        self, raw: list[FAPOAction], state: RANState, report: SafetyReport
    ) -> list[FAPOAction]:
        limits = self._limits
        bounded: list[FAPOAction] = []

        for act in raw:
            policy = state.slices.get(act.slice_id)
            if policy is None:
                report.dropped += 1
                report.reasons.append(
                    f"dropped action for unknown slice {act.slice_id!r}"
                )
                continue

            prbs = int(min(max(act.prbs, policy.min_prbs), policy.max_prbs))
            power = float(
                min(max(act.tx_power_dbm, limits.min_tx_power_dbm), policy.max_power_dbm)
            )

            prev_prbs = self._last_prbs.get(act.slice_id, policy.min_prbs)
            step = max(1, int(round(limits.max_prb_step_frac * policy.max_prbs)))
            prbs = int(min(max(prbs, prev_prbs - step), prev_prbs + step))
            prbs = int(min(max(prbs, policy.min_prbs), policy.max_prbs))

            prev_power = self._last_power.get(act.slice_id, policy.max_power_dbm)
            power = min(
                max(power, prev_power - limits.max_power_step_db),
                prev_power + limits.max_power_step_db,
            )
            power = min(
                max(power, limits.min_tx_power_dbm), policy.max_power_dbm
            )

            if prbs != act.prbs or power != act.tx_power_dbm:
                report.clamped += 1

            bounded.append(
                FAPOAction(slice_id=act.slice_id, prbs=prbs, tx_power_dbm=power)
            )

        if report.clamped:
            report.reasons.append(f"clamped/bounded {report.clamped} action(s)")
        if report.dropped:
            report.reasons.append(f"dropped {report.dropped} action(s)")
        return bounded

    def _apply_cell_budget(
        self,
        actions: list[FAPOAction],
        state: RANState,
        report: SafetyReport,
    ) -> list[FAPOAction]:
        cap = self._limits.cell_prb_cap
        if cap is None or not actions:
            return actions

        def _min_of(act: FAPOAction) -> int:
            policy = state.slices.get(act.slice_id)
            return policy.min_prbs if policy else act.prbs

        total = sum(a.prbs for a in actions)
        if total <= cap:
            return actions

        headroom = [max(0, a.prbs - _min_of(a)) for a in actions]
        reducible = sum(headroom)
        excess = total - cap

        if reducible <= 0:
            report.scaled = True
            report.reasons.append(
                f"cell budget {cap} PRBs exceeded by minimum allocations; "
                f"leaving gNB to arbitrate"
            )
            return actions

        scaled: list[FAPOAction] = []
        remaining = excess
        for act, hr in zip(actions, headroom):
            cut = int(round(excess * (hr / reducible))) if reducible else 0
            cut = min(cut, hr, remaining)
            remaining -= cut
            scaled.append(
                FAPOAction(
                    slice_id=act.slice_id,
                    prbs=act.prbs - cut,
                    tx_power_dbm=act.tx_power_dbm,
                )
            )
        report.scaled = True
        report.reasons.append(
            f"scaled allocations down to respect cell budget of {cap} PRBs"
        )
        return scaled

    def _baseline_actions(
        self, state: RANState, report: SafetyReport
    ) -> list[FAPOAction]:
        actions = [
            FAPOAction(
                slice_id=policy.slice_id,
                prbs=policy.min_prbs,
                tx_power_dbm=policy.max_power_dbm,
            )
            for policy in state.slices.values()
        ]
        self._remember(actions)
        return actions

    def _remember(self, actions: list[FAPOAction]) -> None:
        for act in actions:
            self._last_prbs[act.slice_id] = act.prbs
            self._last_power[act.slice_id] = act.tx_power_dbm
