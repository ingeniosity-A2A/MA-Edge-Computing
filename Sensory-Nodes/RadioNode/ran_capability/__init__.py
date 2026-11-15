"""Exoskeleton RAN Capability.

Boundary layout (see README.md):

    AVA007 / AMOS
          |  Capability API (registry.get("ran"))
          v
    RANCapability        <- capability.py
      |- FAPO            <- fapo.py           (policy optimizer)
      |- SafetyEnvelope  <- safety.py         (bounds, ramp, watchdog)
      |- RANAdapter      <- adapter.py        (transport boundary)
           |- SRSRANAdapter / SimulatedSRSRANAdapter
                v
             srsRAN gNB  (control socket, see srsran-patch/)
"""

from .adapter import RANAdapter, SRSRANAdapter
from .capability import RANCapability
from .fapo import FAPO, FAPOAction
from .models import RANState, RANTelemetry, SlicePolicy, SliceType
from .safety import SafetyEnvelope, SafetyLimits, SafetyReport

__all__ = [
    "RANAdapter",
    "SRSRANAdapter",
    "RANCapability",
    "FAPO",
    "FAPOAction",
    "RANState",
    "RANTelemetry",
    "SlicePolicy",
    "SliceType",
    "SafetyEnvelope",
    "SafetyLimits",
    "SafetyReport",
]
