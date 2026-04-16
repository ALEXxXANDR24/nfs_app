#!/usr/bin/env python3
"""Точка входа приложения NFS VPN Connect."""

import sys
import platform
import subprocess
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt5.QtCore import Qt

# Флаг для скрытия окна консоли на Windows
if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0
from nfs_vpn_app.ui.main_window import MainWindow
from nfs_vpn_app.ui.login_dialog import LoginDialog
from nfs_vpn_app.core.logger import Logger
from nfs_vpn_app.core.ssh_client import SSHClient
from nfs_vpn_app.core.system_gid_manager import ServerGIDManager, SystemGIDManager
from nfs_vpn_app.core.vpn_manager import VPNManager
from nfs_vpn_app.platform_specific.windows import WindowsCommands

logger = Logger(__name__)


def check_requirements():
    """Проверить системные требования."""
    system = platform.system()
    logger.info(f"System: {system}")

    # # Проверить NFS Client для Windows
    if system == "Windows":
        logger.info("Checking NFS Client for Windows...")
        if not WindowsCommands.check_nfs_client_installed():
            logger.warning("NFS Client not found, attempting to install...")

            success, message = WindowsCommands.ensure_nfs_client_installed()

            if not success:
                logger.error(f"NFS Client installation failed: {message}")
                return False
            else:
                logger.info(f"NFS Client installation: {message}")
        else:
            logger.info("NFS Client is installed")

    # Проверить OpenVPN
    try:
        result = subprocess.run(
            ["openvpn", "--version"],
            capture_output=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            logger.warning("OpenVPN might not be installed")
    except Exception as e:
        logger.error(f"OpenVPN check failed: {str(e)}")

    # Проверить paramiko для SSH
    try:
        import paramiko

        logger.info("paramiko SSH library found")
    except ImportError:
        logger.error("paramiko SSH library not found")
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

        # Показать окно авторизации
        login_dialog = LoginDialog()

        # Переменные для хранения данных авторизации
        auth_data = {"email": None, "username": None}

        def on_login_attempt(email: str, username: str):
            """Обработчик попытки логина."""
            logger.info(f"Processing login for: {email}")

            # Создать прогресс диалог
            progress = QProgressDialog("Connecting to VPN...", None, 0, 0, login_dialog)
            progress.setWindowModality(Qt.WindowModal)
            progress.setCancelButton(None)
            progress.setStyleSheet(
                "QProgressDialog { background-color: #2a2a2a; }"
                "QProgressDialog QLabel { color: #ffffff; }"
            )
            progress.show()
            app.processEvents()

            # STEP 1: Подключиться к VPN
            vpn_manager = VPNManager()

            if not vpn_manager.connect():
                logger.error("VPN connection failed during login")
                QMessageBox.critical(
                    login_dialog,
                    "VPN Connection Failed",
                    "Could not establish VPN connection.\n\n"
                    "Please check:\n"
                    "- Internet connection\n"
                    "- OpenVPN is installed\n"
                    "- VPN configuration is valid",
                )
                progress.close()
                return

            logger.info("VPN connected successfully during login")

            # STEP 2: Обновить прогресс - подключиться по SSH
            progress.setLabelText("Connecting to server via SSH...")
            app.processEvents()

            # Инициализировать SSH клиент (подключиться к серверу)
            ssh_client = SSHClient(
                hostname="172.18.130.50",
                port=5282,
                username="nvt-126",
                password="22'@4RqW",
            )

            success, msg = ssh_client.connect()
            if not success:
                logger.error(f"SSH connection failed: {msg}")
                QMessageBox.critical(
                    login_dialog,
                    "Server Connection Failed",
                    f"Could not connect to server:\n\n{msg}\n\n"
                    "Please ensure:\n"
                    "- VPN connection is established\n"
                    "- Server is reachable\n"
                    "- SSH credentials are correct",
                )
                progress.close()
                vpn_manager.disconnect()
                return

            logger.info("SSH connection established")

            # STEP 3: Обновить прогресс - инициализировать GID
            progress.setLabelText("Initializing your account on the server...")
            app.processEvents()

            # Инициализировать GID на сервере
            try:
                server_gid_manager = ServerGIDManager(ssh_client)
                gid_success, gid_number, gid_msg = server_gid_manager.setup_user_gid(
                    username
                )

                if not gid_success:
                    logger.error(f"GID setup failed: {gid_msg}")
                    QMessageBox.critical(
                        login_dialog,
                        "GID Setup Failed",
                        f"Could not setup GID on server:\n\n{gid_msg}",
                    )
                    progress.close()
                    ssh_client.disconnect()
                    vpn_manager.disconnect()
                    return

                logger.info(f"GID setup successful: {gid_msg}")

                # STEP 4: Установить GID в локальной системе
                progress.setLabelText("Configuring local system...")
                app.processEvents()

                system_gid_manager = SystemGIDManager()
                gid_local_success, gid_local_msg = system_gid_manager.set_anonymous_gid(
                    gid_number
                )

                if not gid_local_success:
                    logger.warning(f"Local GID setup warning: {gid_local_msg}")
                else:
                    logger.info(f"Local GID setup successful: {gid_local_msg}")

                # Сохранить данные авторизации
                auth_data["email"] = email
                auth_data["username"] = username
                auth_data["gid"] = gid_number
                auth_data["vpn_manager"] = vpn_manager  # Сохранить VPN менеджер

                progress.close()
                ssh_client.disconnect()
                # Не отключаем VPN - он нужен для NFS!

                # Закрыть диалог логина
                login_dialog.accept()

            except Exception as e:
                logger.error(f"GID initialization error: {str(e)}")
                QMessageBox.critical(
                    login_dialog,
                    "Initialization Failed",
                    f"Error during account initialization:\n\n{str(e)}",
                )
                progress.close()
                ssh_client.disconnect()
                vpn_manager.disconnect()
                return

        # Подключить сигнал логина
        login_dialog.login_success.connect(on_login_attempt)

        # Показать диалог логина
        if login_dialog.exec_() != QMessageBox.Accepted:
            logger.info("User cancelled login")
            return 0

        if auth_data["username"] is None:
            logger.error("Login failed - no user data")
            return 1

        logger.info(f"User authorized: {auth_data['email']}")

        # Создать и показать главное окно с данными пользователя
        window = MainWindow(vpn_manager=auth_data.get("vpn_manager"))
        window.current_user = auth_data["username"]
        window.current_email = auth_data["email"]
        window.current_gid = auth_data.get("gid", 2001)
        window.show()

        logger.info("Application started successfully")

        # Запустить цикл приложения
        exit_code = app.exec_()

        # Отключиться от VPN при выходе
        vpn_mgr = auth_data.get("vpn_manager")
        if vpn_mgr:
            logger.info("Disconnecting VPN on application exit...")
            vpn_mgr.disconnect()

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
