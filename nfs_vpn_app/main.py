#!/usr/bin/env python3
"""Точка входа приложения NFS VPN Connect."""

import sys
import platform
from PyQt5.QtWidgets import QApplication, QMessageBox
from nfs_vpn_app.ui.main_window import MainWindow
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


def check_requirements():
    """Проверить системные требования."""
    system = platform.system()
    logger.info(f"System: {system}")

    # Проверить OpenVPN
    import subprocess

    try:
        result = subprocess.run(
            ["openvpn", "--version"], capture_output=True, timeout=5
        )
        if result.returncode != 0:
            logger.warning("OpenVPN might not be installed")
    except Exception as e:
        logger.error(f"OpenVPN check failed: {str(e)}")
        QMessageBox.critical(
            None,
            "Missing Dependency",
            "OpenVPN is not installed or not in PATH.\n\n"
            "Please install OpenVPN:\n"
            "- Windows: Download from https://openvpn.net\n"
            "- Linux: sudo apt install openvpn\n"
            "- macOS: brew install openvpn",
        )
        return False

    logger.info("All requirements met")
    return True


def main():
    """Главная функция приложения."""
    try:
        logger.info("Starting NFS VPN Connect application")

        # Проверить требования
        if not check_requirements():
            return 1

        # Создать приложение
        app = QApplication(sys.argv)

        # Установить стиль
        app.setStyle("Fusion")

        # Создать и показать главное окно
        window = MainWindow()
        window.show()

        logger.info("Application started successfully")

        # Запустить цикл приложения
        exit_code = app.exec_()

        logger.info(f"Application closed with exit code: {exit_code}")
        return exit_code

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        QMessageBox.critical(
            None,
            "Fatal Error",
            f"An unexpected error occurred:\n{str(e)}\n\nCheck logs for details.",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
