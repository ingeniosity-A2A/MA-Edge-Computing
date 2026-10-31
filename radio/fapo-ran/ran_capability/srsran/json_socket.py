"""Minimal async JSON-Lines socket client for the FAPO control protocol.

Stdlib only. One persistent connection with automatic reconnect on the
next request after any transport failure. Request/response correlation
is by monotonically increasing integer ids.
"""

import asyncio
import json
import logging

from ..protocol import (
    PROTOCOL_VERSION,
    AdapterUnavailable,
    ProtocolError,
    parse_endpoint,
)

logger = logging.getLogger(__name__)


class JsonSocketClient:
    def __init__(
        self,
        endpoint: str,
        connect_timeout_s: float = 2.0,
        request_timeout_s: float = 1.5,
    ):
        self._kind, self._target = parse_endpoint(endpoint)
        self._endpoint = endpoint
        self._connect_timeout_s = connect_timeout_s
        self._request_timeout_s = request_timeout_s
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = 1

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def _ensure_connected(self) -> None:
        if self._reader is not None and self._writer is not None:
            return
        try:
            if self._kind == "tcp":
                host, port = self._target
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), self._connect_timeout_s
                )
            else:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(self._target), self._connect_timeout_s
                )
            logger.debug("connected to %s", self._endpoint)
        except (asyncio.TimeoutError, OSError) as exc:
            self._reader = self._writer = None
            raise AdapterUnavailable(
                f"cannot connect to {self._endpoint}: {exc}"
            ) from exc

    async def request(self, op: str, payload: dict | None = None) -> dict:
        """Send one request and return the parsed response object.

        Raises AdapterUnavailable on transport problems (the connection
        is closed and a reconnect will be attempted next call) and
        ProtocolError on malformed/mismatched responses.
        """
        await self._ensure_connected()
        req_id = self._next_id
        self._next_id += 1

        req = {"v": PROTOCOL_VERSION, "id": req_id, "op": op}
        if payload:
            req.update(payload)
        line = (json.dumps(req, separators=(",", ":")) + "\n").encode("utf-8")

        try:
            self._writer.write(line)
            await asyncio.wait_for(self._writer.drain(), self._request_timeout_s)
            raw = await asyncio.wait_for(
                self._reader.readline(), self._request_timeout_s
            )
        except (
            asyncio.TimeoutError,
            asyncio.IncompleteReadError,
            ConnectionError,
            OSError,
        ) as exc:
            await self.close()
            raise AdapterUnavailable(
                f"transport failure during '{op}' on {self._endpoint}: {exc}"
            ) from exc

        if not raw:
            await self.close()
            raise AdapterUnavailable(
                f"peer closed connection during '{op}' on {self._endpoint}"
            )

        try:
            msg = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError(
                f"malformed response line from {self._endpoint}: {raw[:120]!r}"
            ) from exc

        if not isinstance(msg, dict):
            raise ProtocolError(f"response is not an object: {raw[:120]!r}")
        if msg.get("id") != req_id:
            raise ProtocolError(
                f"response id mismatch: sent {req_id}, got {msg.get('id')!r}"
            )
        return msg

    async def close(self) -> None:
        writer = self._writer
        self._reader = self._writer = None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
