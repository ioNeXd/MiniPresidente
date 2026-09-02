from __future__ import annotations

# app/ui/room_window.py
import logging
from typing import Dict, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import GRID_COLUMNS, __version__
from app.discovery import Discovery, PeerInfo
from app.self_preview import SelfPreview
from app.stream_client import StreamClient
from app.stream_server import StreamServer
from app.ui.update_dialog import UpdateDialog
from app.updater import check_for_updates, is_frozen

logger = logging.getLogger(__name__)

# ─── Estilos CSS centralizados ───────────────────────────────────────────
STYLE_TRANSMIT_BTN = (
    "QPushButton { background:#c0392b; color:white; padding:10px 20px; "
    "font-weight:bold; border-radius:6px; }"
    "QPushButton:hover { background:#e74c3c; }"
)
STYLE_STOP_BTN = (
    "QPushButton { background:#27ae60; color:white; padding:10px 20px; "
    "font-weight:bold; border-radius:6px; }"
    "QPushButton:hover { background:#2ecc71; }"
)


class Bridge(QObject):
    frame_ready = Signal(str, bytes)
    peer_disconnected = Signal(str)


class _ManualUpdateWorker(QObject):
    """Worker que roda check_for_updates em thread separada."""
    result = Signal(object)  # dict ou None
    finished_signal = Signal()

    def run(self) -> None:
        try:
            info = check_for_updates(force=True)
        except Exception:
            info = None
        self.result.emit(info)
        self.finished_signal.emit()


class VideoTile(QWidget):
    """Tile individual que exibe o frame JPEG de um peer."""

    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.image_label = QLabel("Conectando...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(320, 180)
        self.image_label.setStyleSheet(
            "QLabel { background:#111; color:#888; border:1px solid #333; "
            "border-radius:6px; font-size:12px; }")

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("QLabel { color:#ddd; font-size:11px; }")

        layout.addWidget(self.image_label)
        layout.addWidget(self.title_label)

    def set_frame(self, jpeg_bytes: bytes) -> None:
        img = QImage.fromData(jpeg_bytes, "JPEG")
        if img.isNull():
            return
        pix = QPixmap.fromImage(img).scaled(
            max(self.image_label.width(), 320), max(self.image_label.height(), 180),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)


def _sanitize_display_name(name: str) -> str:
    """Sanitiza nome de peer para exibição segura na UI."""
    return name[:32] if name else "Desconhecido"


class RoomWindow(QMainWindow):
    """Janela principal da sala: grid de telas, lista de membros e controles."""

    def __init__(self, discovery: Discovery, room_name: str, username: str):
        super().__init__()
        self.discovery = discovery
        self.username = username
        self.setWindowTitle(f"MiniPresidente — Sala: {room_name} v{__version__}")
        self.resize(1000, 700)
        self._update_in_progress = False

        self.bridge = Bridge()
        self.bridge.frame_ready.connect(self._on_frame_ready)
        self.bridge.peer_disconnected.connect(self._on_peer_disconnected)

        self.stream_server: Optional[StreamServer] = None
        self.self_preview: Optional[SelfPreview] = None
        self.clients: Dict[str, StreamClient] = {}
        self.tiles: Dict[str, VideoTile] = {}

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_peers)
        self.timer.start(1000)

    def _build_ui(self) -> None:
        """Monta o layout principal da janela."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        grid_container = QWidget()
        grid_container.setLayout(self.grid)
        left_layout.addWidget(grid_container)

        controls = QHBoxLayout()
        self.transmit_btn = QPushButton("🔴 Transmitir")
        self.transmit_btn.setStyleSheet(STYLE_TRANSMIT_BTN)
        self.transmit_btn.clicked.connect(self._toggle_transmit)
        controls.addWidget(self.transmit_btn)

        self.update_btn = QPushButton("🔄 Verificar Atualizações")
        self.update_btn.clicked.connect(self._check_updates)
        controls.addWidget(self.update_btn)

        controls.addStretch()
        left_layout.addLayout(controls)
        main_layout.addWidget(left, stretch=3)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Membros na sala"))
        self.member_list = QListWidget()
        right_layout.addWidget(self.member_list)
        main_layout.addWidget(right, stretch=1)

    def _refresh_peers(self) -> None:
        """Atualiza lista de membros e conecta/desconecta viewers."""
        peers = [p for p in self.discovery.get_peers() if p.room_id == self.discovery.room_id]

        self.member_list.clear()
        self.member_list.addItem(f"🟢 {self.username} (você)")
        active_ids = set()
        for p in peers:
            status = "🔴" if p.transmitting else "⚪"
            display_name = _sanitize_display_name(p.username)
            self.member_list.addItem(f"{status} {display_name} ({p.ip})")
            active_ids.add(p.user_id)

            if p.transmitting and p.user_id not in self.clients:
                self._start_watching(p)
            elif not p.transmitting and p.user_id in self.clients:
                self._stop_watching(p.user_id)

        for uid in list(self.clients.keys()):
            if uid not in active_ids:
                self._stop_watching(uid)

    def _start_watching(self, peer: PeerInfo) -> None:
        """Conecta a um peer transmissor e exibe seus frames."""
        tile = VideoTile(_sanitize_display_name(peer.username))
        self.tiles[peer.user_id] = tile
        self._relayout_grid()

        def on_frame(data: bytes, uid: str = peer.user_id) -> None:
            self.bridge.frame_ready.emit(uid, data)

        def on_disconnect(uid: str = peer.user_id) -> None:
            self.bridge.peer_disconnected.emit(uid)

        client = StreamClient(peer.ip, peer.stream_port, on_frame, on_disconnect)
        client.start()
        self.clients[peer.user_id] = client

    def _stop_watching(self, user_id: str) -> None:
        client = self.clients.pop(user_id, None)
        if client:
            client.stop()
        tile = self.tiles.pop(user_id, None)
        if tile:
            self.grid.removeWidget(tile)
            tile.deleteLater()
        self._relayout_grid()

    def _relayout_grid(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        for i, tile in enumerate(self.tiles.values()):
            self.grid.addWidget(tile, i // GRID_COLUMNS, i % GRID_COLUMNS)

    def _on_frame_ready(self, user_id: str, data: bytes) -> None:
        tile = self.tiles.get(user_id)
        if tile:
            tile.set_frame(data)

    def _on_peer_disconnected(self, user_id: str) -> None:
        self._stop_watching(user_id)

    def _toggle_transmit(self) -> None:
        if self.stream_server:
            self._stop_transmission()
        else:
            self._start_transmission()

    def _start_transmission(self) -> None:
        self.stream_server = StreamServer()
        port = self.stream_server.start()
        self.discovery.set_transmitting(True, port)
        self.transmit_btn.setText("⏹ Parar Transmissão")
        self.transmit_btn.setStyleSheet(STYLE_STOP_BTN)

        tile = VideoTile(f"{self.username} (você — transmitindo)")
        self.tiles[self.discovery.user_id] = tile
        self._relayout_grid()

        def on_frame(data: bytes) -> None:
            self.bridge.frame_ready.emit(self.discovery.user_id, data)

        self.self_preview = SelfPreview(on_frame)
        self.self_preview.start()

    def _stop_transmission(self) -> None:
        if self.stream_server:
            self.stream_server.stop()
            self.stream_server = None
        if self.self_preview:
            self.self_preview.stop()
            self.self_preview = None
        self.discovery.set_transmitting(False)
        self.transmit_btn.setText("🔴 Transmitir")
        self.transmit_btn.setStyleSheet(STYLE_TRANSMIT_BTN)

        tile = self.tiles.pop(self.discovery.user_id, None)
        if tile:
            self.grid.removeWidget(tile)
            tile.deleteLater()
        self._relayout_grid()

    def _check_updates(self) -> None:
        """Verificação manual de updates (chamada pelo botão)."""
        if self._update_in_progress:
            return
        self._update_in_progress = True
        self.update_btn.setEnabled(False)

        self._update_thread = QThread(self)
        self._update_worker = _ManualUpdateWorker()
        self._update_worker.moveToThread(self._update_thread)

        self._update_worker.result.connect(self._on_update_check_result)
        self._update_worker.finished_signal.connect(self._update_thread.quit)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_thread.start()

    def _on_update_check_result(self, release_info) -> None:
        """Exibe o resultado da verificação de atualização."""
        self._update_in_progress = False
        self.update_btn.setEnabled(True)

        if release_info is None:
            if not is_frozen():
                QMessageBox.information(
                    self, "Verificação de Atualização",
                    "Atualização automática indisponível em modo de desenvolvimento.")
            else:
                QMessageBox.information(
                    self, "Verificação de Atualização",
                    f"Você já está na versão mais recente (v{__version__}).")
            return

        dialog = UpdateDialog(release_info, parent=self)
        dialog.exec()

    def closeEvent(self, event) -> None:
        """Para todas as threads e recursos antes de fechar."""
        self.timer.stop()
        if self.stream_server:
            self.stream_server.stop()
        if self.self_preview:
            self.self_preview.stop()
        for client in self.clients.values():
            client.stop()
        # Finaliza thread de verificação de updates se estiver rodando
        if getattr(self, "_update_thread", None) and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait()
        self.discovery.set_transmitting(False)
        self.discovery.stop()
        super().closeEvent(event)
