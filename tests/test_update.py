"""Testes mínimos para auto-update: versões, estado, hash, parsing de release."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.update_state import (
    add_ignored_version,
    is_version_ignored,
    load_state,
    save_state,
    should_check_today,
)
from app.updater import compare_versions, fetch_latest_release, verify_hash

# ─── compare_versions ─────────────────────────────────────────────────────

def test_compare_versions_greater():
    assert compare_versions("0.1.0", "0.2.0") is True
    assert compare_versions("1.0.0", "2.0.0") is True
    assert compare_versions("0.9.0", "0.10.0") is True


def test_compare_versions_equal():
    assert compare_versions("0.1.0", "0.1.0") is False


def test_compare_versions_less():
    assert compare_versions("0.2.0", "0.1.0") is False
    assert compare_versions("2.0.0", "1.0.0") is False


def test_compare_versions_invalid():
    assert compare_versions("abc", "0.1.0") is False
    assert compare_versions("0.1.0", "xyz") is False


# ─── should_check_today ──────────────────────────────────────────────────

def test_should_check_today_no_prior_check():
    """Sem last_check, deve retornar True."""
    with patch("app.update_state.load_state", return_value={"last_check": None, "ignored_versions": []}):
        assert should_check_today() is True


def test_should_check_today_recent_check():
    """Última verificação há menos de 24h, deve retornar False."""
    recent = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    with patch("app.update_state.load_state", return_value={"last_check": recent, "ignored_versions": []}):
        assert should_check_today() is False


def test_should_check_today_old_check():
    """Última verificação há mais de 24h, deve retornar True."""
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    with patch("app.update_state.load_state", return_value={"last_check": old, "ignored_versions": []}):
        assert should_check_today() is True


def test_should_check_today_corrupted():
    """Last_check corrompido, deve retornar True."""
    with patch("app.update_state.load_state", return_value={"last_check": "not-a-date"}):
        assert should_check_today() is True# ─── update_state persistence ────────────────────────────────────────────
def test_state_persistence_roundtrip(tmp_path):
    """save/load deve preservar dados (usa diretório temporário)."""
    fake_path = tmp_path / "update_state.json"
    with patch("app.update_state._state_path", return_value=fake_path):
        state = {"ignored_versions": ["0.2.0"], "last_check": "2025-01-01T00:00:00+00:00"}
        save_state(state)
        loaded = load_state()
        assert loaded["ignored_versions"] == ["0.2.0"]
        assert loaded["last_check"] == "2025-01-01T00:00:00+00:00"


def test_is_version_ignored(tmp_path):
    fake_path = tmp_path / "update_state.json"
    with patch("app.update_state._state_path", return_value=fake_path):
        add_ignored_version("0.3.0")
        assert is_version_ignored("0.3.0") is True
        assert is_version_ignored("0.4.0") is False


# ─── verify_hash (arquivo temporário) ────────────────────────────────────

def test_verify_hash_valid():
    """Verificação com hash correto deve passar (urlopen mockado)."""
    import hashlib
    from unittest.mock import MagicMock, patch

    # Cria arquivo temporário com conteúdo conhecido
    content = b"test content for hashing"
    sha256 = hashlib.sha256(content).hexdigest()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".exe") as f:
        f.write(content)
        temp_path = f.name

    hash_content = f"{sha256}  MiniPresidente.exe\n".encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = hash_content
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    try:
        with patch("app.updater.urllib.request.urlopen", return_value=mock_resp):
            assert verify_hash(temp_path, "https://example.com/hash.sha256") is True
    finally:
        os.unlink(temp_path)


def test_verify_hash_mismatch():
    """Verificação com hash incorreto deve falhar (urlopen mockado)."""
    from unittest.mock import MagicMock, patch

    content = b"test content"
    wrong_hash = "0" * 64

    with tempfile.NamedTemporaryFile(delete=False, suffix=".exe") as f:
        f.write(content)
        temp_path = f.name

    hash_content = f"{wrong_hash}  MiniPresidente.exe\n".encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = hash_content
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    try:
        with patch("app.updater.urllib.request.urlopen", return_value=mock_resp):
            assert verify_hash(temp_path, "https://example.com/hash.sha256") is False
    finally:
        os.unlink(temp_path)


def test_verify_hash_no_hash_url():
    """Sem hash_url, deve retornar False."""
    assert verify_hash("/nonexistent", "") is False
    assert verify_hash("/nonexistent", None) is False# ─── fetch_latest_release parsing ────────────────────────────────────────
def test_fetch_release_parsing():
    """Chama fetch_latest_release() com urlopen mockado e valida o parsing real."""
    import json
    from unittest.mock import MagicMock

    fake_response = {
        "tag_name": "v0.2.0",
        "body": "Bug fixes and improvements",
        "assets": [
            {"name": "MiniPresidente.exe", "browser_download_url": "https://example.com/MiniPresidente.exe"},
            {"name": "MiniPresidente.exe.sha256", "browser_download_url": "https://example.com/MiniPresidente.exe.sha256"},
            {"name": "source.zip", "browser_download_url": "https://example.com/source.zip"},
        ],
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(fake_response).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("app.updater.urllib.request.urlopen", return_value=mock_resp):
        result = fetch_latest_release()

    assert result is not None
    assert result["version"] == "0.2.0"
    assert result["release_notes"] == "Bug fixes and improvements"
    assert result["exe_url"] == "https://example.com/MiniPresidente.exe"
    assert result["hash_url"] == "https://example.com/MiniPresidente.exe.sha256"
