from __future__ import annotations

# app/ui/update_dialog.py
import logging
import os
import sys
import tempfile
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.updater import download_file, install_update, verify_hash

logger = logging.getLogger(__name__)


class DownloadWorker(QObject):
    """Worker que roda em QThread para download + verify + install."""
    progress = Signal(int)
    finished = Signal(str)   # caminho do arquivo baixado
    error = Signal(str)

    def __init__(self, exe_url: str, hash_url: Optional[str], parent=None):
        super().__init__(parent)
        self.exe_url = exe_url
        self.hash_url = hash_url
        self._cancelled = False

    def run(self) -> None:
        try:
            # Baixar para tempdir
            dest = os.path.join(tempfile.gettempdir(), "MiniPresidente_update.exe")

            def on_progress(pct: int) -> None:
                if not self._cancelled:
                    self.progress.emit(pct)

            logger.info("Downloading update from %s", self.exe_url)
            if not download_file(self.exe_url, dest, on_progress):
                self.error.emit("Falha no download da atualização.")
                return

            if self._cancelled:
                return

            # Verificar hash
            if self.hash_url:
                logger.info("Verifying SHA-256 hash")
                if not verify_hash(dest, self.hash_url):
                    os.remove(dest)
                    self.error.emit("Falha na verificação de integridade (SHA-256).")
                    return

            logger.info("Download and verification complete")
            self.finished.emit(dest)

        except Exception as exc:
            logger.exception("Unexpected error during update")
            self.error.emit(f"Erro inesperado: {exc}")

    def cancel(self) -> None:
        self._cancelled = True


class UpdateDialog(QDialog):
    """Diálogo modal de atualização com download, progresso e instalação."""

    def __init__(self, release_info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atualização Disponível")
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self._release = release_info
        self._choice: str = "later"
        self._worker: Optional[DownloadWorker] = None
        self._thread: Optional[QThread] = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Versões
        from app.config import __version__
        layout.addWidget(QLabel(f"Versão atual: v{__version__}"))
        layout.addWidget(QLabel(f"Nova versão: v{self._release['version']}"))

        # Release notes
        layout.addWidget(QLabel("Notas da versão:"))
        notes = QTextEdit()
        notes.setPlainText(self._release.get("release_notes", ""))
        notes.setReadOnly(True)
        notes.setMaximumHeight(150)
        layout.addWidget(notes)

        # Botões
        btn_layout = QHBoxLayout()

        self._update_btn = QPushButton("Sim, atualizar agora")
        self._update_btn.setStyleSheet(
            "QPushButton { background:#27ae60; color:white; padding:8px 16px; "
            "font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#2ecc71; }")
        self._update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(self._update_btn)

        self._later_btn = QPushButton("Lembrar mais tarde")
        self._later_btn.clicked.connect(self._on_later)
        btn_layout.addWidget(self._later_btn)

        self._never_btn = QPushButton("Nunca mais")
        self._never_btn.clicked.connect(self._on_never)
        btn_layout.addWidget(self._never_btn)

        layout.addLayout(btn_layout)

    def _on_update(self) -> None:
        self._update_btn.setEnabled(False)
        self._later_btn.setEnabled(False)
        self._never_btn.setEnabled(False)

        self._thread = QThread(self)
        self._worker = DownloadWorker(
            self._release["exe_url"],
            self._release.get("hash_url"),
        )
        self._worker.moveToThread(self._thread)

        # Progress dialog
        self._progress = QProgressDialog("Baixando atualização...", "Cancelar", 0, 100, self)
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)

        # Conectar sinais
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.error.connect(self._on_download_error)
        self._progress.canceled.connect(self._on_cancel)

        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_download_finished(self, file_path: str) -> None:
        self._progress.close()
        self._choice = "update"

        # Fechar todas as janelas e instalar
        app = QApplication.instance()
        if app:
            QApplication.closeAllWindows()
            app.quit()

        install_update(file_path)
        sys.exit(0)

    def _on_download_error(self, msg: str) -> None:
        self._progress.close()
        QMessageBox.warning(self, "Erro na Atualização", msg)
        self._update_btn.setEnabled(True)
        self._later_btn.setEnabled(True)
        self._never_btn.setEnabled(True)

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        self._update_btn.setEnabled(True)
        self._later_btn.setEnabled(True)
        self._never_btn.setEnabled(True)

    def _on_later(self) -> None:
        self._choice = "later"
        self.accept()

    def _on_never(self) -> None:
        self._choice = "never"
        from app.update_state import add_ignored_version
        add_ignored_version(self._release["version"])
        self.accept()

