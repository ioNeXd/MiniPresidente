from __future__ import annotations

import logging
from typing import Dict

from PySide6.QtCore import QObject, Qt, QThread, Signal
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
from app.discovery import PeerInfo
from app.room_session import RoomSession
from app.session_config import SessionConfig
from app.ui.update_dialog import UpdateDialog
from app.updater import check_for_updates, is_frozen

logger = logging.getLogger(__name__)

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


class _ManualUpdateWorker(QObject):
    result = Signal(object)
    finished_signal = Signal()

    def run(self) -> None:
        try:
            info = check_for_updates(force=True)
        except Exception:
            info = None
        self.result.emit(info)
        self.finished_signal.emit()


class VideoTile(QWidget):
    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.image_label = QLabel("Conectando...")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(320, 180)
        self.image_label.setStyleSheet(
            "QLabel { background:#111; color:#888; border:1px solid #333; "
            "border-radius:6px; font-size:12px; }")
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("QLabel { color:#ddd; font-size:11px; }")
        layout.addWidget(self.image_label)
        layout.addWidget(self.title_label)

    def set_frame(self, rgb_bytes: bytes, width: int, height: int) -> None:
        img = QImage(rgb_bytes, width, height, QImage.Format.Format_RGB888).copy()
        if img.isNull():
            return
        pixmap = QPixmap.fromImage(img).scaled(
            max(self.image_label.width(), 320), max(self.image_label.height(), 180),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(pixmap)


def _sanitize_display_name(name: str) -> str:
    return name[:32] if name else "Desconhecido"


class RoomWindow(QMainWindow):
    def __init__(self, session_config: SessionConfig):
        super().__init__()
        self.session_config = session_config
        self.username = session_config.username
        self.setWindowTitle(f"MiniPresidente — Sala: {session_config.room_name} v{__version__}")
        self.resize(1000, 700)
        self._update_in_progress = False
        self._session_stopped = False
        self.session = RoomSession(session_config, self)
        self.tiles: Dict[str, VideoTile] = {}
        self._build_ui()
        self.session.frame_ready.connect(self._on_frame_ready)
        self.session.peer_disconnected.connect(self._remove_tile)
        self.session.peer_list_changed.connect(self._update_peers)
        self.session.transmission_changed.connect(self._update_transmit_button)

    def _build_ui(self) -> None:
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
        self.transmit_btn.clicked.connect(self.session.toggle_transmit)
        controls.addWidget(self.transmit_btn)
        self.back_btn = QPushButton("← Voltar")
        self.back_btn.clicked.connect(self.close)
        controls.addWidget(self.back_btn)
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

    def _update_peers(self, peers: list[PeerInfo]) -> None:
        self.member_list.clear()
        self.member_list.addItem(f"🟢 {self.username} (você)")
        active_ids = set()
        for peer in peers:
            status = "🔴" if peer.transmitting else "⚪"
            self.member_list.addItem(
                f"{status} {_sanitize_display_name(peer.username)} ({peer.ip})")
            active_ids.add(peer.user_id)
            if peer.transmitting and peer.user_id not in self.tiles:
                self.tiles[peer.user_id] = VideoTile(_sanitize_display_name(peer.username))
            elif not peer.transmitting:
                self._remove_tile(peer.user_id)
        for user_id in list(self.tiles):
            if user_id not in active_ids and user_id != self.session.discovery.user_id:
                self._remove_tile(user_id)
        self._relayout_grid()

    def _remove_tile(self, user_id: str) -> None:
        tile = self.tiles.pop(user_id, None)
        if tile:
            self.grid.removeWidget(tile)
            tile.deleteLater()
            self._relayout_grid()

    def _relayout_grid(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        for index, tile in enumerate(self.tiles.values()):
            self.grid.addWidget(tile, index // GRID_COLUMNS, index % GRID_COLUMNS)

    def _on_frame_ready(self, user_id: str, data: bytes, width: int, height: int) -> None:
        tile = self.tiles.get(user_id)
        if tile:
            tile.set_frame(data, width, height)

    def _update_transmit_button(self, transmitting: bool) -> None:
        if transmitting:
            self.transmit_btn.setText("⏹ Parar Transmissão")
            self.transmit_btn.setStyleSheet(STYLE_STOP_BTN)
            user_id = self.session.discovery.user_id
            if user_id not in self.tiles:
                self.tiles[user_id] = VideoTile(f"{self.username} (você — transmitindo)")
                self._relayout_grid()
        else:
            self.transmit_btn.setText("🔴 Transmitir")
            self.transmit_btn.setStyleSheet(STYLE_TRANSMIT_BTN)
            self._remove_tile(self.session.discovery.user_id)

    def _check_updates(self) -> None:
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
        UpdateDialog(release_info, parent=self).exec()

    def closeEvent(self, event) -> None:
        if self._session_stopped:
            event.accept()
            return
        self._session_stopped = True
        self.session.stop()
        from app.ui.lobby_window import LobbyWindow

        self.lobby_window = LobbyWindow()
        self.lobby_window.show()
        if getattr(self, "_update_thread", None) and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait()
        super().closeEvent(event)
