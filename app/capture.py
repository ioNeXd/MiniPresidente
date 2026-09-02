from __future__ import annotations

# ─── capture.py ────────────────────────────────────────────────────────────
# Captura de tela (via mss, funciona em Windows/Linux/Mac). Os frames RGB
# crus daqui alimentam o encoder H.264 (video_codec.py) tanto pra
# transmissão quanto pro preview local. Isso substitui toda a camada
# DXGI/WGC/NVENC do projeto C++ original — mss usa a API nativa do SO por
# baixo dos panos, mas sem exigir que você lide com ponteiros, COM ou
# enumeração manual.
#
# THREAD-SAFETY: mss não é thread-safe. Cada thread que captura deve
# ter sua própria instância. Usamos threading.local() para isso.
# ─────────────────────────────────────────────────────────────────────────────
import logging
import threading
import time
from typing import Callable

import mss
import mss.base
from PIL import Image

logger = logging.getLogger(__name__)

# Thread-local storage para instâncias mss — cada thread tem a sua,
# evitando concorrência e crashes ao capturar de múltiplas threads.
_thread_local = threading.local()


def _get_sct() -> mss.base.MSSBase:
    """Retorna uma instância mss thread-local (uma por thread)."""
    sct: mss.base.MSSBase | None = getattr(_thread_local, "sct", None)
    if sct is None:
        sct = mss.MSS()
        _thread_local.sct = sct
    return sct


def list_monitors() -> list[dict]:
    """Retorna a lista de monitores disponíveis (índice 0 = todos combinados)."""
    return list(_get_sct().monitors)


def capture_loop_rgb(
    running: Callable[[], bool],
    fps: int,
    on_frame: Callable[[bytes, int, int], None],
    monitor_index: int,
    max_width: int,
    logger: logging.Logger,
) -> None:
    """Executa a captura periódica e entrega frames RGB crus (dados, largura,
    altura) ao callback — o mesmo formato que os tiles de vídeo da sala
    esperam (RGB888 + width/height), igual ao que o H264Decoder produz para
    os streams remotos. Usado pelo preview local (self_preview.py).

    O helper centraliza o timing, o tratamento de erro e o sleep do restante
    do intervalo para que o mesmo padrão não seja duplicado em outros loops
    de captura do projeto.
    """
    interval = 1.0 / max(1, fps)
    while running():
        start = time.monotonic()
        try:
            data, width, height = grab_rgb(monitor_index, max_width)
            on_frame(data, width, height)
        except Exception:
            logger.exception("Error capturing frame")
        elapsed = time.monotonic() - start
        if elapsed < interval:
            time.sleep(interval - elapsed)


def grab_rgb(monitor_index: int, max_width: int) -> tuple[bytes, int, int]:
    """Captura um monitor e retorna RGB cru, largura e altura pares."""
    sct = _get_sct()
    monitors = sct.monitors
    idx = monitor_index if 0 < monitor_index < len(monitors) else 1
    raw = sct.grab(monitors[idx])
    img = Image.frombytes("RGB", raw.size, raw.rgb, "raw", "RGB")

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, max(1, int(img.height * ratio))))

    width = img.width - img.width % 2
    height = img.height - img.height % 2
    if width < 2 or height < 2:
        raise ValueError("Captured monitor is too small for H.264")
    if (width, height) != img.size:
        img = img.crop((0, 0, width, height))
    return img.tobytes(), width, height
