"""Testes do transporte H.264 do StreamServer em socket TCP."""

import socket
import struct
import time
from threading import Event

from app.session_config import SessionConfig
from app.stream_client import StreamClient
from app.stream_server import HANDSHAKE_FORMAT, HANDSHAKE_SIZE, StreamServer
from app.video_codec import H264Decoder


def _recv_exact(sock: socket.socket, size: int, timeout: float = 5.0) -> bytes:
    sock.settimeout(timeout)
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RuntimeError("socket closed before all data was received")
        data.extend(chunk)
    return bytes(data)


def _read_packet(sock: socket.socket) -> bytes:
    size = struct.unpack(">I", _recv_exact(sock, 4))[0]
    return _recv_exact(sock, size)


def _capture_factory(width: int, height: int):
    index = 0

    def capture(_monitor: int, _max_width: int) -> tuple[bytes, int, int]:
        nonlocal index
        value = index % 256
        index += 1
        return bytes((value, 80, 180)) * (width * height), width, height

    return capture


def _start_server():
    config = SessionConfig("", "", "", fps=30, video_bitrate_kbps=500)
    server = StreamServer(config, capture_fn=_capture_factory(64, 48))
    server.start()
    return server


def test_viewer_receives_h264_handshake_and_frame():
    server = _start_server()
    sock = socket.create_connection(("127.0.0.1", server.port), timeout=5)
    try:
        handshake = _read_packet(sock)
        magic, width, height, fps = struct.unpack(HANDSHAKE_FORMAT, handshake)
        assert len(handshake) == HANDSHAKE_SIZE
        assert magic == b"MPH264"
        assert (width, height, fps) == (64, 48, 30)
        decoder = H264Decoder()
        decoded = []
        deadline = time.monotonic() + 5
        while not decoded and time.monotonic() < deadline:
            try:
                decoded.extend(decoder.decode_packet(_read_packet(sock)))
            except Exception:
                continue
        assert decoded
        assert len(decoded[0]) == width * height * 3
    finally:
        sock.close()
        server.stop()


def test_real_stream_client_round_trip():
    server = _start_server()
    received: list[tuple[bytes, int, int]] = []
    frame_ready = Event()

    def on_frame(data: bytes, width: int, height: int) -> None:
        received.append((data, width, height))
        frame_ready.set()

    client = StreamClient("127.0.0.1", server.port, on_frame)
    client.start()
    try:
        assert frame_ready.wait(5)
        assert received[0][1:] == (64, 48)
        assert len(received[0][0]) == 64 * 48 * 3
    finally:
        client.stop()
        server.stop()


def test_multiple_viewers_receive_ordered_packets():
    server = _start_server()
    clients = [socket.create_connection(("127.0.0.1", server.port), timeout=5) for _ in range(3)]
    try:
        for sock in clients:
            assert _read_packet(sock).startswith(b"MPH264")
            assert _read_packet(sock)
    finally:
        for sock in clients:
            sock.close()
        server.stop()


def test_server_accepts_injected_capture():
    width, height = 64, 48
    server = StreamServer(
        SessionConfig("", "", "", fps=30, video_bitrate_kbps=500),
        capture_fn=_capture_factory(width, height),
    )
    server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", server.port), timeout=5)
        try:
            handshake = _read_packet(sock)
            assert struct.unpack(HANDSHAKE_FORMAT, handshake)[1:3] == (width, height)
        finally:
            sock.close()
    finally:
        server.stop()
