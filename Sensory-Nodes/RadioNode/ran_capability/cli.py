"""Run the FAPO control loop from the command line.

Modes:
  --twin                 run against the in-process digital twin
  --endpoint tcp://...   run against the patched gNB control socket

Examples:
  python bootstrap.py --twin
  python tools/fake_srsran.py --endpoint tcp://127.0.0.1:9001 &
  python bootstrap.py --endpoint tcp://127.0.0.1:9001
"""

import asyncio
import logging
import signal

from .config import DEFAULT_CELL_PRBS, default_slice_policies
from .control_loop import ControlLoop
from .capability import RANCapability
from .fapo import FAPO
from .safety import SafetyEnvelope, SafetyLimits
from .srsran.control_socket_adapter import SRSRANAdapter
from .srsran.twin import SimulatedSRSRANAdapter

logger = logging.getLogger(__name__)


def build_registry(
    endpoint: str | None = None,
    use_twin: bool = False,
    cell_prbs: int = DEFAULT_CELL_PRBS,
    fapo_v: float = 100.0,
):
    """Wire the RAN Capability exactly as in the architecture note:

        registry = CapabilityRegistry()
        ran = RANCapability(adapter=..., optimizer=SafetyEnvelope(FAPO(), limits))
        registry.register(ran)

    AVA007 only ever sees `registry.get("ran")`; srsRAN specifics stay
    inside the capability. The only delta from the original note is the
    SafetyEnvelope decorating FAPO — same optimize() contract.
    """
    policies = default_slice_policies()
    if use_twin or not endpoint:
        adapter = SimulatedSRSRANAdapter(policies=policies, cell_prbs=cell_prbs)
    else:
        adapter = SRSRANAdapter(endpoint)

    limits = SafetyLimits(cell_prb_cap=cell_prbs)
    optimizer = SafetyEnvelope(FAPO(V=fapo_v), limits)
    capability = RANCapability(adapter=adapter, optimizer=optimizer)

    from ava007.capabilities import CapabilityRegistry

    registry = CapabilityRegistry()
    registry.register(capability)
    return registry, capability


async def _run(args) -> None:
    registry, capability = build_registry(
        endpoint=args.endpoint,
        use_twin=args.twin,
        cell_prbs=args.cell_prbs,
        fapo_v=args.fapo_v,
    )

    hello = getattr(capability.adapter, "hello", None)
    if hello is not None:
        try:
            info = await hello()
            logger.info("gNB control server: %s", info)
        except Exception as exc:  # non-fatal: the loop will retry anyway
            logger.warning("gNB hello probe failed (%s); continuing", exc)

    control = ControlLoop(registry.get("ran"), period_s=args.period)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-Unix
            pass
    await control.run(stop)

    close = getattr(capability.adapter, "close", None)
    if close is not None:
        await close()


def main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="fapo-loop",
        description="Run the FAPO RAN capability control loop.",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="gNB control socket: tcp://host:port or unix:///path/to/sock",
    )
    parser.add_argument(
        "--twin",
        action="store_true",
        help="run against the in-process digital twin (no SDR needed)",
    )
    parser.add_argument(
        "--period", type=float, default=1.0, help="control loop period in seconds"
    )
    parser.add_argument(
        "--cell-prbs", type=int, default=DEFAULT_CELL_PRBS, help="cell PRB budget"
    )
    parser.add_argument(
        "--fapo-v",
        type=float,
        default=100.0,
        help=(
            "Lyapunov operating point V: the power-delay tradeoff weight. "
            "Higher V favours transmit-power savings (longer tolerated "
            "queues), lower V favours minimal delay (max resources). "
            "Default: 100"
        ),
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    main()
