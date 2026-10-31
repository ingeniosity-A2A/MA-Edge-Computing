import time

import pytest

from ran_capability.fapo import FAPO, FAPOAction
from ran_capability.models import RANState, RANTelemetry, SlicePolicy, SliceType
from ran_capability.safety import SafetyEnvelope, SafetyLimits


def make_policies():
    return {
        "rll": SlicePolicy("rll", SliceType.RLL, min_prbs=2, max_prbs=12,
                           max_latency_ms=10.0, max_power_dbm=21.0, priority=1),
        "high_capacity": SlicePolicy("high_capacity", SliceType.HIGH_CAPACITY,
                                     min_prbs=4, max_prbs=24, max_latency_ms=20.0,
                                     max_power_dbm=23.0, priority=2),
    }


def make_state(policies=None, ts=None, queue_depth=50.0, latency_ms=30.0):
    t = RANTelemetry(
        timestamp=ts if ts is not None else time.time(),
        throughput_mbps=10.0, latency_ms=latency_ms, packet_loss=0.0,
        queue_depth=queue_depth, available_prbs=51, tx_power_dbm=23.0,
        spectral_efficiency=3.5,
    )
    return RANState(telemetry=t, slices=policies or make_policies())


class StubOptimizer:
    """FAPO stand-in returning canned actions (bypasses real logic)."""

    def __init__(self, actions):
        self.actions = list(actions)

    def optimize(self, state):
        return list(self.actions)


def loose_limits(**overrides):
    defaults = dict(
        max_prb_step_frac=1.0,     # no ramp restriction
        max_power_step_db=100.0,   # no power ramp restriction
        min_apply_interval_s=0.0,  # no rate limiting
        telemetry_max_age_s=3.0,
        cell_prb_cap=None,
    )
    defaults.update(overrides)
    return SafetyLimits(**defaults)


def test_unknown_slice_actions_are_dropped():
    inner = StubOptimizer([FAPOAction("ghost", prbs=10, tx_power_dbm=20.0)])
    env = SafetyEnvelope(inner, loose_limits())
    out = env.optimize(make_state())
    assert out == []
    assert env.last_report.dropped == 1


def test_hard_clamps_enforce_policy_bounds():
    inner = StubOptimizer([
        FAPOAction("rll", prbs=999, tx_power_dbm=99.0),
        FAPOAction("high_capacity", prbs=0, tx_power_dbm=-50.0),
    ])
    env = SafetyEnvelope(inner, loose_limits(min_tx_power_dbm=0.0))
    out = {a.slice_id: a for a in env.optimize(make_state())}
    assert out["rll"].prbs == 12
    assert out["rll"].tx_power_dbm == pytest.approx(21.0)
    assert out["high_capacity"].prbs == 4
    assert out["high_capacity"].tx_power_dbm == pytest.approx(0.0)
    assert env.last_report.clamped >= 2


def test_prb_ramp_limit_ratchets_from_baseline():
    inner = StubOptimizer([FAPOAction("rll", prbs=12, tx_power_dbm=21.0)])
    env = SafetyEnvelope(inner, loose_limits(max_prb_step_frac=0.25))  # step = 3
    seen = []
    for _ in range(5):
        (act,) = env.optimize(make_state())
        seen.append(act.prbs)
    # 2 -> 5 -> 8 -> 11 -> 12 (clamped at max)
    assert seen == [5, 8, 11, 12, 12]


def test_power_ramp_limit():
    inner = StubOptimizer([FAPOAction("rll", prbs=2, tx_power_dbm=15.0)])
    env = SafetyEnvelope(inner, loose_limits(max_power_step_db=2.0))
    (act,) = env.optimize(make_state())
    # cold start from max_power 21.0, max drop 2 dB per cycle
    assert act.tx_power_dbm == pytest.approx(19.0)


def test_stale_telemetry_reverts_to_baseline_bypassing_rate_limit():
    inner = StubOptimizer([FAPOAction("rll", prbs=12, tx_power_dbm=15.0)])
    env = SafetyEnvelope(inner, loose_limits(min_apply_interval_s=60.0))
    old = time.time() - 10.0
    out = env.optimize(make_state(ts=old))
    by_id = {a.slice_id: a for a in out}
    assert by_id["rll"].prbs == 2
    assert by_id["rll"].tx_power_dbm == pytest.approx(21.0)
    assert env.last_report.degraded
    assert env.last_report.stale_age_s >= 10.0


def test_rate_limit_holds_previous_policy():
    inner = StubOptimizer([FAPOAction("rll", prbs=8, tx_power_dbm=20.0)])
    env = SafetyEnvelope(inner, loose_limits(min_apply_interval_s=60.0))
    first = env.optimize(make_state())
    assert first, "first call must not be rate limited"
    second = env.optimize(make_state())
    assert second == []
    assert env.last_report.rate_limited


def test_cell_budget_scales_down_proportionally():
    inner = StubOptimizer([
        FAPOAction("rll", prbs=12, tx_power_dbm=21.0),
        FAPOAction("high_capacity", prbs=24, tx_power_dbm=23.0),
    ])
    env = SafetyEnvelope(inner, loose_limits(cell_prb_cap=20))
    out = env.optimize(make_state())
    total = sum(a.prbs for a in out)
    by_id = {a.slice_id: a for a in out}
    assert total <= 20
    assert by_id["rll"].prbs >= 2
    assert by_id["high_capacity"].prbs >= 4
    assert env.last_report.scaled
    # headroom-proportional cut: rll headroom 10, hc headroom 20 -> excess 16
    assert by_id["rll"].prbs == 12 - 5
    assert by_id["high_capacity"].prbs == 24 - 11


def test_optimizer_exception_triggers_baseline_revert():
    class Exploding:
        def optimize(self, state):
            raise RuntimeError("boom")

    env = SafetyEnvelope(Exploding(), loose_limits())
    out = {a.slice_id: a for a in env.optimize(make_state())}
    assert out["rll"].prbs == 2
    assert out["rll"].tx_power_dbm == pytest.approx(21.0)
    assert out["high_capacity"].prbs == 4
    assert env.last_report.degraded


def test_no_telemetry_returns_nothing():
    env = SafetyEnvelope(FAPO(), loose_limits())
    state = RANState(telemetry=None, slices=make_policies())
    assert env.optimize(state) == []
    assert not env.last_report.degraded


def test_real_fapo_flows_through_envelope():
    env = SafetyEnvelope(FAPO(), loose_limits(cell_prb_cap=51))
    out = env.optimize(make_state(queue_depth=90.0, latency_ms=45.0))
    assert len(out) == 2
    by_id = {a.slice_id: a for a in out}
    for sid, pol in make_policies().items():
        assert pol.min_prbs <= by_id[sid].prbs <= pol.max_prbs
