# ─── stream_client.py ──────────────────────────────────────────────────────
# Cliente TCP: conecta no stream_server de um peer e recebe frames JPEG
# continuamente, entregando cada um via callback (a UI decide o que fazer).
# ─────────────────────────────────────────────────────────────────────────────

import logging
import socket
import struct
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class StreamClient:
    def __init__(self, ip: str, port: int,
                 on_frame: Callable[[bytes], None],
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
        logger.info("StreamClient connecting to %s:%d", self.ip, self.port)

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        logger.info("StreamClient stopped")

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Recebe exatamente n bytes do socket. Usa bytearray para
        eficiência — evita criar novo objeto bytes a cada chunk."""
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

    def _run(self) -> None:
        try:
            self._sock = socket.create_connection((self.ip, self.port), timeout=5)
            self._sock.settimeout(None)
        except OSError:
            logger.warning("Failed to connect to %s:%d", self.ip, self.port)
            if self.on_disconnect:
                self.on_disconnect()
            return

        logger.info("Connected to %s:%d", self.ip, self.port)

        while self._running:
            header = self._recv_exact(4)
            if header is None:
                break
            (size,) = struct.unpack(">I", header)
            data = self._recv_exact(size)
            if data is None:
                break
            self.on_frame(data)

        logger.info("Disconnected from %s:%d", self.ip, self.port)
        if self.on_disconnect:
            self.on_disconnect()
