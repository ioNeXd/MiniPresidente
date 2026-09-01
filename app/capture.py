from __future__ import annotations

# ─── capture.py ────────────────────────────────────────────────────────────
# Captura de tela (via mss, funciona em Windows/Linux/Mac) + encode JPEG.
# Isso substitui toda a camada DXGI/WGC/NVENC do projeto C++ original —
# mss usa a API nativa do SO por baixo dos panos, mas sem exigir que você
# lide com ponteiros, COM ou enumeração manual.
# ─────────────────────────────────────────────────────────────────────────────
import io
import logging

import mss
from PIL import Image

logger = logging.getLogger(__name__)

# Singleton do mss para reutilização — criar/destroir por frame é ineficiente
# e pode causar erros em algumas plataformas.
_sct: mss.mss | None = None


def _get_sct() -> mss.mss:
    """Retorna uma instância singleton do mss."""
    global _sct
    if _sct is None:
        _sct = mss.mss()
    return _sct


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
    # .rgb retorna os bytes do frame em formato RGB
    img = Image.frombytes("RGB", raw.size, raw.rgb, "raw", "RGB")

    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, max(1, int(img.height * ratio)))
        img = img.resize(new_size)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
