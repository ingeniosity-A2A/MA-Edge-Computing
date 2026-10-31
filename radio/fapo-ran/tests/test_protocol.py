import pytest

from ran_capability.protocol import (
    CAPABILITIES,
    ERR_UNKNOWN_OP,
    OP_APPLY,
    OP_HELLO,
    OP_PING,
    OP_RESET,
    OP_TELEMETRY,
    PROTOCOL_VERSION,
    SERVER_NAME,
    parse_endpoint,
)


def test_parse_tcp_endpoint():
    kind, target = parse_endpoint("tcp://127.0.0.1:9001")
    assert kind == "tcp"
    assert target == ("127.0.0.1", 9001)


def test_parse_tcp_endpoint_hostname():
    kind, target = parse_endpoint("tcp://gnb-lab.local:5555")
    assert kind == "tcp"
    assert target == ("gnb-lab.local", 5555)


def test_parse_unix_endpoint():
    kind, target = parse_endpoint("unix:///var/run/fapo-gnb.sock")
    assert kind == "unix"
    assert target == "/var/run/fapo-gnb.sock"


@pytest.mark.parametrize("bad", [
    "127.0.0.1:9001",          # missing scheme (the original note used http://)
    "http://127.0.0.1:9000",   # unsupported scheme
    "tcp://9001",              # no host
    "tcp://host:notaport",     # bad port
    "tcp://host:99999",        # out of range
    "unix://",                 # no path
])
def test_parse_endpoint_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_endpoint(bad)


def test_protocol_constants_are_v1_shape():
    assert PROTOCOL_VERSION == 1
    assert OP_TELEMETRY == "get_telemetry"
    assert OP_APPLY == "apply"
    assert OP_RESET == "reset"
    assert OP_HELLO == "hello"
    assert OP_PING == "ping"
    assert ERR_UNKNOWN_OP == "unknown_op"
    assert SERVER_NAME == "srsran-fapo-control"
    assert set(CAPABILITIES) == {"telemetry", "apply", "reset"}
