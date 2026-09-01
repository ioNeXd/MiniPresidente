# ─── stream_server.py ──────────────────────────────────────────────────────
# Servidor TCP: quando você está "transmitindo", cada amigo que quiser
# assistir sua tela abre uma conexão TCP nova aqui. Cada conexão tem sua
# própria thread, que captura e envia frames JPEG continuamente
# (protocolo simples: 4 bytes de tamanho + payload JPEG).
#
# Isso substitui RTP/UDP/FEC/jitter-buffer do projeto original — em LAN,
# TCP simples é bem mais fácil de acertar e "só funciona".
# ─────────────────────────────────────────────────────────────────────────────

import logging
import socket
import struct
import threading
import time
from typing import Optional

from app.capture import grab_jpeg
from app.config import DEFAULT_FPS, DEFAULT_JPEG_QUALITY, DEFAULT_MAX_WIDTH

logger = logging.getLogger(__name__)


class StreamServer:
    def __init__(self, monitor_index: int = 1, fps: int = DEFAULT_FPS,
                 quality: int = DEFAULT_JPEG_QUALITY, max_width: int = DEFAULT_MAX_WIDTH):
        self.monitor_index = monitor_index
        self.fps = fps
        self.quality = quality
        self.max_width = max_width

        self._sock: Optional[socket.socket] = None
        self._running = False
        self.port = 0
        self._client_count = 0
        self._lock = threading.Lock()

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", 0))  # porta efêmera livre
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        logger.info("StreamServer started on port %d", self.port)
        return self.port

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        logger.info("StreamServer stopped")

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                # Socket fechado ou erro — termina a thread
                break
            threading.Thread(target=self._serve_client, args=(conn,), daemon=True).start()

    def _serve_client(self, conn: socket.socket) -> None:
        with self._lock:
            self._client_count += 1
        try:
            interval = 1.0 / max(1, self.fps)
            while self._running:
                start = time.time()
                try:
                    frame = grab_jpeg(self.monitor_index, self.quality, self.max_width)
                except Exception:
                    break
                header = struct.pack(">I", len(frame))
                try:
                    conn.sendall(header + frame)
                except OSError:
                    break
                elapsed = time.time() - start
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        finally:
            with self._lock:
                self._client_count -= 1
            try:
                conn.close()
            except OSError:
                pass

    @property
    def viewer_count(self) -> int:
        with self._lock:
            return self._client_count
