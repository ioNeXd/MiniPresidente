from __future__ import annotations

# app/ui/lobby_window.py
import logging
import os
import re
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.capture import list_monitors
from app.config import __version__
from app.discovery import detect_advertise_ip, parse_seed_peers
from app.session_config import (
    AUDIO_BITRATE_OPTIONS,
    RESOLUTION_PRESETS,
    VIDEO_FPS_OPTIONS,
    SessionConfig,
    nearest_resolution_bucket,
)
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
        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("IP anunciado (VPN: Radmin/Hamachi):"))
        self.retry_ip_btn = QPushButton("🔄")
        self.retry_ip_btn.setToolTip("Detectar novamente o IP anunciado")
        self.retry_ip_btn.setFixedWidth(32)
        self.retry_ip_btn.clicked.connect(self._retry_advertise_ip)
        ip_layout.addWidget(self.retry_ip_btn)
        layout.addLayout(ip_layout)
        self.ip_input = QLineEdit()
        self.ip_input.setText(detect_advertise_ip())
        self.ip_input.setPlaceholderText("Ex: 25.10.10.5")
        layout.addWidget(self.ip_input)

        # ─── Campo de seed peers (VPN) ──────────────────────────────────
        layout.addWidget(QLabel("IPs de peers (VPN, separados por vírgula):"))
        self.seed_input = QLineEdit()
        self.seed_input.setPlaceholderText("Ex: 25.10.10.5, 25.10.10.8")
        layout.addWidget(self.seed_input)

        self._native_size = self._detect_native_size()
        layout.addWidget(QLabel("Qualidade de vídeo:"))
        quality_layout = QHBoxLayout()
        self.resolution_combo = QComboBox()
        for name in (*RESOLUTION_PRESETS.keys(), "origem"):
            label = name
            if name == "origem":
                label = f"Origem ({self._native_size[0]}×{self._native_size[1]})"
            self.resolution_combo.addItem(label, name)
        self.resolution_combo.setCurrentIndex(self.resolution_combo.findData("1080p"))
        self.resolution_combo.currentIndexChanged.connect(self._resolution_changed)
        quality_layout.addWidget(self.resolution_combo)
        self.fps_combo = QComboBox()
        for fps in VIDEO_FPS_OPTIONS:
            self.fps_combo.addItem(str(fps), fps)
        self.fps_combo.setCurrentText(str(RESOLUTION_PRESETS["1080p"]["fps"]))
        self.fps_combo.currentIndexChanged.connect(self._fps_or_resolution_warning_changed)
        quality_layout.addWidget(self.fps_combo)
        self.video_bitrate_input = QSpinBox()
        self.video_bitrate_input.setSuffix(" kbps")
        self.video_bitrate_input.valueChanged.connect(self._bitrate_changed)
        quality_layout.addWidget(self.video_bitrate_input)
        self.audio_bitrate_combo = QComboBox()
        for bitrate in AUDIO_BITRATE_OPTIONS:
            self.audio_bitrate_combo.addItem(f"{bitrate} kbps", bitrate)
        self.audio_bitrate_combo.setCurrentText("128 kbps")
        quality_layout.addWidget(self.audio_bitrate_combo)
        layout.addLayout(quality_layout)
        self.quality_warning = QLabel("")
        self.quality_warning.setStyleSheet("color:#8a6d3b; font-size:11px;")
        layout.addWidget(self.quality_warning)
        self._resolution_changed()

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
        Cria uma configuração isolada para esta sessão.
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
        room_id = room_name.lower()
        resolution = self.resolution_combo.currentData()
        video_fps = self.fps_combo.currentData()
        bitrate = self.video_bitrate_input.value()
        max_width = self._native_size[0] if resolution == "origem" else RESOLUTION_PRESETS[resolution]["width"]
        session_config = SessionConfig(
            username=username,
            room_name=room_name,
            room_id=room_id,
            manual_advertise_ip=manual_ip,
            seed_peers=seed_peers,
            max_width=max_width,
            resolution=resolution,
            native_size=self._native_size if resolution == "origem" else None,
            video_fps=video_fps,
            video_bitrate_kbps=bitrate,
            audio_bitrate_kbps=self.audio_bitrate_combo.currentData(),
        )

        logger.info("User '%s' joining room '%s' (IP=%s, seeds=%s)",
                     username, room_name, manual_ip, seed_peers)

        self.room_window = RoomWindow(session_config)
        self.room_window.show()
        self.close()

    def _retry_advertise_ip(self) -> None:
        self.ip_input.setText(detect_advertise_ip())

    @staticmethod
    def _detect_native_size() -> tuple[int, int]:
        if sys.platform.startswith("linux") and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        ):
            return (1920, 1080)
        try:
            monitor = list_monitors()[1]
            return monitor["width"], monitor["height"]
        except (IndexError, KeyError, OSError):
            return (1920, 1080)

    def _resolution_changed(self) -> None:
        resolution = self.resolution_combo.currentData()
        preset = RESOLUTION_PRESETS[nearest_resolution_bucket(*self._native_size)] if resolution == "origem" else RESOLUTION_PRESETS[resolution]
        self.video_bitrate_input.setRange(preset["min"], min(preset["max"], 20000))
        self.video_bitrate_input.setValue(preset["bitrate"])
        self._update_quality_warning()

    def _fps_or_resolution_warning_changed(self) -> None:
        self._update_quality_warning()

    def _update_quality_warning(self) -> None:
        resolution = self.resolution_combo.currentData()
        fps = self.fps_combo.currentData()
        high_resolution = resolution == "1440p" or (
            resolution == "origem" and nearest_resolution_bucket(*self._native_size) == "1440p"
        )
        if high_resolution and fps == 120:
            self.quality_warning.setText("Combinação pesada, pode engasgar sem placa de captura dedicada.")
        elif high_resolution and fps == 60:
            self.quality_warning.setText("60 FPS em alta resolução pode exigir mais CPU e banda.")
        else:
            self.quality_warning.setText("")

    def _bitrate_changed(self, value: int) -> None:
        minimum = self.video_bitrate_input.minimum()
        maximum = self.video_bitrate_input.maximum()
        if value < minimum or value > maximum:
            self.video_bitrate_input.setValue(max(minimum, min(value, maximum)))
