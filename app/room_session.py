from __future__ import annotations

import logging
from typing import Dict

from PySide6.QtCore import QObject, Signal

from app.discovery import Discovery, PeerInfo
from app.self_preview import SelfPreview
from app.session_config import SessionConfig
from app.stream_client import StreamClient
from app.stream_server import StreamServer

logger = logging.getLogger(__name__)


class RoomSession(QObject):
    """Orquestra discovery, transmissão e viewers de uma sala."""

    frame_ready = Signal(str, bytes, int, int)
    peer_disconnected = Signal(str)
    peer_list_changed = Signal(list)
    transmission_changed = Signal(bool)

    def __init__(self, session_config: SessionConfig, parent: QObject | None = None):
        super().__init__(parent)
        self.session_config = session_config
        self.discovery = Discovery(session_config)
        self.stream_server: StreamServer | None = None
        self.self_preview: SelfPreview | None = None
        self.clients: Dict[str, StreamClient] = {}
        self.discovery.set_on_change(self._refresh_peers)
        self.discovery.set_room(session_config.room_id, session_config.room_name)
        self.discovery.start()

    def _refresh_peers(self) -> None:
        peers = [
            peer for peer in self.discovery.get_peers()
            if peer.room_id == self.session_config.room_id
        ]
        active_ids = {peer.user_id for peer in peers}
        for peer in peers:
            if peer.transmitting and peer.user_id not in self.clients:
                self._start_watching(peer)
            elif not peer.transmitting and peer.user_id in self.clients:
                self._stop_watching(peer.user_id)
        for user_id in list(self.clients):
            if user_id not in active_ids:
                self._stop_watching(user_id)
        self.peer_list_changed.emit(peers)

    def _start_watching(self, peer: PeerInfo) -> None:
        def on_frame(data: bytes, width: int, height: int, user_id: str = peer.user_id) -> None:
            self.frame_ready.emit(user_id, data, width, height)

        def on_disconnect(user_id: str = peer.user_id) -> None:
            self.clients.pop(user_id, None)
            self.peer_disconnected.emit(user_id)

        client = StreamClient(peer.ip, peer.stream_port, on_frame, on_disconnect)
        self.clients[peer.user_id] = client
        client.start()

    def _stop_watching(self, user_id: str) -> None:
        client = self.clients.pop(user_id, None)
        if client:
            client.stop()

    def toggle_transmit(self) -> None:
        if self.stream_server:
            self.stop_transmission()
        else:
            self.start_transmission()

    def start_transmission(self) -> None:
        self.stream_server = StreamServer(self.session_config)
        port = self.stream_server.start()
        self.discovery.set_transmitting(True, port)

        def on_frame(data: bytes, width: int, height: int) -> None:
            self.frame_ready.emit(self.discovery.user_id, data, width, height)

        self.self_preview = SelfPreview(self.session_config, on_frame)
        self.self_preview.start()
        self.transmission_changed.emit(True)

    def stop_transmission(self) -> None:
        if self.stream_server:
            self.stream_server.stop()
            self.stream_server = None
        if self.self_preview:
            self.self_preview.stop()
            self.self_preview = None
        self.discovery.set_transmitting(False)
        self.transmission_changed.emit(False)

    def stop(self) -> None:
        self.stop_transmission()
        for user_id in list(self.clients):
            self._stop_watching(user_id)
        self.discovery.stop()
