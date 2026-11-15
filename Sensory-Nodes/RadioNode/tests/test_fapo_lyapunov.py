"""LDPTRLQ Lyapunov engine properties: V operating point, virtual
queues (y, z, F), isolation defense, determinism, and the closed-loop
power-delay tradeoff over the digital twin."""

import asyncio
import math

from ran_capability.config import default_slice_policies
from ran_capability.fapo import FAPO, FAPOAction
from ran_capability.models import RANTelemetry, RANState, SliceTelemetry
from ran_capability.safety import SafetyEnvelope, SafetyLimits
from ran_capability.srsran.twin import SimulatedSRSRANAdapter

from test_fapo import make_policies, make_state


def make_per_slice_state(
    per_slice: dict[str, tuple[float, float, int]],
    policies: dict | None = None,
) -> RANState:
    """Build state with explicit per-slice telemetry (q, lat, used)."""
    t = RANTelemetry(
        timestamp=123.0,
        throughput_mbps=10.0,
        latency_ms=max((lat for _, lat, _ in per_slice.values()), default=0.0),
        packet_loss=0.0,
        queue_depth=max((q for q, _, _ in per_slice.values()), default=0.0),
        available_prbs=51,
        tx_power_dbm=23.0,
        spectral_efficiency=3.5,
        slices={
            sid: SliceTelemetry(queue_depth=q, latency_ms=lat, prbs_used=used)
            for sid, (q, lat, used) in per_slice.items()
        },
    )
    return RANState(telemetry=t, slices=policies or make_policies())


def test_v_raises_power_savings_at_fixed_state():
    # Same steady moderate-load state: the large-V operating point
    # discounts accumulated pressure -> fewer PRBs, less tx power.
    state = make_state(queue_depth=40.0, latency_ms=8.0)
    low_v = {a.slice_id: a for a in FAPO(V=1.0).optimize(state)}
    high_v = {a.slice_id: a for a in FAPO(V=100.0).optimize(state)}
    for sid in low_v:
        assert low_v[sid].prbs >= high_v[sid].prbs
        assert low_v[sid].tx_power_dbm >= high_v[sid].tx_power_dbm
    assert any(
        low_v[sid].tx_power_dbm > high_v[sid].tx_power_dbm for sid in low_v
    ), "V must strictly shift the operating point at moderate load"


def test_virtual_queues_decay_after_relief():
    fapo = FAPO(V=100.0)
    # sustained overload: latency 90 ms vs rll budget 10 ms
    for _ in range(30):
        fapo.optimize(make_state(queue_depth=100.0, latency_ms=90.0))
    snap = fapo.snapshot()
    assert max(q["y"] for q in snap.values()) > 0.0
    assert max(q["z"] for q in snap.values()) > 0.0

    # sustained relief: queues must drain (stability of the drift term)
    for _ in range(400):
        fapo.optimize(make_state(queue_depth=0.0, latency_ms=1.0))
    snap = fapo.snapshot()
    assert max(q["y"] for q in snap.values()) < 1.0
    assert max(q["z"] for q in snap.values()) < 1.0


def test_isolation_deficit_reacts_to_real_undergrant():
    # The scheduler grants rll 0 PRBs despite its guaranteed minimum
    # of 2: the F virtual queue must accumulate and drive the request
    # to the slice maximum.
    fapo = FAPO(V=100.0)
    actions = None
    for _ in range(30):
        actions = fapo.optimize(
            make_per_slice_state(
                {"rll": (10.0, 4.0, 0), "high_capacity": (10.0, 4.0, 8)}
            )
        )
    by_id = {a.slice_id: a for a in actions}
    assert by_id["rll"].prbs == 12
    assert fapo.snapshot()["rll"]["F"] > 0.0


def test_no_isolation_deficit_when_grants_cover_guarantee():
    fapo = FAPO(V=100.0)
    for _ in range(10):
        fapo.optimize(
            make_per_slice_state(
                {"rll": (10.0, 4.0, 4), "high_capacity": (10.0, 4.0, 8)}
            )
        )
    assert all(q["F"] == 0.0 for q in fapo.snapshot().values())


def test_power_stays_within_hard_backoff_window():
    fapo = FAPO(V=100.0)
    for queue, lat in ((0.0, 1.0), (35.0, 12.0), (70.0, 25.0), (100.0, 90.0)):
        for a in fapo.optimize(make_state(queue_depth=queue, latency_ms=lat)):
            pol = make_policies()[a.slice_id]
            assert pol.max_power_dbm - 3.0 - 1e-9 <= a.tx_power_dbm <= pol.max_power_dbm


def test_engine_is_deterministic():
    def run() -> list[list[FAPOAction]]:
        fapo = FAPO(V=100.0)
        out = []
        for i in range(20):
            q = 20.0 + 3.0 * (i % 7)
            lat = 6.0 + (i % 5)
            out.append(fapo.optimize(make_state(queue_depth=q, latency_ms=lat)))
        return out

    assert run() == run()


def test_invalid_v_rejected():
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        try:
            FAPO(V=bad)
        except ValueError:
            continue
        raise AssertionError(f"V={bad!r} must be rejected")


def test_backward_compatible_constructor_weights():
    fapo = FAPO(queue_weight=1.0, latency_weight=2.0, power_weight=0.25)
    actions = fapo.optimize(make_state(queue_depth=50.0, latency_ms=12.0))
    assert len(actions) == 2
    # power_weight 0.25 == the 3 dB backoff ceiling of the original engine
    for a in actions:
        pol = make_policies()[a.slice_id]
        assert a.tx_power_dbm >= pol.max_power_dbm - 3.0 - 1e-9


def test_closed_loop_v_operating_point_over_twin():
    """The [O(1/V), O(V)] signature, measured on the closed loop.

    Same twin seed and traffic for both runs: the small-V engine holds
    maximum resources (delay-minimizing, power-hungry); the large-V
    engine settles at a lower-power operating point.
    """

    async def _run(v: float) -> tuple[float, float, bool]:
        policies = default_slice_policies()
        twin = SimulatedSRSRANAdapter(policies=policies, cell_prbs=51, seed=11)
        twin.set_backlog("rll", 40.0)
        twin.set_backlog("high_capacity", 55.0)
        twin.set_backlog("best_effort", 50.0)
        limits = SafetyLimits(
            cell_prb_cap=51, min_apply_interval_s=0.0, telemetry_max_age_s=0.5
        )
        envelope = SafetyEnvelope(FAPO(V=v), limits)

        powers: list[float] = []
        rll_prbs: list[int] = []
        in_bounds = True
        state = await twin.telemetry()
        for _ in range(150):
            actions = envelope.optimize(state)
            for a in actions:
                pol = state.slices[a.slice_id]
                if not (pol.min_prbs <= a.prbs <= pol.max_prbs):
                    in_bounds = False
            if actions:
                await twin.apply(actions)
            state = await twin.telemetry()
            if state.telemetry is not None:
                powers.append(state.telemetry.tx_power_dbm)
            rll_actions = [a for a in actions if a.slice_id == "rll"]
            if rll_actions:
                rll_prbs.append(rll_actions[0].prbs)

        assert in_bounds
        return (
            sum(powers) / len(powers),
            sum(rll_prbs) / max(1, len(rll_prbs)),
            True,
        )

    mean_power_v1, mean_rll_v1, _ = asyncio.run(_run(1.0))
    mean_power_v100, mean_rll_v100, _ = asyncio.run(_run(100.0))

    assert math.isfinite(mean_power_v1) and math.isfinite(mean_power_v100)
    # large V -> measurably less transmit power
    assert mean_power_v100 < mean_power_v1
    # ... and small V -> at least as many PRBs for the RLL slice
    assert mean_rll_v1 >= mean_rll_v100
