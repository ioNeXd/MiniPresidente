from __future__ import annotations

# ─── discovery.py ──────────────────────────────────────────────────────────
# Descoberta de peers na LAN/VPN — equivalente ao módulo discovery/ do
# MiniPresidente original.
#
# Dois caminhos de discovery funcionam em paralelo:
#   1. BROADCAST UDP (255.255.255.255) — funciona em LAN física.
#   2. UNICAST para seed peers + gossip — funciona em VPNs (Radmin/Hamachi)
#      onde broadcast não é encaminhado. O usuário informa o IP de pelo
#      menos um peer na lobby; a partir daí o gossip propaga automaticamente.
# ─────────────────────────────────────────────────────────────────────────────
import ipaddress
import json
import logging
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from app.config import BROADCAST_INTERVAL_S, DISCOVERY_PORT, PEER_TIMEOUT_S

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    user_id: str
    username: str
    ip: str
    room_id: str
    room_name: str
    transmitting: bool
    stream_port: int
    last_seen: float = field(default_factory=time.monotonic)


def _is_valid_ipv4(value: str) -> bool:
    """Valida se uma string é um IPv4 válido."""
    try:
        ipaddress.IPv4Address(value)
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def parse_seed_peers(raw: str) -> list[str]:
    """Parse de uma string de seed peers (vírgula-separada) em lista de IPs válidos.

    Exemplos:
        "25.10.10.5, 25.10.10.8" -> ["25.10.10.5", "25.10.10.8"]
        "25.10.10.5"             -> ["25.10.10.5"]
        "invalido, 25.10.10.5"   -> ["25.10.10.5"]
    """
    result: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if item and _is_valid_ipv4(item):
            result.append(item)
    return result


def detect_advertise_ip() -> str:
    """Detecta o IP a ser anunciado no broadcast.

    1. Se MANUAL_ADVERTISE_IP estiver definido, usa ele.
    2. Enumera todos os IPs e prioriza os que NÃO são LAN comum
       (192.168.x, 10.x, 172.16-31.x) — costumam ser IPs de VPN.
    3. Fallback: 127.0.0.1.
    """
    from app.config import MANUAL_ADVERTISE_IP

    if MANUAL_ADVERTISE_IP:
        logger.info("Using manual advertise IP: %s", MANUAL_ADVERTISE_IP)
        return MANUAL_ADVERTISE_IP

    try:
        hostname = socket.gethostname()
        all_ips = socket.gethostbyname_ex(hostname)[2]
        preferred: list[str] = []
        fallback: list[str] = []
        for ip in all_ips:
            if ip.startswith("127."):
                continue
            parts = ip.split(".")
            if len(parts) != 4:
                continue
            first = int(parts[0])
            second = int(parts[1]) if len(parts) > 1 else 0
            is_private_lan = (
                (first == 192 and second == 168)
                or first == 10
                or (first == 172 and 16 <= second <= 31)
            )
            if is_private_lan:
                fallback.append(ip)
            else:
                preferred.append(ip)

        if preferred:
            logger.info("Detected VPN/non-LAN IP: %s", preferred[0])
            return preferred[0]
        elif fallback:
            logger.info("Using LAN IP: %s", fallback[0])
            return fallback[0]
        else:
            logger.warning("No non-loopback IPs found, falling back to 127.0.0.1")
            return "127.0.0.1"
    except Exception:
        logger.warning("IP detection failed, falling back to 127.0.0.1")
        return "127.0.0.1"


class Discovery:
    """Gerencia descoberta de peers via broadcast UDP e unicast/gossip."""

    def __init__(self, username: str, manual_advertise_ip: str = "", seed_peers: Optional[List[str]] = None):
        """Inicializa Discovery com socket UDP e estado compartilhado."""
        from app import config as app_config

        self.user_id = str(uuid.uuid4())[:8]
        self.username = username
        self._room_id = ""
        self._room_name = ""
        self._transmitting = False
        self._stream_port = 0
        self._manual_advertise_ip = manual_advertise_ip or app_config.MANUAL_ADVERTISE_IP
        self._seed_peers = list(seed_peers) if seed_peers else list(app_config.SEED_PEERS)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self._sock.bind(("", DISCOVERY_PORT))
        except OSError:
            logger.warning("Port %d occupied, binding to ephemeral port", DISCOVERY_PORT)
            self._sock.bind(("", 0))
        self._sock.settimeout(1.0)

        self.peers: Dict[str, PeerInfo] = {}
        self._lock = threading.Lock()
        self._running = False
        self._on_change: Optional[Callable[[], None]] = None
        self._threads: list[threading.Thread] = []

    # ─── Propriedades com proteção de lock ──────────────────────────────
    @property
    def room_id(self) -> str:
        with self._lock:
            return self._room_id

    @room_id.setter
    def room_id(self, value: str) -> None:
        with self._lock:
            self._room_id = value

    @property
    def room_name(self) -> str:
        with self._lock:
            return self._room_name

    @room_name.setter
    def room_name(self, value: str) -> None:
        with self._lock:
            self._room_name = value

    @property
    def transmitting(self) -> bool:
        with self._lock:
            return self._transmitting

    @property
    def stream_port(self) -> int:
        with self._lock:
            return self._stream_port

    def set_on_change(self, cb: Callable[[], None]) -> None:
        self._on_change = cb

    def start(self) -> None:
        """Inicia as threads de broadcast, escuta e reap."""
        self._running = True
        self._threads = [
            threading.Thread(target=self._broadcast_loop, daemon=True),
            threading.Thread(target=self._listen_loop, daemon=True),
            threading.Thread(target=self._reap_loop, daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        logger.info("Discovery started for user %s", self.username)

    def stop(self) -> None:
        """Para todas as threads e fecha o socket."""
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass
        for thread in self._threads:
            thread.join(timeout=2.0)
        logger.info("Discovery stopped")

    def set_room(self, room_id: str, room_name: str) -> None:
        """Define a sala atual (thread-safe)."""
        with self._lock:
            self._room_id = room_id
            self._room_name = room_name

    def set_transmitting(self, on: bool, stream_port: int = 0) -> None:
        """Define o estado de transmissão e a porta do stream (thread-safe)."""
        with self._lock:
            self._transmitting = on
            self._stream_port = stream_port

    # ─── Broadcast + unicast (gossip) ──────────────────────────────────
    def _broadcast_loop(self) -> None:
        ip = self._manual_advertise_ip or detect_advertise_ip()
        last_ip_check = time.monotonic()

        while self._running:
            now = time.monotonic()
            if now - last_ip_check >= 30.0:
                ip = self._manual_advertise_ip or detect_advertise_ip()
                last_ip_check = now

            with self._lock:
                rid = self._room_id
                rname = self._room_name
                tx = self._transmitting
                sport = self._stream_port

            if rid:
                msg = {
                    "user_id": self.user_id,
                    "username": self.username,
                    "ip": ip,
                    "room_id": rid,
                    "room_name": rname,
                    "transmitting": tx,
                    "stream_port": sport,
                }
                data = json.dumps(msg).encode("utf-8")

                # 1) Broadcast para LAN
                try:
                    self._sock.sendto(data, ("255.255.255.255", DISCOVERY_PORT))
                except OSError:
                    pass

                # 2) Unicast para seed peers + gossip (peers conhecidos)
                self._unicast_to_known_peers(data, ip)

            time.sleep(BROADCAST_INTERVAL_S)

    def _unicast_to_known_peers(self, data: bytes, my_ip: str) -> None:
        """Envia o payload via unicast para seed peers + peers aprendidos (gossip).
        Evita enviar para o próprio IP."""
        with self._lock:
            peer_ips = {p.ip for p in self.peers.values() if p.ip != my_ip}

        all_destinations = set(self._seed_peers) | peer_ips
        for dest_ip in all_destinations:
            if dest_ip == my_ip or not _is_valid_ipv4(dest_ip):
                continue
            try:
                self._sock.sendto(data, (dest_ip, DISCOVERY_PORT))
            except OSError:
                pass

    def _listen_loop(self) -> None:
        while self._running:
            try:
                data, _addr = self._sock.recvfrom(4096)
            except (socket.timeout, OSError):
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if msg.get("user_id") == self.user_id:
                continue

            # Validação dos dados recebidos do peer
            try:
                info = _parse_peer_msg(msg)
            except (KeyError, ValueError):
                continue

            info.last_seen = time.monotonic()
            with self._lock:
                self.peers[info.user_id] = info
                on_change = self._on_change
            if on_change:
                on_change()

    def _reap_loop(self) -> None:
        while self._running:
            time.sleep(1.0)
            now = time.monotonic()
            removed = False
            with self._lock:
                dead = [uid for uid, p in self.peers.items() if now - p.last_seen > PEER_TIMEOUT_S]
                for uid in dead:
                    del self.peers[uid]
                    removed = True
                on_change = self._on_change
            if removed and on_change:
                on_change()

    def get_peers(self) -> List[PeerInfo]:
        with self._lock:
            return list(self.peers.values())


def _parse_peer_msg(msg: dict) -> PeerInfo:
    """Valida e parseia uma mensagem de broadcast de peer.

    Valida:
    - Campos obrigatórios existem
    - Tipos estão corretos
    - IP parece IPv4
    - stream_port é inteiro positivo
    - Strings não excedem tamanhos razoáveis
    """
    user_id = msg.get("user_id")
    username = msg.get("username")
    ip = msg.get("ip")
    room_id = msg.get("room_id")
    room_name = msg.get("room_name")
    transmitting = msg.get("transmitting")
    stream_port = msg.get("stream_port")

    if not isinstance(user_id, str) or not user_id:
        raise ValueError("Invalid user_id")
    if not isinstance(username, str) or not username:
        raise ValueError("Invalid username")
    if not isinstance(ip, str) or not _is_valid_ipv4(ip):
        raise ValueError(f"Invalid IP: {ip}")
    if not isinstance(room_id, str) or not room_id:
        raise ValueError("Invalid room_id")
    if not isinstance(room_name, str) or not room_name:
        raise ValueError("Invalid room_name")
    if not isinstance(transmitting, bool):
        raise ValueError("Invalid transmitting")
    if isinstance(stream_port, bool) or not isinstance(stream_port, int) or not (0 <= stream_port <= 65535):
        raise ValueError(f"Invalid port: {stream_port}")

    return PeerInfo(
        user_id=user_id[:64],
        username=username[:64],
        ip=ip,
        room_id=room_id[:128],
        room_name=room_name[:128],
        transmitting=transmitting,
        stream_port=stream_port,
    )
