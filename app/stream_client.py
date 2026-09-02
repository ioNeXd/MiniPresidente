from __future__ import annotations

import logging
import socket
import struct
import threading
from typing import Callable, Optional

from app.config import MAX_FRAME_BYTES
from app.stream_server import HANDSHAKE_FORMAT, HANDSHAKE_MAGIC, HANDSHAKE_SIZE
from app.video_codec import H264Decoder

logger = logging.getLogger(__name__)
FrameCallback = Callable[[bytes, int, int], None]


class StreamClient:
    def __init__(self, ip: str, port: int, on_frame: FrameCallback,
                 on_disconnect: Optional[Callable[[], None]] = None):
        self.ip = ip
        self.port = port
        self.on_frame = on_frame
        self.on_disconnect = on_disconnect
        self._running = False
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _recv_exact(self, n: int) -> bytes | None:
        buf = bytearray()
        while len(buf) < n:
            if not self._running or not self._sock:
                return None
            try:
                chunk = self._sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _read_packet(self) -> bytes | None:
        header = self._recv_exact(4)
        if header is None:
            return None
        (size,) = struct.unpack(">I", header)
        if size <= 0 or size > MAX_FRAME_BYTES:
            logger.warning("Packet size %d out of bounds", size)
            if self._sock:
                self._sock.close()
            return None
        return self._recv_exact(size)

    def _run(self) -> None:
        try:
            self._sock = socket.create_connection((self.ip, self.port), timeout=5)
            self._sock.settimeout(None)
            handshake = self._read_packet()
            if handshake is None or len(handshake) != HANDSHAKE_SIZE:
                raise ValueError("Invalid H.264 handshake")
            magic, width, height, fps = struct.unpack(HANDSHAKE_FORMAT, handshake)
            if magic != HANDSHAKE_MAGIC or min(width, height, fps) <= 0:
                raise ValueError("Invalid H.264 stream metadata")
            decoder = H264Decoder()
            while self._running:
                packet = self._read_packet()
                if packet is None:
                    break
                try:
                    frames = decoder.decode_packet(packet)
                except Exception:
                    logger.debug("Unable to decode H.264 packet", exc_info=True)
                    continue
                for frame in frames:
                    self.on_frame(frame, width, height)
        except (OSError, ValueError):
            logger.warning("Failed to receive H.264 stream from %s:%d", self.ip, self.port)
        finally:
            if self.on_disconnect:
                self.on_disconnect()
