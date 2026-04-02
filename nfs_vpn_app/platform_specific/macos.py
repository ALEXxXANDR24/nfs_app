"""Команды для macOS."""

import subprocess
import os
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


class MacOSCommands:
    """Команды для macOS."""

    @staticmethod
    def mount_nfs(server: str, share: str, mount_point: str) -> tuple:
        """Смонтировать NFS."""
        # Убедиться, что директория существует
        if not os.path.exists(mount_point):
            try:
                result = subprocess.run(
                    ["mkdir", "-p", mount_point],
                    capture_output=True,
                    text=True,
                    timeout=10,
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
                ["sudo"] + command, capture_output=True, text=True, timeout=30
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
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)

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
                ["mount"], capture_output=True, text=True, timeout=5
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
