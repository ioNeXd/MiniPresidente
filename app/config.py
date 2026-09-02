from __future__ import annotations

# ─── config.py ─────────────────────────────────────────────────────────────
# Constantes centrais do MiniPresidente.
# ─────────────────────────────────────────────────────────────────────────────
# Fonte única de versão — pyproject.toml lê este valor via dynamic version.
__version__ = "0.1.0"

# ─── Discovery (UDP broadcast) ────────────────────────────────────────────
DISCOVERY_PORT = 47001       # porta UDP de broadcast (presença/descoberta de salas)
BROADCAST_INTERVAL_S = 1.5   # a cada quanto tempo cada peer anuncia sua presença
PEER_TIMEOUT_S = 5.0         # tempo sem anúncio até considerar o peer offline

# ─── Stream (captura + compressão) ────────────────────────────────────────
DEFAULT_FPS = 15             # fps de cada stream (suba com cautela)
DEFAULT_JPEG_QUALITY = 60    # 1-95, mais alto = melhor qualidade / mais banda
DEFAULT_MAX_WIDTH = 1280     # downscale do frame antes de enviar (poupa banda/CPU)
MAX_FRAME_BYTES = 32 * 1024 * 1024  # limite do protocolo de framing: rejeita payloads JPEG absurdamente grandes no fluxo de rede compartilhado entre server e client

# ─── UI ───────────────────────────────────────────────────────────────────
GRID_COLUMNS = 2             # colunas no grid de telas da sala

def validate_config() -> None:
    """Valida os valores de configuração no startup."""
    if not (1 <= DISCOVERY_PORT <= 65535):
        raise ValueError(f"DISCOVERY_PORT must be 1-65535, got {DISCOVERY_PORT}")
    if DEFAULT_FPS < 1:
        raise ValueError(f"DEFAULT_FPS must be >= 1, got {DEFAULT_FPS}")
    if not (1 <= DEFAULT_JPEG_QUALITY <= 95):
        raise ValueError(f"DEFAULT_JPEG_QUALITY must be 1-95, got {DEFAULT_JPEG_QUALITY}")
    if DEFAULT_MAX_WIDTH < 100:
        raise ValueError(f"DEFAULT_MAX_WIDTH must be >= 100, got {DEFAULT_MAX_WIDTH}")
    if MAX_FRAME_BYTES < 1:
        raise ValueError(f"MAX_FRAME_BYTES must be >= 1, got {MAX_FRAME_BYTES}")
    if GRID_COLUMNS < 1:
        raise ValueError(f"GRID_COLUMNS must be >= 1, got {GRID_COLUMNS}")


# Validação automática no import
validate_config()
