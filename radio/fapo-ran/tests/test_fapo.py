from dataclasses import dataclass, field

import pytest

from ran_capability.fapo import FAPO, FAPOAction
from ran_capability.models import RANState, RANTelemetry, SlicePolicy, SliceType


def make_policies() -> dict[str, SlicePolicy]:
    return {
        "rll": SlicePolicy("rll", SliceType.RLL, min_prbs=2, max_prbs=12,
                           max_latency_ms=10.0, max_power_dbm=21.0, priority=1),
        "high_capacity": SlicePolicy("high_capacity", SliceType.HIGH_CAPACITY,
                                     min_prbs=4, max_prbs=24, max_latency_ms=20.0,
                                     max_power_dbm=23.0, priority=2),
    }


def make_state(queue_depth: float, latency_ms: float,
               policies: dict[str, SlicePolicy] | None = None) -> RANState:
    t = RANTelemetry(
        timestamp=123.0, throughput_mbps=10.0, latency_ms=latency_ms,
        packet_loss=0.0, queue_depth=queue_depth, available_prbs=51,
        tx_power_dbm=23.0, spectral_efficiency=3.5,
    )
    return RANState(telemetry=t, slices=policies or make_policies())


def test_no_telemetry_produces_no_actions():
    state = RANState(telemetry=None, slices=make_policies())
    assert FAPO().optimize(state) == []


def test_actions_within_policy_bounds():
    fapo = FAPO()
    for queue in (0.0, 25.0, 50.0, 80.0, 120.0):
        actions = fapo.optimize(make_state(queue_depth=queue, latency_ms=5.0))
        by_id = {a.slice_id: a for a in actions}
        for sid, pol in make_policies().items():
            assert pol.min_prbs <= by_id[sid].prbs <= pol.max_prbs
            assert by_id[sid].tx_power_dbm <= pol.max_power_dbm


def test_full_pressure_hits_upper_bound_and_max_power():
    # queue 100 + latency blowout far beyond max_latency -> urgency saturates at 1.0
    actions = FAPO().optimize(make_state(queue_depth=100.0, latency_ms=90.0))
    by_id = {a.slice_id: a for a in actions}
    assert by_id["rll"].prbs == 12
    assert by_id["rll"].tx_power_dbm == pytest.approx(21.0)
    assert by_id["high_capacity"].prbs == 24


def test_zero_pressure_sits_at_lower_bound_with_power_backoff():
    # queue 0, latency below every max_latency -> urgency ~ 0
    actions = FAPO().optimize(make_state(queue_depth=0.0, latency_ms=1.0))
    by_id = {a.slice_id: a for a in actions}
    assert by_id["rll"].prbs == 2
    # power = max_power - (1-urgency)*3
    assert by_id["rll"].tx_power_dbm == pytest.approx(21.0 - 3.0)
    assert by_id["high_capacity"].tx_power_dbm == pytest.approx(23.0 - 3.0)


def test_urgency_is_monotonic_in_queue_depth():
    fapo = FAPO()
    low = {a.slice_id: a.prbs for a in fapo.optimize(make_state(10.0, 1.0))}
    high = {a.slice_id: a.prbs for a in fapo.optimize(make_state(90.0, 1.0))}
    assert high["rll"] > low["rll"]
    assert high["high_capacity"] > low["high_capacity"]


def test_latency_pressure_is_per_slice():
    # q=0, flat latency 50 ms: rll (budget 10 ms) accumulates more
    # latency-budget violation than high_capacity (budget 20 ms).
    # z_rll = 50-10-0.5 = 39.5 -> w = 2*39.5 = 79  -> rho = 79/200 = 0.395
    # z_hc  = 50-20-0.5 = 29.5 -> w = 2*29.5 = 59  -> rho = 59/200 = 0.295
    actions = FAPO().optimize(make_state(queue_depth=0.0, latency_ms=50.0))
    by_id = {a.slice_id: a for a in actions}
    assert by_id["rll"].prbs == pytest.approx(6)
    assert by_id["high_capacity"].prbs == pytest.approx(10)
    # under latency pressure the power backoff eases from its floor
    assert 18.0 < by_id["rll"].tx_power_dbm < 21.0


def test_fapo_action_dataclass_shape():
    act = FAPOAction(slice_id="rll", prbs=5, tx_power_dbm=20.0)
    assert act.slice_id == "rll" and act.prbs == 5
    assert act.tx_power_dbm == pytest.approx(20.0)
