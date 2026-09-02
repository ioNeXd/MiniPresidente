from __future__ import annotations

# app/main.py
import logging
import sys

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from app.ui.lobby_window import LobbyWindow

logger = logging.getLogger(__name__)


class UpdateController(QObject):
    """Gerencia a verificação automática de updates ao iniciar.

    Mantém referências ao QThread e worker para evitar garbage collection.
    Usa flag _update_in_progress para evitar diálogos simultâneos.
    """
    _check_done = Signal(object)  # dict ou None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _AutoUpdateWorker | None = None
        self._update_in_progress = False
        self._lobby: LobbyWindow | None = None

    def start_check(self, lobby: LobbyWindow) -> None:
        """Inicia verificação automática (force=False) na lobby."""
        self._lobby = lobby
        self._update_in_progress = True

        self._thread = QThread(self)
        self._worker = _AutoUpdateWorker()
        self._worker.moveToThread(self._thread)

        self._worker.result.connect(self._on_check_result)
        self._worker.done.connect(self._on_thread_done)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_check_result(self, release_info) -> None:
        if self._update_in_progress and release_info is not None:
            from app.ui.update_dialog import UpdateDialog
            dialog = UpdateDialog(release_info, parent=self._lobby)
            dialog.exec()
        self._update_in_progress = False

    def _on_thread_done(self) -> None:
        self._update_in_progress = False
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
            self._worker = None


class _AutoUpdateWorker(QObject):
    """Worker que roda check_for_updates(force=False) em thread."""
    result = Signal(object)
    done = Signal()

    def run(self) -> None:
        from app.updater import check_for_updates
        try:
            info = check_for_updates(force=False)
        except Exception:
            logger.exception("Error during auto-update check")
            info = None
        self.result.emit(info)
        self.done.emit()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    lobby = LobbyWindow()
    lobby.show()

    # Verificação automática de update (roda em background)
    controller = UpdateController(app)
    controller.start_check(lobby)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
