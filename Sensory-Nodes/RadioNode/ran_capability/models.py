from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class SliceType(str, Enum):
    RLL = "rll"
    HIGH_CAPACITY = "high_capacity"
    BEST_EFFORT = "best_effort"


@dataclass
class SlicePolicy:
    slice_id: str
    slice_type: SliceType
    min_prbs: int
    max_prbs: int
    max_latency_ms: float
    max_power_dbm: float
    priority: int


@dataclass
class SliceTelemetry:
    """Per-slice scheduler metrics as reported by the patched gNB.

    These come straight from the srsRAN inter-slice scheduler state
    (pending bytes, allocation EWMA, HARQ loss). The flat RANTelemetry
    fields remain the worst-slice aggregation for the frozen contract;
    the Lyapunov engine consumes the per-slice view.
    """

    queue_depth: float = 0.0        # 0..100 congestion percentage
    latency_ms: float = 0.0
    prbs_used: int = 0              # actual scheduler grant (RRM)
    packet_loss: float = 0.0


@dataclass
class RANTelemetry:
    timestamp: float
    throughput_mbps: float
    latency_ms: float
    packet_loss: float
    queue_depth: float
    available_prbs: int
    tx_power_dbm: float
    spectral_efficiency: float
    slices: Dict[str, SliceTelemetry] = field(default_factory=dict)


@dataclass
class RANState:
    telemetry: Optional[RANTelemetry] = None
    slices: Dict[str, SlicePolicy] = field(default_factory=dict)
