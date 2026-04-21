import sys
import platform
import subprocess
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt5.QtCore import Qt

from nfs_vpn_app.ui.main_window import MainWindow
from nfs_vpn_app.ui.login_dialog import LoginDialog
from nfs_vpn_app.core.logger import Logger
from nfs_vpn_app.core.config_manager import ConfigManager, load_env_file
from nfs_vpn_app.core.ssh_client import SSHClient
from nfs_vpn_app.core.system_gid_manager import ServerGIDManager, SystemGIDManager
from nfs_vpn_app.core.vpn_manager import VPNManager
from nfs_vpn_app.platform_specific.windows import WindowsCommands

if platform.system() == "Linux":
    from nfs_vpn_app.platform_specific.linux import LinuxCommands
elif platform.system() == "Darwin":
    from nfs_vpn_app.platform_specific.macos import MacOSCommands

if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0

logger = Logger(__name__)


def check_requirements():
    """Проверить системные требования."""
    system = platform.system()
    logger.info(f"System: {system}")

    # ============ WINDOWS ============
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

    # ============ LINUX ============
    elif system == "Linux":
        logger.info("Checking NFS Common for Linux...")
        if not LinuxCommands.check_nfs_common_installed():
            logger.warning("nfs-common not found, attempting to install...")

            success, message = LinuxCommands.ensure_nfs_common_installed()

            if not success:
                logger.error(f"nfs-common installation failed: {message}")
                return False
            else:
                logger.info(f"nfs-common installation: {message}")
        else:
            logger.info("nfs-common is installed")

        logger.info("Checking OpenVPN for Linux...")
        if not LinuxCommands.check_openvpn_installed():
            logger.warning("OpenVPN not found, attempting to install...")

            success, message = LinuxCommands.ensure_openvpn_installed()

            if not success:
                logger.error(f"OpenVPN installation failed: {message}")
                return False
            else:
                logger.info(f"OpenVPN installation: {message}")
        else:
            logger.info("OpenVPN is installed")

    # ============ macOS ============
    elif system == "Darwin":
        logger.info("Checking NFS tools for macOS...")
        if not MacOSCommands.check_nfs_tools_installed():
            logger.warning("NFS tools not found, attempting to install via Homebrew...")

            success, message = MacOSCommands.ensure_nfs_tools_installed()

            if not success:
                logger.error(f"NFS tools installation failed: {message}")
                return False
            else:
                logger.info(f"NFS tools installation: {message}")
        else:
            logger.info("NFS tools are installed")

        logger.info("Checking OpenVPN for macOS...")
        if not MacOSCommands.check_openvpn_installed():
            logger.warning("OpenVPN not found, attempting to install via Homebrew...")

            success, message = MacOSCommands.ensure_openvpn_installed()

            if not success:
                logger.error(f"OpenVPN installation failed: {message}")
                return False
            else:
                logger.info(f"OpenVPN installation: {message}")
        else:
            logger.info("OpenVPN is installed")

    # ============ CHECK PYTHON DEPENDENCIES ============
    try:
        import paramiko

        logger.info("paramiko SSH library found")
    except ImportError:
        logger.error("paramiko SSH library not found")
        return False

    logger.info("All requirements met")
    return True


def main():
    try:
        logger.info("Starting NFS VPN Connect application")

        if not check_requirements():
            return 1

        app = QApplication(sys.argv)

        app.setStyle("Fusion")

        login_dialog = LoginDialog()

        auth_data = {"email": None, "username": None}

        def on_login_attempt(email: str, username: str):
            logger.info(f"Processing login for: {email}")

            progress = QProgressDialog("Connecting to VPN...", None, 0, 0, login_dialog)
            progress.setWindowModality(Qt.WindowModal)
            progress.setCancelButton(None)
            progress.setStyleSheet(
                "QProgressDialog { background-color: #2a2a2a; }"
                "QProgressDialog QLabel { color: #ffffff; }"
            )
            progress.show()
            app.processEvents()

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

            progress.setLabelText("Connecting to server via SSH...")
            app.processEvents()

            # Загрузить конфигурацию с переменными окружения
            config = ConfigManager()

            # Получить SSH учетные данные из переменных окружения
            ssh_host = config.env_vars.get("SSH_SERVER_HOST", "172.18.130.50")
            ssh_port = int(config.env_vars.get("SSH_SERVER_PORT", "5282"))
            ssh_username = config.env_vars.get("SSH_SERVER_USERNAME", "nvt-126")
            ssh_password = config.env_vars.get("SSH_SERVER_PASSWORD", "")

            if not ssh_password:
                logger.error("SSH password not configured in environment variables")
                QMessageBox.critical(
                    login_dialog,
                    "Configuration Error",
                    "SSH credentials not configured.\n\n"
                    "Please ensure .env file contains SSH_SERVER_PASSWORD.",
                )
                progress.close()
                vpn_manager.disconnect()
                return

            ssh_client = SSHClient(
                hostname=ssh_host,
                port=ssh_port,
                username=ssh_username,
                password=ssh_password,
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

            progress.setLabelText("Initializing your account on the server...")
            app.processEvents()

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

                auth_data["email"] = email
                auth_data["username"] = username
                auth_data["gid"] = gid_number
                auth_data["vpn_manager"] = vpn_manager

                progress.close()
                ssh_client.disconnect()

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

        login_dialog.login_success.connect(on_login_attempt)

        if login_dialog.exec_() != QMessageBox.Accepted:
            logger.info("User cancelled login")
            return 0

        if auth_data["username"] is None:
            logger.error("Login failed - no user data")
            return 1

        logger.info(f"User authorized: {auth_data['email']}")

        window = MainWindow(vpn_manager=auth_data.get("vpn_manager"))
        window.current_user = auth_data["username"]
        window.current_email = auth_data["email"]
        window.current_gid = auth_data.get("gid", 2001)
        window.show()

        logger.info("Application started successfully")

        exit_code = app.exec_()

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
