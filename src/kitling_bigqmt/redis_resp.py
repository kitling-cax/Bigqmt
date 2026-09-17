"""Small RESP2 client for the project-owned local Redis instance.

It deliberately implements only the commands the read-only RPC client needs.
Keeping this dependency-free avoids coupling the host gateway to QMT's embedded
Python packages.
"""

from __future__ import annotations

import socket
from typing import Any


class RedisProtocolError(RuntimeError):
    pass


class RedisRespClient:
    def __init__(self, host: str, port: int, db: int, password: str = "", timeout: float = 5.0):
        self.host = host
        self.port = int(port)
        self.db = int(db)
        self.password = password or ""
        self.timeout = float(timeout)

    @staticmethod
    def _encode(parts: tuple[Any, ...]) -> bytes:
        encoded = []
        for part in parts:
            value = str(part).encode("utf-8")
            encoded.append(b"$" + str(len(value)).encode("ascii") + b"\r\n" + value + b"\r\n")
        return b"*" + str(len(encoded)).encode("ascii") + b"\r\n" + b"".join(encoded)

    @staticmethod
    def _read_line(stream) -> bytes:
        line = stream.readline()
        if not line.endswith(b"\r\n"):
            raise RedisProtocolError("incomplete Redis response")
        return line[:-2]

    @classmethod
    def _read_response(cls, stream):
        prefix = stream.read(1)
        if not prefix:
            raise RedisProtocolError("Redis closed the connection")
        if prefix == b"+":
            return cls._read_line(stream).decode("utf-8")
        if prefix == b"-":
            raise RedisProtocolError(cls._read_line(stream).decode("utf-8", "replace"))
        if prefix == b":":
            return int(cls._read_line(stream))
        if prefix == b"$":
            length = int(cls._read_line(stream))
            if length == -1:
                return None
            payload = stream.read(length)
            if len(payload) != length or stream.read(2) != b"\r\n":
                raise RedisProtocolError("incomplete Redis bulk response")
            return payload.decode("utf-8")
        if prefix == b"*":
            length = int(cls._read_line(stream))
            if length == -1:
                return None
            return [cls._read_response(stream) for _ in range(length)]
        raise RedisProtocolError("unsupported Redis response prefix: %r" % prefix)

    def command(self, *parts: Any):
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            with sock.makefile("rwb") as stream:
                if self.password:
                    stream.write(self._encode(("AUTH", self.password)))
                    stream.flush()
                    self._read_response(stream)
                stream.write(self._encode(("SELECT", self.db)))
                stream.flush()
                self._read_response(stream)
                stream.write(self._encode(tuple(parts)))
                stream.flush()
                return self._read_response(stream)
