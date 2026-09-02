"""Testes mínimos para discovery.py — parse de seeds, validação de peers, detecção de IP."""

from app.discovery import _is_valid_ipv4, _parse_peer_msg, detect_advertise_ip, parse_seed_peers

# ─── parse_seed_peers ─────────────────────────────────────────────────────

def test_parse_seed_peers_multiple():
    assert parse_seed_peers("25.10.10.5, 25.10.10.8") == ["25.10.10.5", "25.10.10.8"]


def test_parse_seed_peers_single():
    assert parse_seed_peers("25.10.10.5") == ["25.10.10.5"]


def test_parse_seed_peers_with_spaces():
    assert parse_seed_peers("  25.10.10.5 ,  25.10.10.8  ") == ["25.10.10.5", "25.10.10.8"]


def test_parse_seed_peers_filters_invalid():
    assert parse_seed_peers("invalido, 25.10.10.5, 999.999.999.999") == ["25.10.10.5"]


def test_parse_seed_peers_empty():
    assert parse_seed_peers("") == []


def test_parse_seed_peers_all_invalid():
    assert parse_seed_peers("abc, def") == []


def test_parse_seed_peers_trailing_comma():
    assert parse_seed_peers("25.10.10.5,") == ["25.10.10.5"]


# ─── _is_valid_ipv4 ──────────────────────────────────────────────────────

def test_valid_ipv4():
    assert _is_valid_ipv4("192.168.1.1") is True
    assert _is_valid_ipv4("25.10.10.5") is True
    assert _is_valid_ipv4("0.0.0.0") is True
    assert _is_valid_ipv4("255.255.255.255") is True


def test_invalid_ipv4():
    assert _is_valid_ipv4("not_an_ip") is False
    assert _is_valid_ipv4("256.1.1.1") is False
    assert _is_valid_ipv4("1.2.3") is False
    assert _is_valid_ipv4("") is False


# ─── detect_advertise_ip ─────────────────────────────────────────────────

def test_detect_advertise_ip_returns_string():
    ip = detect_advertise_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_detect_advertise_ip_with_manual_override():
    import app.config
    old = app.config.MANUAL_ADVERTISE_IP
    app.config.MANUAL_ADVERTISE_IP = "10.0.0.1"
    try:
        assert detect_advertise_ip() == "10.0.0.1"
    finally:
        app.config.MANUAL_ADVERTISE_IP = old


# ─── _parse_peer_msg ─────────────────────────────────────────────────────

def test_parse_peer_msg_valid():
    msg = {
        "user_id": "abc123",
        "username": "TestUser",
        "ip": "192.168.1.10",
        "room_id": "sala-teste",
        "room_name": "Sala Teste",
        "transmitting": True,
        "stream_port": 50000,
    }
    peer = _parse_peer_msg(msg)
    assert peer.user_id == "abc123"
    assert peer.username == "TestUser"
    assert peer.ip == "192.168.1.10"
    assert peer.transmitting is True
    assert peer.stream_port == 50000


def test_parse_peer_msg_invalid_ip():
    msg = {
        "user_id": "abc123",
        "username": "TestUser",
        "ip": "not_an_ip",
        "room_id": "sala",
        "room_name": "Sala",
        "transmitting": False,
        "stream_port": 50000,
    }
    try:
        _parse_peer_msg(msg)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_parse_peer_msg_invalid_port():
    msg = {
        "user_id": "abc123",
        "username": "TestUser",
        "ip": "192.168.1.10",
        "room_id": "sala",
        "room_name": "Sala",
        "transmitting": False,
        "stream_port": 99999,
    }
    try:
        _parse_peer_msg(msg)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_parse_peer_msg_truncates_long_strings():
    msg = {
        "user_id": "x" * 100,
        "username": "y" * 100,
        "ip": "192.168.1.10",
        "room_id": "z" * 200,
        "room_name": "w" * 200,
        "transmitting": False,
        "stream_port": 50000,
    }
    peer = _parse_peer_msg(msg)
    assert len(peer.user_id) <= 64
    assert len(peer.username) <= 64
    assert len(peer.room_id) <= 128
    assert len(peer.room_name) <= 128


def test_parse_peer_msg_rejects_string_bool_and_non_bool_int():
    for bad in ("true", "false", 1, 0):
        msg = {
            "user_id": "abc123",
            "username": "TestUser",
            "ip": "192.168.1.10",
            "room_id": "sala",
            "room_name": "Sala",
            "transmitting": bad,
            "stream_port": 50000,
        }
        try:
            _parse_peer_msg(msg)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


def test_parse_peer_msg_accepts_zero_port_when_not_transmitting():
    msg = {
        "user_id": "abc123",
        "username": "TestUser",
        "ip": "192.168.1.10",
        "room_id": "sala",
        "room_name": "Sala",
        "transmitting": False,
        "stream_port": 0,
    }
    peer = _parse_peer_msg(msg)
    assert peer.stream_port == 0
    assert peer.transmitting is False


def test_parse_peer_msg_rejects_missing_field():
    msg = {
        "user_id": "abc123",
        "username": "TestUser",
        "ip": "192.168.1.10",
        "room_id": "sala",
        "room_name": "Sala",
        "stream_port": 50000,
    }
    try:
        _parse_peer_msg(msg)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
