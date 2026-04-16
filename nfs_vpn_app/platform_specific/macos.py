"""Команды для macOS."""

import subprocess
import os
import platform
import time
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)

# Флаг для скрытия окна консоли (не используется на macOS, но для консистентности)
if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0


class MacOSCommands:
    """Команды для macOS."""

    @staticmethod
    def check_nfs_tools_installed() -> bool:
        """Проверить установку NFS tools."""
        try:
            # macOS включает встроенную поддержку NFS через mount_nfs
            # Проверим наличие команды mount_nfs
            result = subprocess.run(
                ["which", "mount_nfs"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            is_installed = result.returncode == 0
            if is_installed:
                logger.info("mount_nfs is available")
            else:
                logger.warning("mount_nfs not found")
            return is_installed
        except Exception as e:
            logger.warning(f"Failed to check mount_nfs: {str(e)}")
            return False

    @staticmethod
    def ensure_nfs_tools_installed() -> tuple:
        """
        Проверить и установить NFS tools если необходимо.

        Returns:
            (success, message)
        """
        # Проверить установлены ли уже
        if MacOSCommands.check_nfs_tools_installed():
            logger.info("NFS tools are already installed")
            return True, "NFS tools are already installed"

        logger.info("Attempting to install NFS tools via brew...")

        try:
            # Проверим установлен ли brew
            result = subprocess.run(
                ["which", "brew"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                msg = "Homebrew is not installed. Please install Homebrew first from https://brew.sh"
                logger.error(msg)
                return False, msg

            # Устанавливаем nfs-utils через brew
            command = ["brew", "install", "nfs-utils"]
            logger.debug(f"Running command: {' '.join(command)}")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                logger.info("NFS tools installed successfully")
                return True, "NFS tools installed successfully"
            else:
                error_msg = (
                    result.stderr.strip()
                    if result.stderr
                    else result.stdout.strip() if result.stdout else "Unknown error"
                )
                logger.error(f"Installation failed: {error_msg}")
                return False, f"Installation failed: {error_msg}"

        except subprocess.TimeoutExpired:
            msg = "Installation timeout"
            logger.error(msg)
            return False, msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Installation error: {error_msg}")
            return False, f"Installation error: {error_msg}"

    @staticmethod
    def mount_nfs(server: str, share: str, mount_point: str) -> tuple:
        """Смонтировать NFS."""
        # Проверить и подключить VPN если необходимо
        logger.info(f"Checking VPN connection before mounting NFS...")

        vpn_connected = False
        try:
            # Попытаемся пинганть VPN сервер
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", "172.18.130.50"],
                capture_output=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            vpn_connected = result.returncode == 0
            logger.info(
                f"VPN connection check: {'Connected' if vpn_connected else 'Not connected'}"
            )
        except Exception as e:
            logger.warning(f"Could not check VPN connection: {str(e)}")

        # Если VPN не подключен, пытаемся подключиться
        if not vpn_connected:
            logger.info("VPN is not connected, attempting to connect...")
            try:
                # Импортируем VPNManager здесь чтобы избежать циклических импортов
                from nfs_vpn_app.core.vpn_manager import VPNManager

                vpn_manager = VPNManager()
                if vpn_manager.connect():
                    logger.info("VPN connected successfully")
                    vpn_connected = True
                    # Даем время на установку соединения
                    time.sleep(2)
                else:
                    logger.error("Failed to connect to VPN")
                    return (
                        False,
                        "Failed to establish VPN connection. Please connect manually and try again.",
                    )
            except Exception as e:
                error_msg = f"VPN connection error: {str(e)}"
                logger.error(error_msg)
                return False, error_msg

        if not vpn_connected:
            msg = "VPN is not connected and connection failed. Please ensure VPN is set up correctly."
            logger.error(msg)
            return False, msg

        # Убедиться, что директория существует
        if not os.path.exists(mount_point):
            try:
                result = subprocess.run(
                    ["mkdir", "-p", mount_point],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    logger.info(f"Created mount point: {mount_point}")
                else:
                    logger.warning(f"Failed to create mount point: {result.stderr}")
            except Exception as e:
                logger.error(f"Failed to create mount point: {str(e)}")
                return False, str(e)

        command = [
            "mount_nfs",
            "-o",
            "resvport,intr,vers=4,port=2049",
            f"{server}:{share}",
            mount_point,
        ]

        logger.info(f"Mounting NFS: {server}:{share} -> {mount_point}")

        try:
            result = subprocess.run(
                ["sudo"] + command,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                logger.info(f"Successfully mounted NFS on {mount_point}")
                return True, f"Mounted on {mount_point}"
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"Mount failed: {error_msg}")
                return False, error_msg

        except subprocess.TimeoutExpired:
            msg = "Mount command timeout"
            logger.error(msg)
            return False, msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Mount command failed: {error_msg}")
            return False, error_msg

    @staticmethod
    def unmount_nfs(mount_point: str) -> tuple:
        """Размонтировать NFS."""
        command = ["umount", "-f", mount_point]

        logger.info(f"Unmounting NFS from {mount_point}")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                logger.info(f"Successfully unmounted {mount_point}")
                return True, "Unmounted"
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"Unmount failed: {error_msg}")
                return False, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unmount command failed: {error_msg}")
            return False, error_msg

    @staticmethod
    def check_mount(mount_point: str) -> bool:
        """Проверить, смонтирована ли ФС."""
        try:
            result = subprocess.run(
                ["mount"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            is_mounted = mount_point in result.stdout
            logger.debug(f"Mount check for {mount_point}: {is_mounted}")
            return is_mounted
        except Exception as e:
            logger.warning(f"Failed to check mount: {str(e)}")
            return False

    @staticmethod
    def get_openvpn_command(config_path: str) -> list:
        """Получить команду для запуска OpenVPN."""
        return ["openvpn", "--config", config_path]
