"""Shared runtime defaults for the RAN Capability.

The slice policies below are the *static* gNB-side configuration the
testbed starts from; the patched srsRAN server reports the same values
back in every telemetry response, and the safety watchdog reverts to
them when telemetry goes stale.
"""

from .models import SlicePolicy, SliceType

DEFAULT_CELL_PRBS = 51  # 20 MHz NR, 30 kHz SCS: up to 51 PRBs


def default_slice_policies() -> dict[str, SlicePolicy]:
    return {
        "rll": SlicePolicy(
            slice_id="rll",
            slice_type=SliceType.RLL,
            min_prbs=2,
            max_prbs=12,
            max_latency_ms=10.0,
            max_power_dbm=21.0,
            priority=1,
        ),
        "high_capacity": SlicePolicy(
            slice_id="high_capacity",
            slice_type=SliceType.HIGH_CAPACITY,
            min_prbs=4,
            max_prbs=24,
            max_latency_ms=20.0,
            max_power_dbm=23.0,
            priority=2,
        ),
        "best_effort": SlicePolicy(
            slice_id="best_effort",
            slice_type=SliceType.BEST_EFFORT,
            min_prbs=2,
            max_prbs=15,
            max_latency_ms=100.0,
            max_power_dbm=20.0,
            priority=3,
        ),
    }
