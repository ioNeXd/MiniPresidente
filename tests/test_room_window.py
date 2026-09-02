from __future__ import annotations

import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QWidget

from app.session_config import SessionConfig
from app.ui import lobby_window
from app.ui.room_window import RoomWindow


class _FakeLobbyWindow(QWidget):
    def show(self) -> None:
        pass


def test_close_event_stops_session_and_creates_one_lobby(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(lobby_window, "LobbyWindow", _FakeLobbyWindow)

    room = RoomWindow(SessionConfig("user", "room", "room"))
    stop_spy = Mock(wraps=room.session.stop)
    room.session.stop = stop_spy

    room.closeEvent(QCloseEvent())
    first_lobby = room.lobby_window
    room.closeEvent(QCloseEvent())

    assert stop_spy.call_count == 1
    assert room.lobby_window is first_lobby

    room.lobby_window.close()
    app.processEvents()


def test_lobby_resolution_updates_video_bitrate_controls():
    app = QApplication.instance() or QApplication([])
    window = lobby_window.LobbyWindow()
    window.resolution_combo.setCurrentIndex(window.resolution_combo.findData("720p"))
    assert window.video_bitrate_input.minimum() == 1000
    assert window.video_bitrate_input.maximum() == 6000
    assert window.video_bitrate_input.value() == 2500
    window.close()
    app.processEvents()


def test_lobby_fps_default_and_custom_bitrate_preservation():
    app = QApplication.instance() or QApplication([])
    window = lobby_window.LobbyWindow()
    assert window.fps_combo.currentData() == 30

    window.video_bitrate_input.setValue(3500)
    window.fps_combo.setCurrentText("60")
    assert window.video_bitrate_input.value() == 3500

    window.resolution_combo.setCurrentIndex(window.resolution_combo.findData("720p"))
    assert window.video_bitrate_input.value() == 2500
    window.close()
    app.processEvents()
