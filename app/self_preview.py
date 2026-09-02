from __future__ import annotations

# ─── self_preview.py ───────────────────────────────────────────────────────
# Captura local (só pra você) enquanto está transmitindo, pra mostrar
# "qual tela está sendo transmitida" na sua própria janela — isso é o
# preview com imagem real que faltava no MiniPresidente original.
# ─────────────────────────────────────────────────────────────────────────────
import logging
import threading
from typing import Callable

from app.capture import capture_loop
from app.config import DEFAULT_FPS, DEFAULT_JPEG_QUALITY, DEFAULT_MAX_WIDTH

logger = logging.getLogger(__name__)


class SelfPreview:
    def __init__(self, on_frame: Callable[[bytes], None], monitor_index: int = 1,
                 fps: int = DEFAULT_FPS, quality: int = DEFAULT_JPEG_QUALITY,
                 max_width: int = DEFAULT_MAX_WIDTH):
        self.on_frame = on_frame
        self.monitor_index = monitor_index
        self.fps = fps
        self.quality = quality
        self.max_width = max_width
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("SelfPreview started")

    def stop(self) -> None:
        self._running = False
        logger.info("SelfPreview stopped")

    def _run(self) -> None:
        capture_loop(
            running=lambda: self._running,
            fps=self.fps,
            on_frame=self.on_frame,
            monitor_index=self.monitor_index,
            quality=self.quality,
            max_width=self.max_width,
            logger=logger,
        )
