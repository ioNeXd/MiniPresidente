# ─── discovery.py ──────────────────────────────────────────────────────────
# Descoberta de peers na LAN via broadcast UDP — equivalente ao módulo
# discovery/ do MiniPresidente original, só que sem a complexidade de
# enumerar interfaces de rede manualmente.
#
# Cada cliente anuncia periodicamente: quem é, em qual sala está, e se está
# transmitindo (e em qual porta TCP, caso esteja). Quem escuta esses
# anúncios monta uma lista de peers "vivos" (com timeout de presença).
# ─────────────────────────────────────────────────────────────────────────────

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
    last_seen: float = field(default_factory=time.time)


class Discovery:
    def __init__(self, username: str):
        self.user_id = str(uuid.uuid4())[:8]
        self.username = username
        self.room_id = ""
        self.room_name = ""
        self.transmitting = False
        self.stream_port = 0

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self._sock.bind(("", DISCOVERY_PORT))
        except OSError:
            # porta ocupada (ex: dois clientes na mesma máquina para teste) —
            # usa uma porta efêmera só pra enviar; ainda recebe broadcasts
            # de quem usou a porta fixa.
            logger.warning("Port %d occupied, binding to ephemeral port", DISCOVERY_PORT)
            self._sock.bind(("", 0))
        self._sock.settimeout(1.0)

        self.peers: Dict[str, PeerInfo] = {}
        self._lock = threading.Lock()
        self._running = False
        self._on_change: Optional[Callable[[], None]] = None

    def set_on_change(self, cb: Callable[[], None]) -> None:
        self._on_change = cb

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._reap_loop, daemon=True).start()
        logger.info("Discovery started for user %s", self.username)

    def stop(self) -> None:
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass
        logger.info("Discovery stopped")

    def set_room(self, room_id: str, room_name: str) -> None:
        self.room_id = room_id
        self.room_name = room_name

    def set_transmitting(self, on: bool, stream_port: int = 0) -> None:
        self.transmitting = on
        self.stream_port = stream_port

    @staticmethod
    def _local_ip() -> str:
        """Detecta o IP a ser anunciado no broadcast.

        1. Se MANUAL_ADVERTISE_IP estiver definido, usa ele (override manual).
        2. Enumera todos os IPs da máquina e prioriza os que NÃO são
           da LAN física comum (192.168.x, 10.x, 172.16-31.x) —
           esses costumam ser IPs de VPN (Radmin, Hamachi, etc).
        3. Se só houver IPs de LAN, usa o primeiro deles.
        4. Fallback: 127.0.0.1.
        """
        from app.config import MANUAL_ADVERTISE_IP

        if MANUAL_ADVERTISE_IP:
            logger.info("Using manual advertise IP: %s", MANUAL_ADVERTISE_IP)
            return MANUAL_ADVERTISE_IP

        # Enumera todos os IPs via hostname
        try:
            hostname = socket.gethostname()
            all_ips = socket.gethostbyname_ex(hostname)[2]
            preferred = []   # IPs que NÃO são LAN comum (provavelmente VPN)
            fallback = []    # IPs de LAN comum (192.168, 10, 172.16-31)
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
                logger.info("Detected VPN/non-LAN IP: %s (from %d candidates)", preferred[0], len(preferred))
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

    def _broadcast_loop(self) -> None:
        ip = self._local_ip()
        while self._running:
            if self.room_id:
                msg = {
                    "user_id": self.user_id,
                    "username": self.username,
                    "ip": ip,
                    "room_id": self.room_id,
                    "room_name": self.room_name,
                    "transmitting": self.transmitting,
                    "stream_port": self.stream_port,
                }
                data = json.dumps(msg).encode("utf-8")
                try:
                    self._sock.sendto(data, ("255.255.255.255", DISCOVERY_PORT))
                except OSError:
                    pass
            time.sleep(BROADCAST_INTERVAL_S)

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
                continue  # ignora nosso próprio broadcast

            try:
                info = PeerInfo(
                    user_id=msg["user_id"],
                    username=msg["username"],
                    ip=msg["ip"],
                    room_id=msg["room_id"],
                    room_name=msg["room_name"],
                    transmitting=msg["transmitting"],
                    stream_port=msg["stream_port"],
                )
            except KeyError:
                continue

            # Atualiza peer e notifica callback de forma thread-safe
            with self._lock:
                self.peers[info.user_id] = info
                on_change = self._on_change
            if on_change:
                on_change()

    def _reap_loop(self) -> None:
        while self._running:
            time.sleep(1.0)
            now = time.time()
            removed = False
            # Notifica callback fora do lock para evitar deadlock
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
