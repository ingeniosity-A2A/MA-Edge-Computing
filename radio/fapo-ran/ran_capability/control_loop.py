"""Async control loop: observe -> optimize -> apply at a fixed period.

The loop is failure-isolated by design: any exception from the
capability (adapter unavailable, protocol error, timeout) is caught,
counted, and retried with exponential backoff. Consecutive failures
never crash the loop — the safety envelope's watchdog independently
reverts the radio to baseline if telemetry stops flowing.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LoopStats:
    cycles: int = 0
    applies: int = 0
    errors: int = 0
    consecutive_errors: int = 0
    degraded_cycles: int = 0
    last_result: dict | None = None
    last_error: str | None = None
    started_at: float | None = None
    recent_cycle_durations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cycles": self.cycles,
            "applies": self.applies,
            "errors": self.errors,
            "consecutive_errors": self.consecutive_errors,
            "degraded_cycles": self.degraded_cycles,
            "last_error": self.last_error,
        }


class ControlLoop:
    def __init__(self, capability, period_s: float = 1.0, max_backoff_s: float = 30.0):
        if period_s <= 0:
            raise ValueError("period_s must be positive")
        self._capability = capability
        self._period_s = period_s
        self._max_backoff_s = max_backoff_s
        self.stats = LoopStats()

    async def run(self, stop: asyncio.Event) -> None:
        self.stats.started_at = time.time()
        logger.info(
            "control loop started: period=%.2fs capability=%r",
            self._period_s,
            self._capability.name,
        )
        while not stop.is_set():
            t0 = time.monotonic()
            try:
                result = await self._capability.optimize()
                self.stats.cycles += 1
                self.stats.consecutive_errors = 0
                self.stats.last_result = result
                if result.get("actions"):
                    self.stats.applies += 1
                    logger.info(
                        "cycle %d applied: %s",
                        self.stats.cycles,
                        json.dumps(result["actions"]),
                    )
                else:
                    logger.debug("cycle %d: no actions", self.stats.cycles)

                report = getattr(self._capability.optimizer, "last_report", None)
                if report is not None:
                    if report.degraded:
                        self.stats.degraded_cycles += 1
                        logger.warning(
                            "cycle %d degraded: %s",
                            self.stats.cycles,
                            "; ".join(report.reasons),
                        )
                    elif report.rate_limited:
                        logger.debug(
                            "cycle %d rate-limited: %s",
                            self.stats.cycles,
                            "; ".join(report.reasons),
                        )
            except Exception as exc:  # failure isolation
                self.stats.errors += 1
                self.stats.consecutive_errors += 1
                self.stats.last_error = f"{type(exc).__name__}: {exc}"
                backoff = min(
                    self._max_backoff_s,
                    self._period_s * (2 ** min(self.stats.consecutive_errors - 1, 5)),
                )
                logger.error(
                    "cycle failed (%s); retrying in %.1fs",
                    self.stats.last_error,
                    backoff,
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                continue

            dt = time.monotonic() - t0
            self.stats.recent_cycle_durations.append(dt)
            if len(self.stats.recent_cycle_durations) > 100:
                self.stats.recent_cycle_durations.pop(0)
            sleep_for = max(0.0, self._period_s - dt)
            try:
                await asyncio.wait_for(stop.wait(), timeout=sleep_for)
            except asyncio.TimeoutError:
                pass
        logger.info(
            "control loop stopped: %s", json.dumps(self.stats.to_dict())
        )

    async def run_for(self, seconds: float) -> LoopStats:
        """Convenience for tests and one-shot experiments."""
        stop = asyncio.Event()
        task = asyncio.create_task(self.run(stop))
        await asyncio.sleep(seconds)
        stop.set()
        await task
        return self.stats
