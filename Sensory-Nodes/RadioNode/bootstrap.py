"""Runtime wiring for the Exoskeleton RAN Capability.

Registration mirrors the architecture note: AVA007 only ever sees the
CapabilityRegistry; srsRAN specifics stay inside the capability.

    AVA invokes:  result = await registry.get("ran").optimize()

Default wiring runs the digital twin so the whole stack is runnable on
a laptop. Point --endpoint at the patched gNB control socket once the
SDR testbed is up (see srsran-patch/INTEGRATION.md).
"""

from ran_capability.cli import build_registry

# Module-level registry, matching the original bootstrap snippet.
# Swap to build_registry(endpoint="tcp://127.0.0.1:9001") for the real gNB.
registry = build_registry(use_twin=True)

if __name__ == "__main__":
    from ran_capability.cli import main

    main()
