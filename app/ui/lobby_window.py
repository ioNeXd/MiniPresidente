from __future__ import annotations

# app/ui/lobby_window.py
import logging
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

import app.config
from app.config import __version__
from app.discovery import Discovery, detect_advertise_ip, parse_seed_peers
from app.ui.room_window import RoomWindow

logger = logging.getLogger(__name__)

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_NAME_LENGTH = 32
_MAX_ROOM_LENGTH = 64


class LobbyWindow(QWidget):
    """Tela inicial: entrada de nome, sala, IP anunciado e seed peers."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"MiniPresidente v{__version__}")
        self.resize(400, 400)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel(f"MiniPresidente v{__version__}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Seu nome:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("ex: ioNe")
        self.name_input.setMaxLength(_MAX_NAME_LENGTH)
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Nome da sala:"))
        self.room_input = QLineEdit()
        self.room_input.setPlaceholderText("ex: sala-dos-amigos")
        self.room_input.setMaxLength(_MAX_ROOM_LENGTH)
        self.room_input.returnPressed.connect(self._enter_room)
        layout.addWidget(self.room_input)

        # ─── Campo de IP anunciado ──────────────────────────────────────
        layout.addWidget(QLabel("IP anunciado (VPN: Radmin/Hamachi):"))
        self.ip_input = QLineEdit()
        self.ip_input.setText(detect_advertise_ip())
        self.ip_input.setPlaceholderText("Ex: 25.10.10.5")
        layout.addWidget(self.ip_input)

        # ─── Campo de seed peers (VPN) ──────────────────────────────────
        layout.addWidget(QLabel("IPs de peers (VPN, separados por vírgula):"))
        self.seed_input = QLineEdit()
        self.seed_input.setPlaceholderText("Ex: 25.10.10.5, 25.10.10.8")
        layout.addWidget(self.seed_input)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#c0392b; font-size:11px;")
        layout.addWidget(self.status_label)

        self.enter_btn = QPushButton("Entrar / Criar sala")
        self.enter_btn.setStyleSheet(
            "QPushButton { background:#2980b9; color:white; padding:10px; "
            "font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#3498db; }")
        self.enter_btn.clicked.connect(self._enter_room)
        layout.addWidget(self.enter_btn)

        self.room_window = None

    def _enter_room(self) -> None:
        """
        Valida os campos de entrada, configura a descoberta e abre a janela da sala.
        Salva IP manual e seed peers na configuração global.
        """
        username = self.name_input.text().strip()
        room_name = self.room_input.text().strip()
        manual_ip = self.ip_input.text().strip()
        seed_raw = self.seed_input.text().strip()

        if not username:
            self.status_label.setText("Digite seu nome.")
            return
        if not room_name:
            self.status_label.setText("Digite o nome da sala.")
            return

        if not _VALID_NAME_RE.match(username):
            self.status_label.setText("Nome: apenas letras, números, _ ou -")
            return
        if not _VALID_NAME_RE.match(room_name):
            self.status_label.setText("Sala: apenas letras, números, _ ou -")
            return

        seed_peers = parse_seed_peers(seed_raw)
        app.config.MANUAL_ADVERTISE_IP = manual_ip
        app.config.SEED_PEERS = seed_peers

        room_id = room_name.lower()

        logger.info("User '%s' joining room '%s' (IP=%s, seeds=%s)",
                     username, room_name, manual_ip, seed_peers)

        discovery = Discovery(username, manual_advertise_ip=manual_ip, seed_peers=seed_peers)
        discovery.set_room(room_id, room_name)
        discovery.start()

        self.room_window = RoomWindow(discovery, room_name, username)
        self.room_window.show()
        self.close()
