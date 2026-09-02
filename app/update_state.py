from __future__ import annotations

# ─── update_state.py ───────────────────────────────────────────────────────
# Estado persistente do auto-update (versões ignoradas, última verificação).
# Salvo em JSON no diretório apropriado:
#   - Frozen (exe): pasta do executável (se gravável)
#   - Dev (python): %APPDATA%/MiniPresidente ou ~/.config/MiniPresidente
# ─────────────────────────────────────────────────────────────────────────────
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_FILENAME = "update_state.json"


def _state_path() -> Path:
    """Retorna o caminho do arquivo de estado.

    Regra: se frozen E a pasta do executável é gravável, usar essa pasta.
    Caso contrário (modo dev), usar APPDATA ou ~/.config.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        if os.access(exe_dir, os.W_OK):
            return exe_dir / _STATE_FILENAME

    # Modo dev: pasta dedicada no APPDATA ou ~/.config
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    state_dir = base / "MiniPresidente"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / _STATE_FILENAME


def load_state() -> dict:
    """Lê o estado do JSON. Retorna dict padrão se ausente ou corrompido."""
    path = _state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.debug("Could not load update state: %s", exc)
    return {"ignored_versions": [], "last_check": None}


def save_state(state: dict) -> None:
    """Salva o estado em JSON."""
    path = _state_path()
    try:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not save update state: %s", exc)


def is_version_ignored(version: str) -> bool:
    """Verifica se uma versão foi marcada como 'nunca mais'."""
    state = load_state()
    return version in state.get("ignored_versions", [])


def add_ignored_version(version: str) -> None:
    """Adiciona uma versão à lista de ignoradas."""
    state = load_state()
    ignored = state.get("ignored_versions", [])
    if version not in ignored:
        ignored.append(version)
    state["ignored_versions"] = ignored
    save_state(state)


def should_check_today() -> bool:
    """True se last_check é None ou há mais de 24 horas."""
    state = load_state()
    last = state.get("last_check")
    if last is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        now = datetime.now(timezone.utc)
        return (now - last_dt).total_seconds() > 86400
    except (ValueError, TypeError):
        return True


def update_last_check() -> None:
    """Registra a data/hora atual como última verificação."""
    state = load_state()
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
