import re
import os
import platform
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


class Validators:
    @staticmethod
    def validate_mount_point_windows(drive_letter: str) -> bool:
        """Валидировать букву диска (A-Z)."""
        if not drive_letter or len(drive_letter) != 1:
            return False

        drive = drive_letter.upper()
        if drive < "A" or drive > "Z":
            logger.warning(f"Invalid drive letter: {drive}")
            return False

        logger.debug(f"Drive {drive} is valid")
        return True

    @staticmethod
    def validate_mount_point_posix(path: str) -> bool:
        """Валидировать путь для Linux/macOS."""
        if not path or len(path) < 2:
            logger.warning(f"Path too short: {path}")
            return False

        if not path.startswith("/"):
            logger.warning(f"Path {path} is not absolute")
            return False

        if re.match(r"^/[\w\-/.]*$", path):
            logger.debug(f"Path {path} is valid")
            return True

        logger.warning(f"Path {path} contains invalid characters")
        return False

    @staticmethod
    def validate_mount_point(mount_point: str, platform_name: str = None) -> bool:
        """Валидировать точку монтирования для текущей ОС."""
        if platform_name is None:
            platform_name = platform.system().lower()

        if platform_name == "windows":
            return Validators.validate_mount_point_windows(mount_point)
        else:
            return Validators.validate_mount_point_posix(mount_point)

    @staticmethod
    def is_path_available(path: str) -> bool:
        """Проверить, что путь доступен для использования."""
        try:
            if platform.system() == "Windows":
                import ctypes

                drive = f"{path}:\\"
                return bool(ctypes.windll.kernel32.GetDriveTypeW(drive))
            else:
                parent_dir = os.path.dirname(path)
                if not parent_dir:
                    parent_dir = "/"
                return os.access(parent_dir, os.W_OK)
        except Exception as e:
            logger.warning(f"Failed to check path availability: {str(e)}")
            return False

    @staticmethod
    def validate_vpn_config(config_content: str) -> bool:
        """Валидировать VPN конфиг (проверка на наличие ключевых данных)."""
        if not config_content:
            logger.warning("VPN config is empty")
            return False

        if "client" not in config_content.lower():
            logger.warning(
                "Missing key 'client' in VPN config - not a valid OpenVPN config"
            )
            return False

        logger.debug("VPN config is valid (contains 'client' directive)")
        return True
