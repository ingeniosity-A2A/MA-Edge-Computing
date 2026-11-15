"""FAPO control protocol v1 (JSON Lines).

Framing: one UTF-8 JSON object per line, terminated by '\n'.
Transport: TCP (tcp://host:port) or Unix domain socket (unix:///path).

Requests (client -> gNB control server):

    {"v":1,"id":1,"op":"hello"}
    {"v":1,"id":2,"op":"get_telemetry"}
    {"v":1,"id":3,"op":"apply","actions":[
        {"slice_id":"rll","prbs":8,"tx_power_dbm":19.0}]}
    {"v":1,"id":4,"op":"reset","mode":"baseline"}
    {"v":1,"id":5,"op":"ping"}

Responses (gNB -> client). Successful responses carry "ok": true plus
the op-specific payload; failures carry "ok": false and an "error"
object {"code", "message"}:

    {"v":1,"id":2,"ok":true,"ts":1730000000.5,
     "cell":{"prbs_total":51,"available_prbs":39,"throughput_mbps":18.4,
             "latency_ms":12.3,"packet_loss":0.001,"tx_power_dbm":21.5,
             "spectral_efficiency":3.5},
     "slices":{"rll":{"queue_depth":42.0,"latency_ms":23.3,
                      "prbs_used":4,"packet_loss":0.0}},
     "policies":{"rll":{"slice_type":"rll","min_prbs":2,"max_prbs":12,
                        "max_latency_ms":10.0,"max_power_dbm":21.0,
                        "priority":1}}}

    {"v":1,"id":3,"ok":true,"applied":[{...}],"rejected":[...]}

    {"v":1,"id":3,"ok":false,"error":{"code":"unknown_slice",
                                      "message":"no such slice: x"}}

`queue_depth` is a normalized congestion percentage (0..100), not raw
bits. `ts` is unix epoch seconds (float) and is what the safety
envelope uses as a staleness watchdog.
"""

PROTOCOL_VERSION = 1

OP_HELLO = "hello"
OP_TELEMETRY = "get_telemetry"
OP_APPLY = "apply"
OP_RESET = "reset"
OP_PING = "ping"

ERR_BAD_REQUEST = "bad_request"
ERR_UNKNOWN_OP = "unknown_op"
ERR_VERSION_MISMATCH = "version_mismatch"
ERR_NOT_READY = "not_ready"
ERR_UNKNOWN_SLICE = "unknown_slice"
ERR_OUT_OF_BOUNDS = "out_of_bounds"
ERR_INTERNAL = "internal"

SERVER_NAME = "srsran-fapo-control"
CAPABILITIES = ("telemetry", "apply", "reset")


class AdapterUnavailable(RuntimeError):
    """Transport-level failure: cannot connect, timeout, or dropped link."""


class ProtocolError(RuntimeError):
    """Peer spoke the protocol incorrectly or returned an error response."""


def parse_endpoint(endpoint: str):
    """Parse 'tcp://host:port' or 'unix:///path/to/sock'.

    Returns ("tcp", (host, port)) or ("unix", path).
    Raises ValueError for anything else.
    """
    if not isinstance(endpoint, str) or "://" not in endpoint:
        raise ValueError(
            f"endpoint must be 'tcp://host:port' or 'unix:///path', got {endpoint!r}"
        )
    scheme, _, rest = endpoint.partition("://")
    scheme = scheme.lower()
    if scheme == "tcp":
        host, sep, port_str = rest.rpartition(":")
        if not sep or not host:
            raise ValueError(f"tcp endpoint needs 'tcp://host:port', got {endpoint!r}")
        try:
            port = int(port_str)
        except ValueError as exc:
            raise ValueError(f"invalid port in endpoint {endpoint!r}") from exc
        if not (0 < port < 65536):
            raise ValueError(f"port out of range in endpoint {endpoint!r}")
        return "tcp", (host, port)
    if scheme == "unix":
        if not rest:
            raise ValueError(f"unix endpoint needs a path, got {endpoint!r}")
        return "unix", rest
    raise ValueError(f"unsupported endpoint scheme {scheme!r} in {endpoint!r}")
