from __future__ import annotations

# ─── self_preview.py ───────────────────────────────────────────────────────
# Captura local (só pra você) enquanto está transmitindo, pra mostrar
# "qual tela está sendo transmitida" na sua própria janela. Usa o mesmo
# formato de frame (RGB cru + width/height) que os tiles da sala esperam,
# consistente com o que o H264Decoder entrega para os streams remotos.
# ─────────────────────────────────────────────────────────────────────────────
import logging
import threading
from typing import Callable

from app.capture import capture_loop_rgb
from app.session_config import SessionConfig

logger = logging.getLogger(__name__)


class SelfPreview:
    def __init__(self, session_config: SessionConfig,
                 on_frame: Callable[[bytes, int, int], None]):
        self.on_frame = on_frame
        self.monitor_index = session_config.monitor_index
        # Usa o mesmo FPS configurado para a transmissão real (video_fps),
        # não o `fps` legado (não configurável na lobby) — assim o preview
        # local reflete fielmente o que está sendo enviado aos outros peers.
        self.fps = session_config.video_fps
        self.max_width = session_config.max_width
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("SelfPreview started")

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.info("SelfPreview stopped")

    def _run(self) -> None:
        capture_loop_rgb(
            running=lambda: self._running,
            fps=self.fps,
            on_frame=self.on_frame,
            monitor_index=self.monitor_index,
            max_width=self.max_width,
            logger=logger,
        )
