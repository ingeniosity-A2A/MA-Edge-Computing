#!/usr/bin/env python3
"""Cross-language interop check: real Python SRSRANAdapter <-> real C++ FAPO control server.

Drives the full FAPO v1 protocol (hello / get_telemetry / apply / reset) against the
real `fapo_control_server` compiled inside the srsRAN Project tree (fixture binary
`fapo_interop_server`, see tests/unittests/scheduler/fapo/).

Usage:
    python scripts/interop_check.py /path/to/fapo_interop_server
"""

import asyncio
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ran_capability.fapo import FAPOAction  # noqa: E402
from ran_capability.srsran.control_socket_adapter import SRSRANAdapter  # noqa: E402

SOCK = "/tmp/fapo_interop_{}.sock".format(time.time_ns())


async def run_check(binary: str) -> bool:
    proc = subprocess.Popen(
        [binary, f"unix://{SOCK}", "60"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    ok = True
    try:
        # Wait for the socket.
        for _ in range(100):
            if Path(SOCK).exists():
                break
            if proc.poll() is not None:
                print("fixture died:", proc.communicate()[0])
                return False
            await asyncio.sleep(0.05)

        adapter = SRSRANAdapter(f"unix://{SOCK}", connect_timeout_s=3.0, request_timeout_s=2.0)

        hello = await adapter.hello()
        print("hello:", hello)
        ok &= hello.get("ok") is True and hello.get("server") == "srsran-fapo-control"

        state = await adapter.telemetry()
        print("telemetry:", state)
        ok &= state.telemetry is not None
        ok &= "sst2-sd0xa" in state.slices and "default" in state.slices
        pol = state.slices["sst2-sd0xa"]
        ok &= pol.min_prbs == 5 and pol.max_prbs == 20 and pol.priority == 8

        first = state.telemetry
        # Cell metrics derived from real counters: packet loss = 100/(900+100) = 0.1.
        ok &= abs(first.packet_loss - 0.1) < 1e-6
        ok &= first.available_prbs >= 0 and first.available_prbs <= 51

        # Apply a PRB raise within bounds.
        await adapter.apply([FAPOAction(slice_id="sst2-sd0xa", prbs=30, tx_power_dbm=19.0)])
        # Apply above cell capacity -> server clamps to 51.
        await adapter.apply([FAPOAction(slice_id="sst2-sd0xa", prbs=999, tx_power_dbm=19.0)])
        await asyncio.sleep(0.3)

        # Reset restores baseline (5..20 for the configured slice).
        await adapter._client.request("reset")

        await asyncio.sleep(0.3)
        await adapter.close()

        # Check the drain log: the scheduler side accepted the commands with clamped values.
        proc.send_signal(2)  # SIGINT
        out, _ = proc.communicate(timeout=10)
        print("--- fixture log ---")
        print(out)
        ok &= "APPLIED cell=0 slice=2 max_rbs=30" in out
        ok &= "APPLIED cell=0 slice=2 max_rbs=51" in out
        ok &= "APPLIED_RESET cell=0" in out
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            Path(SOCK).unlink()
        except FileNotFoundError:
            pass

    return ok


def main() -> int:
    binary = sys.argv[1] if len(sys.argv) > 1 else "fapo_interop_server"
    ok = asyncio.run(run_check(binary))
    print("INTEROP:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
