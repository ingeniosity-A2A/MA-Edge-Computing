from abc import ABC, abstractmethod

from .fapo import FAPOAction
from .models import RANState


class RANAdapter(ABC):

    @abstractmethod
    async def telemetry(self) -> RANState:
        raise NotImplementedError

    @abstractmethod
    async def apply(self, actions: list[FAPOAction]) -> None:
        raise NotImplementedError


# The original NotImplementedError stub has been replaced by the
# control-socket implementation in .srsran.control_socket_adapter.
# Re-exported so existing imports keep working unchanged:
#   from ran_capability.adapter import SRSRANAdapter
from .srsran.control_socket_adapter import SRSRANAdapter  # noqa: E402

__all__ = ["RANAdapter", "SRSRANAdapter"]
