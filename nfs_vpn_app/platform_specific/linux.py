import subprocess
import os
import platform
import time
from nfs_vpn_app.core.logger import Logger
from nfs_vpn_app.core.config_manager import ConfigManager

logger = Logger(__name__)
config_manager = ConfigManager()

if platform.system() == "Windows":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0


class LinuxCommands:
    """Команды для Linux."""

    REQUIRED_PACKAGES = ["nfs-common", "openvpn"]

    @staticmethod
    def check_nfs_common_installed() -> bool:
        """Проверить установку NFS Common."""
        try:
            result = subprocess.run(
                ["dpkg", "-l", "nfs-common"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
            is_installed = result.returncode == 0
            if is_installed:
                logger.info("nfs-common is installed")
            else:
                logger.warning("nfs-common is not installed")
            return is_installed
        except Exception as e:
            logger.warning(f"Failed to check nfs-common: {str(e)}")
            return False

    @staticmethod
    def ensure_nfs_common_installed() -> tuple:
        """
        Проверить и установить NFS Common если необходимо.

        Returns:
            (success, message)
        """
        if LinuxCommands.check_nfs_common_installed():
            logger.info("nfs-common is already installed")
            return True, "nfs-common is already installed"

        logger.info("Attempting to install nfs-common...")

        try:
            commands = [
                ["sudo", "apt", "update"],
                ["sudo", "apt", "install", "-y", "nfs-common"],
            ]

            for command in commands:
                logger.debug(f"Running command: {' '.join(command)}")
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    creationflags=CREATE_NO_WINDOW,
                )

                if result.returncode != 0:
                    error_msg = (
                        result.stderr.strip()
                        if result.stderr
                        else result.stdout.strip() if result.stdout else "Unknown error"
                    )
                    logger.error(f"Command failed: {' '.join(command)} - {error_msg}")
                    return False, f"Installation failed: {error_msg}"

            logger.info("nfs-common installed successfully")
            return True, "nfs-common installed successfully"

        except subprocess.TimeoutExpired:
            msg = "Installation timeout"
            logger.error(msg)
            return False, msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Installation error: {error_msg}")
            return False, f"Installation error: {error_msg}"

    @staticmethod
    def check_openvpn_installed() -> bool:
        """Проверить установку OpenVPN."""
        try:
            result = subprocess.run(
                ["which", "openvpn"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            is_installed = result.returncode == 0
            if is_installed:
                logger.info("OpenVPN is installed")
            else:
                logger.warning("OpenVPN is not installed")
            return is_installed
        except Exception as e:
            logger.warning(f"Failed to check OpenVPN: {str(e)}")
            return False

    @staticmethod
    def ensure_openvpn_installed() -> tuple:
        """
        Проверить и установить OpenVPN если необходимо.

        Returns:
            (success, message)
        """
        if LinuxCommands.check_openvpn_installed():
            logger.info("OpenVPN is already installed")
            return True, "OpenVPN is already installed"

        logger.info("Attempting to install OpenVPN...")

        try:
            commands = [
                ["sudo", "apt", "update"],
                ["sudo", "apt", "install", "-y", "openvpn"],
            ]

            for command in commands:
                logger.debug(f"Running command: {' '.join(command)}")
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    creationflags=CREATE_NO_WINDOW,
                )

                if result.returncode != 0:
                    error_msg = (
                        result.stderr.strip()
                        if result.stderr
                        else result.stdout.strip() if result.stdout else "Unknown error"
                    )
                    logger.error(f"Command failed: {' '.join(command)} - {error_msg}")
                    return False, f"Installation failed: {error_msg}"

            logger.info("OpenVPN installed successfully")
            return True, "OpenVPN installed successfully"

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
        logger.info(f"Checking VPN connection before mounting NFS...")

        vpn_connected = False
        try:
            server_ip = config_manager.env_vars.get("NFS_SERVER_HOST", "172.18.130.50")

            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", server_ip],
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

        if not vpn_connected:
            logger.info("VPN is not connected, attempting to connect...")
            try:
                from nfs_vpn_app.core.vpn_manager import VPNManager

                vpn_manager = VPNManager()
                if vpn_manager.connect():
                    logger.info("VPN connected successfully")
                    vpn_connected = True
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

        if not os.path.exists(mount_point):
            try:
                result = subprocess.run(
                    ["sudo", "mkdir", "-p", mount_point],
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
            "mount",
            "-t",
            "nfs4",
            "-o",
            "vers=4.2,port=2049",
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
        command = ["umount", mount_point]

        logger.info(f"Unmounting NFS from {mount_point}")

        try:
            result = subprocess.run(
                ["sudo"] + command,
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
                ["mountpoint", mount_point],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            is_mounted = result.returncode == 0
            logger.debug(f"Mount check for {mount_point}: {is_mounted}")
            return is_mounted
        except Exception as e:
            logger.warning(f"Failed to check mount: {str(e)}")
            return False

    @staticmethod
    def get_openvpn_command(config_path: str) -> list:
        """Получить команду для запуска OpenVPN."""
        return ["openvpn", "--config", config_path]
