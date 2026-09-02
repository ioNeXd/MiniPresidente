import socket
import struct

import pytest

from app.config import MAX_FRAME_BYTES
from app.stream_client import StreamClient


class FakeSocket:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def recv(self, n):
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) > n:
            self._chunks.insert(0, chunk[n:])
            chunk = chunk[:n]
        return chunk

    def close(self):
        self.closed = True


@pytest.fixture
def fake_socket_factory(monkeypatch):
    created = {}

    def factory(*args, **kwargs):
        payload = created.get("payload", b"x" * 8)
        sock = FakeSocket([struct.pack(">I", len(payload)), payload])
        created["sock"] = sock
        return sock

    monkeypatch.setattr(socket, "create_connection", factory)
    return created


def test_stream_client_accepts_frame_within_limit(fake_socket_factory):
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=seen.append)
    client._running = True
    client._run()
    assert seen == [b"x" * 8]


def test_stream_client_accepts_exact_max_size_frame(monkeypatch):
    payload = b"x" * MAX_FRAME_BYTES
    fake = FakeSocket([struct.pack(">I", len(payload)), payload])
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: fake)
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=seen.append)
    client._running = True
    client._run()
    assert seen == [payload]


def test_stream_client_rejects_too_large_frame(monkeypatch):
    payload = b"x" * (MAX_FRAME_BYTES + 1)
    fake = FakeSocket([struct.pack(">I", len(payload)), payload])
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: fake)
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=seen.append)
    client._running = True
    client._run()
    assert seen == []
    assert fake.closed is True or fake.timeout is not None


def test_stream_client_rejects_zero_size_frame(monkeypatch):
    fake = FakeSocket([struct.pack(">I", 0)])
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: fake)
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=seen.append)
    client._running = True
    client._run()
    assert seen == []


def test_stream_client_handles_partial_header_without_crash(monkeypatch):
    fake = FakeSocket([b"\x00\x00\x00"])
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: fake)
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=seen.append)
    client._running = True
    client._run()
    assert seen == []


def test_stream_client_handles_disconnect_mid_payload(monkeypatch):
    payload = b"x" * 32
    fake = FakeSocket([struct.pack(">I", len(payload)), b"abc"])
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: fake)
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=seen.append)
    client._running = True
    client._run()
    assert seen == []
