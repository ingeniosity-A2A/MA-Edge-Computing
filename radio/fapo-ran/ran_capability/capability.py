"""The Capability itself: AVA007's entire view of the radio.

Kept exactly as designed in the architecture note. FAPO and the
adapter are injected; the capability owns the observe -> optimize ->
apply cycle and exposes one async entrypoint: optimize().
"""

from .adapter import RANAdapter
from .fapo import FAPO
from .models import RANState


class RANCapability:
    """
    Exoskeleton Capability.

    AVA007 can invoke this capability.
    The capability owns its RAN-specific implementation.
    """

    name = "ran"

    def __init__(self, adapter: RANAdapter, optimizer: FAPO):
        self.adapter = adapter
        self.optimizer = optimizer

    async def observe(self) -> RANState:
        return await self.adapter.telemetry()

    async def optimize(self) -> dict:
        state = await self.observe()

        actions = self.optimizer.optimize(state)

        if actions:
            await self.adapter.apply(actions)

        return {
            "capability": self.name,
            "actions": [
                {
                    "slice_id": a.slice_id,
                    "prbs": a.prbs,
                    "tx_power_dbm": a.tx_power_dbm,
                }
                for a in actions
            ],
        }
