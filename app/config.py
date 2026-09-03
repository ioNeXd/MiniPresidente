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
# FPS, bitrate e resolução reais são escolhidos por sessão na lobby (ver
# app/session_config.py). DEFAULT_MAX_WIDTH é só o fallback usado se nenhuma
# resolução for aplicada.
DEFAULT_MAX_WIDTH = 1280     # downscale do frame antes de enviar (poupa banda/CPU)
MAX_FRAME_BYTES = 32 * 1024 * 1024  # limite do protocolo de framing: rejeita payloads JPEG absurdamente grandes no fluxo de rede compartilhado entre server e client
MAX_CLIENT_QUEUE = 60        # backpressure por viewer: cerca de 2 s de vídeo a 30 FPS

# ─── UI ───────────────────────────────────────────────────────────────────
GRID_COLUMNS = 2             # colunas no grid de telas da sala

def validate_config() -> None:
    """Valida os valores de configuração no startup."""
    if not (1 <= DISCOVERY_PORT <= 65535):
        raise ValueError(f"DISCOVERY_PORT must be 1-65535, got {DISCOVERY_PORT}")
    if DEFAULT_MAX_WIDTH < 100:
        raise ValueError(f"DEFAULT_MAX_WIDTH must be >= 100, got {DEFAULT_MAX_WIDTH}")
    if MAX_FRAME_BYTES < 1:
        raise ValueError(f"MAX_FRAME_BYTES must be >= 1, got {MAX_FRAME_BYTES}")
    if MAX_CLIENT_QUEUE < 1:
        raise ValueError(f"MAX_CLIENT_QUEUE must be >= 1, got {MAX_CLIENT_QUEUE}")
    if GRID_COLUMNS < 1:
        raise ValueError(f"GRID_COLUMNS must be >= 1, got {GRID_COLUMNS}")


# Validação automática no import
validate_config()
