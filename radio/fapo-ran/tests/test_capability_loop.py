"""Closed-loop tests: FAPO + SafetyEnvelope + RANCapability over the twin,
plus the failure-isolated control loop and the telemetry watchdog."""

import asyncio

import pytest

from ava007.capabilities import CapabilityRegistry
from ran_capability.capability import RANCapability
from ran_capability.config import default_slice_policies
from ran_capability.control_loop import ControlLoop
from ran_capability.fapo import FAPO
from ran_capability.safety import SafetyEnvelope, SafetyLimits
from ran_capability.srsran.twin import SimulatedSRSRANAdapter


def build_stack(period_s: float = 0.02):
    policies = default_slice_policies()
    twin = SimulatedSRSRANAdapter(policies=policies, cell_prbs=51, seed=11)
    # fast test settings: no rate limit, tight watchdog
    limits = SafetyLimits(
        cell_prb_cap=51,
        min_apply_interval_s=0.0,
        telemetry_max_age_s=0.5,
        max_prb_step_frac=0.25,
    )
    capability = RANCapability(adapter=twin, optimizer=SafetyEnvelope(FAPO(), limits))

    registry = CapabilityRegistry()
    registry.register(capability)
    return registry, capability, twin


def test_registry_exposes_only_the_capability_name():
    registry, _, _ = build_stack()
    assert registry.names() == ("ran",)
    assert registry.get("ran").name == "ran"


def test_closed_loop_stabilizes_queues():
    async def _main():
        registry, capability, twin = build_stack()
        twin.set_backlog("rll", 60.0)
        twin.set_backlog("high_capacity", 75.0)
        twin.set_backlog("best_effort", 70.0)
        initial = twin.queue_depths()

        loop = ControlLoop(registry.get("ran"), period_s=0.02)
        stats = await loop.run_for(1.2)

        assert stats.errors == 0, stats.last_error
        assert stats.applies >= 5, "FAPO should have applied policy repeatedly"

        final = twin.queue_depths()
        # the loop must have drained congestion: FAPO allocated PRBs and
        # the twin served bits in response
        assert max(final.values()) < max(initial.values()) * 0.6
        assert stats.degraded_cycles == 0

    asyncio.run(_main())


def test_watchdog_reverts_to_baseline_on_stale_telemetry():
    async def _main():
        registry, capability, twin = build_stack()
        twin.set_backlog("high_capacity", 80.0)

        loop = ControlLoop(registry.get("ran"), period_s=0.02)
        stop = asyncio.Event()
        task = asyncio.create_task(loop.run(stop))
        await asyncio.sleep(0.4)
        assert loop.stats.errors == 0

        # freeze the telemetry feed (SDR unplugged / gNB hung)
        twin.age_clock(5.0)
        await asyncio.sleep(0.2)

        envelope = capability.optimizer
        assert envelope.last_report.degraded
        assert envelope.last_report.stale_age_s >= 5.0
        # baseline = min PRBs, max power applied over the wire
        depths = twin.queue_depths()
        assert twin.applied_history, "baseline must have been applied"

        stop.set()
        await task
        assert loop.stats.degraded_cycles > 0

    asyncio.run(_main())


def test_capability_returns_serializable_result():
    async def _main():
        registry, capability, twin = build_stack()
        twin.set_backlog("rll", 70.0)
        result = await registry.get("ran").optimize()
        assert result["capability"] == "ran"
        for action in result["actions"]:
            assert set(action) == {"slice_id", "prbs", "tx_power_dbm"}
            assert isinstance(action["prbs"], int)

    asyncio.run(_main())


def test_adapter_outage_does_not_crash_the_loop():
    async def _main():
        policies = default_slice_policies()
        twin = SimulatedSRSRANAdapter(policies=policies, cell_prbs=51, seed=3)

        class FlakyAdapter:
            def __init__(self, inner):
                self._inner = inner
                self.calls = 0

            async def telemetry(self):
                self.calls += 1
                if self.calls <= 3:
                    raise ConnectionError("gNB socket down")
                return await self._inner.telemetry()

            async def apply(self, actions):
                return await self._inner.apply(actions)

        capability = RANCapability(
            adapter=FlakyAdapter(twin),
            optimizer=SafetyEnvelope(FAPO(), SafetyLimits(min_apply_interval_s=0.0)),
        )
        loop = ControlLoop(capability, period_s=0.01)
        stats = await loop.run_for(0.5)

        assert stats.errors >= 3
        assert stats.consecutive_errors == 0, "loop must recover after outage"
        assert stats.cycles > 0

    asyncio.run(_main())
