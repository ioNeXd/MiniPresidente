import socket
import struct

import pytest

from app.config import MAX_FRAME_BYTES
from app.stream_client import StreamClient
from app.stream_server import make_handshake


class FakeSocket:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False

    def settimeout(self, _value):
        pass

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


def _packet(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + payload


@pytest.fixture
def fake_socket_factory(monkeypatch):
    created = {}

    def factory(*_args, **_kwargs):
        handshake = _packet(make_handshake(64, 48, 15))
        sock = FakeSocket([handshake, _packet(b"encoded"), b""])
        created["sock"] = sock
        return sock

    monkeypatch.setattr(socket, "create_connection", factory)
    return created


def test_stream_client_decodes_frames_after_handshake(monkeypatch, fake_socket_factory):
    class Decoder:
        def decode_packet(self, data):
            assert data == b"encoded"
            return [b"rgb"]

    monkeypatch.setattr("app.stream_client.H264Decoder", Decoder)
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=lambda *frame: seen.append(frame))
    client._running = True
    client._run()
    assert seen == [(b"rgb", 64, 48)]


def test_stream_client_continues_after_decode_error(monkeypatch):
    handshake = _packet(make_handshake(64, 48, 15))
    fake = FakeSocket([handshake, _packet(b"bad"), b""])
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: fake)

    class Decoder:
        def decode_packet(self, _data):
            raise ValueError("not a keyframe")

    monkeypatch.setattr("app.stream_client.H264Decoder", Decoder)
    seen = []
    client = StreamClient("127.0.0.1", 5000, on_frame=lambda *frame: seen.append(frame))
    client._running = True
    client._run()
    assert seen == []


def test_stream_client_rejects_too_large_packet(monkeypatch):
    handshake = _packet(make_handshake(64, 48, 15))
    fake = FakeSocket([handshake, struct.pack(">I", MAX_FRAME_BYTES + 1)])
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: fake)
    client = StreamClient("127.0.0.1", 5000, on_frame=lambda *_frame: None)
    client._running = True
    client._run()
    assert fake.closed is True
