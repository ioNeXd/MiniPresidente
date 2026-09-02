"""Testes mínimos para o protocolo de framing do stream (4 bytes big-endian + payload JPEG)."""

import struct


def test_frame_header_size():
    """Header de tamanho deve ter exatamente 4 bytes."""
    frame = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # Simula JPEG
    header = struct.pack(">I", len(frame))
    assert len(header) == 4


def test_frame_header_roundtrip():
    """Header deve serializar/deserializar corretamente."""
    sizes = [0, 1, 255, 1024, 65536, 1048576]
    for size in sizes:
        header = struct.pack(">I", size)
        (decoded,) = struct.unpack(">I", header)
        assert decoded == size


def test_frame_header_big_endian():
    """Header deve ser big-endian (>I)."""
    val = 0x01020304
    header = struct.pack(">I", val)
    assert header == b"\x01\x02\x03\x04"


def test_frame_header_max_uint32():
    """Header deve suportar até 4GB de payload."""
    max_val = 0xFFFFFFFF
    header = struct.pack(">I", max_val)
    (decoded,) = struct.unpack(">I", header)
    assert decoded == max_val
