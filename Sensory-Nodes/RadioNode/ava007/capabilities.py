"""AVA007 capability registry.

AVA doesn't need to know anything about srsRAN, PRBs, Lyapunov queues,
SDR drivers, etc. It sees capabilities by name and invokes them.
"""


class CapabilityRegistry:

    def __init__(self):
        self._capabilities = {}

    def register(self, capability):
        self._capabilities[capability.name] = capability

    def get(self, name):
        return self._capabilities[name]

    def names(self):
        return tuple(self._capabilities)
