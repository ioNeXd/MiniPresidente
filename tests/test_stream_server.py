"""Testes do fan-out do StreamServer em nível de socket TCP."""

import socket
import struct
import time

import pytest

import app.capture as capture_mod
from app.stream_server import StreamServer


@pytest.fixture
def synthetic_jpeg(monkeypatch):
    """Substitui a captura real de tela por um JPEG sintético e estável."""
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    monkeypatch.setattr(capture_mod, "grab_jpeg", lambda *args, **kwargs: jpeg)
    return jpeg


def _recv_exact(sock: socket.socket, size: int, timeout: float = 5.0) -> bytes:
    """Lê exatamente `size` bytes de um socket, sem deixar o teste travar."""
    sock.settimeout(timeout)
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("socket closed before all data was received")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_one_frame(sock: socket.socket, timeout: float = 5.0) -> bytes:
    """Lê um frame completo, incluindo header big-endian + payload JPEG."""
    sock.settimeout(timeout)
    header = _recv_exact(sock, 4, timeout=timeout)
    payload_size = struct.unpack(">I", header)[0]
    payload = _recv_exact(sock, payload_size, timeout=timeout)
    return payload


def test_single_viewer_receives_frame(synthetic_jpeg):
    """Um viewer isolado deve receber o último frame capturado."""
    server = StreamServer(fps=30)
    server.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect(("127.0.0.1", server.port))
        frame = _read_one_frame(sock, timeout=5.0)
        assert frame == synthetic_jpeg
    finally:
        sock.close()
        server.stop()


def test_multiple_viewers_receive_frames(synthetic_jpeg):
    """Cada viewer deve receber ao menos um frame completo sem roubar o do outro."""
    server = StreamServer(fps=30)
    server.start()
    clients: list[socket.socket] = []
    try:
        for _ in range(3):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect(("127.0.0.1", server.port))
            clients.append(sock)

        received = []
        for sock in clients:
            frame = _read_one_frame(sock, timeout=5.0)
            received.append(frame)

        assert len(received) == 3
        assert all(frame == synthetic_jpeg for frame in received)
    finally:
        for sock in clients:
            sock.close()
        server.stop()


def test_stop_unblocks_viewers(synthetic_jpeg):
    """stop() deve liberar a espera de viewers e encerrar o serviço sem travar."""
    server = StreamServer(fps=30)
    server.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect(("127.0.0.1", server.port))
        _read_one_frame(sock, timeout=5.0)
        server.stop()
        time.sleep(0.2)
    finally:
        sock.close()
