from __future__ import annotations

# ─── capture.py ────────────────────────────────────────────────────────────
# Captura de tela (via mss, funciona em Windows/Linux/Mac) + encode JPEG.
# Isso substitui toda a camada DXGI/WGC/NVENC do projeto C++ original —
# mss usa a API nativa do SO por baixo dos panos, mas sem exigir que você
# lide com ponteiros, COM ou enumeração manual.
#
# THREAD-SAFETY: mss não é thread-safe. Cada thread que captura deve
# ter sua própria instância. Usamos threading.local() para isso.
# ─────────────────────────────────────────────────────────────────────────────
import io
import logging
import threading

import mss
from PIL import Image

logger = logging.getLogger(__name__)

# Thread-local storage para instâncias mss — cada thread tem a sua,
# evitando concorrência e crashes ao capturar de múltiplas threads.
_thread_local = threading.local()


def _get_sct() -> mss.mss:
    """Retorna uma instância mss thread-local (uma por thread)."""
    sct: mss.mss | None = getattr(_thread_local, "sct", None)
    if sct is None:
        sct = mss.mss()
        _thread_local.sct = sct
    return sct


def list_monitors() -> list[dict]:
    """Retorna a lista de monitores disponíveis (índice 0 = todos combinados)."""
    return list(_get_sct().monitors)


def grab_jpeg(monitor_index: int = 1, quality: int = 60, max_width: int = 1280) -> bytes:
    """Captura um frame do monitor escolhido e retorna os bytes já em JPEG.

    monitor_index: 1 = primeiro monitor físico (0 seria "todos combinados").
    quality: 1-95 (qualidade JPEG).
    max_width: reduz a resolução antes de comprimir, pra poupar banda/CPU.
    """
    sct = _get_sct()
    monitors = sct.monitors
    idx = monitor_index if 0 < monitor_index < len(monitors) else 1

    raw = sct.grab(monitors[idx])
    img = Image.frombytes("RGB", raw.size, raw.rgb, "raw", "RGB")

    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, max(1, int(img.height * ratio)))
        img = img.resize(new_size)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
