from __future__ import annotations

# ─── stream_server.py ──────────────────────────────────────────────────────
# Servidor TCP: quando você está "transmitindo", cada amigo que quiser
# assistir sua tela abre uma conexão TCP nova aqui.
#
# OTIMIZAÇÃO: em vez de capturar N vezes (1 por viewer), captura 1 frame
# por intervalo e distribui o mesmo JPEG para todos os viewers via
# threading.Event. Isso reduz CPU de O(N) para O(1).
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

        # Frame compartilhado: um capture por intervalo, distribuído a todos
        self._current_frame: Optional[bytes] = None
        self._frame_lock = threading.Condition()
        self._frame_seq: int = 0

        self._client_count = 0
        self._clients_lock = threading.Lock()

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._running = True

        # Thread de captura: captura 1 frame e acorda todos os viewers
        threading.Thread(target=self._capture_loop, daemon=True).start()
        # Thread de aceitação de conexões
        threading.Thread(target=self._accept_loop, daemon=True).start()

        logger.info("StreamServer started on port %d", self.port)
        return self.port

    def stop(self) -> None:
        self._running = False
        with self._frame_lock:
            self._frame_lock.notify_all()  # Desperta threads bloqueadas
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        logger.info("StreamServer stopped")

    def _capture_loop(self) -> None:
        """Captura 1 frame por intervalo e distribui para todos os viewers."""
        interval = 1.0 / max(1, self.fps)
        while self._running:
            start = time.time()
            try:
                frame = grab_jpeg(self.monitor_index, self.quality, self.max_width)
                with self._frame_lock:
                    self._current_frame = frame
                    self._frame_seq += 1
                    self._frame_lock.notify_all()
            except Exception:
                logger.exception("Error capturing frame in StreamServer")
            elapsed = time.time() - start
            if elapsed < interval:
                time.sleep(interval - elapsed)

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                break
            threading.Thread(target=self._serve_client, args=(conn,), daemon=True).start()

    def _serve_client(self, conn: socket.socket) -> None:
        with self._clients_lock:
            self._client_count += 1
        last_seq = 0
        try:
            while self._running:
                with self._frame_lock:
                    # Espera até que um novo frame esteja disponível
                    while self._frame_seq == last_seq and self._running:
                        self._frame_lock.wait(timeout=2.0)
                    if not self._running:
                        break
                    frame = self._current_frame
                    last_seq = self._frame_seq
                if frame is None:
                    continue
                header = struct.pack(">I", len(frame))
                try:
                    conn.sendall(header + frame)
                except OSError:
                    logger.info("Viewer disconnected")
                    break
        finally:
            with self._clients_lock:
                self._client_count -= 1
            try:
                conn.close()
            except OSError:
                pass


