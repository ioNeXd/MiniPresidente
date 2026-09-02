from __future__ import annotations

# ─── updater.py ────────────────────────────────────────────────────────────
# Lógica de auto-update: fetch release, download, verify SHA-256, install.
# Funciona APENAS no Windows frozen. Em modo dev, retorna None silenciosamente.
# ─────────────────────────────────────────────────────────────────────────────
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Optional

from packaging.version import Version

from app.config import __version__
from app.update_state import (
    is_version_ignored,
    should_check_today,
    update_last_check,
)

logger = logging.getLogger(__name__)

_GITHUB_API_URL = "https://api.github.com/repos/ioNeXd/MiniPresidente/releases/latest"
_USER_AGENT = f"MiniPresidente/{__version__}"


def get_current_version() -> str:
    """Retorna a versão atual do app."""
    return __version__


def is_frozen() -> bool:
    """True se rodando como executável PyInstaller."""
    return getattr(sys, "frozen", False)


def fetch_latest_release() -> Optional[dict]:
    """Busca a release mais recente no GitHub.

    Retorna dict com keys: version, release_notes, exe_url, hash_url.
    Retorna None se 404 (sem releases) ou erro de rede — degradação graciosa.
    """
    req = urllib.request.Request(_GITHUB_API_URL, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logger.info("No releases found on GitHub (404)")
        else:
            logger.warning("GitHub API error %d: %s", exc.code, exc.reason)
        return None
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("Network error fetching releases: %s", exc)
        return None

    tag = str(data.get("tag_name", "")).lstrip("v")
    body = str(data.get("body", ""))

    exe_url: Optional[str] = None
    hash_url: Optional[str] = None
    for asset in data.get("assets", []):
        name = str(asset.get("name", ""))
        url = str(asset.get("browser_download_url", ""))
        if name.endswith(".exe"):
            exe_url = url
        elif name.endswith(".exe.sha256"):
            hash_url = url

    if not tag or not exe_url:
        logger.warning("Release data incomplete (tag=%s, exe=%s)", tag, exe_url)
        return None

    return {
        "version": tag,
        "release_notes": body,
        "exe_url": exe_url,
        "hash_url": hash_url,
    }


def compare_versions(local: str, remote: str) -> bool:
    """True se remote > local (comparação semântica de versões)."""
    try:
        return Version(remote) > Version(local)
    except Exception:
        logger.warning("Version parse error: local=%s remote=%s", local, remote)
        return False


def should_show_update(remote_version: str) -> bool:
    """True se a versão remota não foi ignorada pelo usuário."""
    return not is_version_ignored(remote_version)


def download_file(url: str, dest_path: str, progress_callback=None) -> bool:
    """Baixa um arquivo com progresso. Retorna True se bem-sucedido."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(int(downloaded * 100 / total))
        return True
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Download failed: %s", exc)
        return False


def verify_hash(file_path: str, hash_url: str) -> bool:
    """Verifica SHA-256 do arquivo contra o hash baixado.

    Formato esperado do .sha256: <hash>  <nome_do_arquivo>
    Retorna False se hash_url ausente, download falhou, ou mismatch.
    """
    if not hash_url:
        logger.warning("No hash URL provided, refusing to proceed without verification")
        return False

    req = urllib.request.Request(hash_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            hash_text = resp.read().decode("utf-8").strip()
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Failed to download hash file: %s", exc)
        return False

    # Extrai o primeiro token (o hash) da linha
    expected_hash = hash_text.split()[0].lower() if hash_text else ""

    # Calcula SHA-256 do arquivo baixado
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)
    except OSError as exc:
        logger.error("Failed to read file for hashing: %s", exc)
        return False

    actual_hash = sha256.hexdigest().lower()

    if actual_hash == expected_hash:
        logger.info("SHA-256 verification passed")
        return True
    else:
        logger.error("SHA-256 mismatch: expected %s, got %s", expected_hash, actual_hash)
        return False


def create_update_script(new_exe_path: str, current_exe_path: str) -> str:
    """Gera um .bat que substitui o executável atual (Windows only)."""
    bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
copy /Y "{new_exe_path}" "{current_exe_path}"
if %errorlevel% neq 0 (
    echo ERROR: Failed to copy update.
    pause
    exit /b 1
)
start "" "{current_exe_path}"
"""
    bat_path = os.path.join(tempfile.gettempdir(), "MiniPresidente_update.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    return bat_path


def install_update(new_exe_path: str) -> None:
    """Executa o script de atualização e fecha o app."""
    current_exe = sys.executable
    bat_path = create_update_script(new_exe_path, current_exe)
    logger.info("Launching update script: %s", bat_path)

    # Flags detached no Windows para o .bat sobreviver ao fechamento do app
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [bat_path],
        shell=True,
        creationflags=creation_flags if sys.platform == "win32" else 0,
    )


def check_for_updates(force: bool = False) -> Optional[dict]:
    """Verifica se há atualização disponível.

    Retorna dict com {version, release_notes, exe_url, hash_url} ou None.
    Modo dev e não-Windows: retorna None silenciosamente.
    """
    if not is_frozen():
        logger.debug("Auto-update disabled in dev mode")
        return None

    if sys.platform != "win32":
        logger.info("Auto-update only supported on Windows")
        return None

    if not force and not should_check_today():
        logger.debug("Already checked today, skipping")
        return None

    if not force:
        update_last_check()

    release = fetch_latest_release()
    if release is None:
        return None

    remote_ver = release["version"]
    local_ver = get_current_version()

    if not compare_versions(local_ver, remote_ver):
        logger.info("Already up to date (local=%s, remote=%s)", local_ver, remote_ver)
        return None

    if not force and not should_show_update(remote_ver):
        logger.info("Version %s is ignored by user", remote_ver)
        return None

    logger.info("Update available: %s -> %s", local_ver, remote_ver)
    return release
