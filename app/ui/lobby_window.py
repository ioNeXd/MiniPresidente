# app/ui/lobby_window.py
import logging
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

import app.config
from app.discovery import Discovery
from app.ui.room_window import RoomWindow

logger = logging.getLogger(__name__)

# Validação de entrada: apenas letras, números, hífens e underscores
_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_NAME_LENGTH = 32
_MAX_ROOM_LENGTH = 64


class LobbyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MiniPresidente")
        self.resize(380, 340)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("MiniPresidente")
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

        # ─── Campo de IP (detecção automática + override manual) ────────
        # Discovery._local_ip() já implementa a lógica VPN-aware:
        # prioriza IPs que não são da LAN física (192.168, 10, 172.16-31).
        layout.addWidget(QLabel("IP anunciado (VPN: Radmin/Hamachi):"))
        self.ip_input = QLineEdit()
        detected_ip = Discovery._local_ip()
        self.ip_input.setText(detected_ip)
        self.ip_input.setPlaceholderText("Ex: 25.10.10.5")
        layout.addWidget(self.ip_input)

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
        username = self.name_input.text().strip()
        room_name = self.room_input.text().strip()
        manual_ip = self.ip_input.text().strip()

        if not username:
            self.status_label.setText("Digite seu nome.")
            return
        if not room_name:
            self.status_label.setText("Digite o nome da sala.")
            return

        # Validação de caracteres: apenas alfanuméricos, hífens e underscores
        if not _VALID_NAME_RE.match(username):
            self.status_label.setText("Nome: apenas letras, números, _ ou -")
            return
        if not _VALID_NAME_RE.match(room_name):
            self.status_label.setText("Sala: apenas letras, números, _ ou -")
            return

        # Salva o IP informado na config global para o Discovery usar
        app.config.MANUAL_ADVERTISE_IP = manual_ip

        room_id = room_name.lower().replace(" ", "-")

        logger.info("User '%s' joining room '%s' with advertise IP '%s'", username, room_name, manual_ip)
        discovery = Discovery(username)
        discovery.set_room(room_id, room_name)
        discovery.start()

        self.room_window = RoomWindow(discovery, room_name, username)
        self.room_window.show()
        self.close()
