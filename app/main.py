# app/main.py
import logging
import sys

from PySide6.QtWidgets import QApplication

from app.ui.lobby_window import LobbyWindow


def main() -> None:
    # Configuração de logging centralizada — todos os módulos usam
    # logging.getLogger(__name__) para consistência.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    lobby = LobbyWindow()
    lobby.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
