import os
import sys
import json
import platform
from pathlib import Path
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


def load_env_file(env_path: str = None) -> dict:
    """
    Загрузить переменные окружения из .env файла.

    Args:
        env_path: Путь к .env файлу. Если None, ищет в корне проекта.

    Returns:
        Словарь переменных окружения
    """
    if env_path is None:
        current_dir = Path(__file__).parent
        while current_dir != current_dir.parent:
            env_file = current_dir / ".env"
            if env_file.exists():
                env_path = str(env_file)
                break
            current_dir = current_dir.parent

    env_vars = {}

    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if (value.startswith('"') and value.endswith('"')) or (
                            value.startswith("'") and value.endswith("'")
                        ):
                            value = value[1:-1]
                        env_vars[key] = value
                        os.environ[key] = value

            logger.debug(
                f"Loaded {len(env_vars)} environment variables from {env_path}"
            )
        except Exception as e:
            logger.warning(f"Failed to load .env file: {str(e)}")

    return env_vars


class ConfigManager:
    """Управление конфигурацией приложения."""

    def __init__(self):
        self.env_vars = load_env_file()

        self.NFS_SERVER = self.env_vars.get("NFS_SERVER_HOST", "172.18.130.50")
        self.NFS_PORT = int(self.env_vars.get("NFS_MOUNT_PORT", 2049))
        self.SSH_PORT = int(self.env_vars.get("SSH_SERVER_PORT", 5282))

        self.NFS_PATHS = {
            "windows": self.env_vars.get("NFS_SHARE_WINDOWS", "srv\\nfs4\\students"),
            "linux": self.env_vars.get("NFS_SHARE_LINUX", "/"),
            "darwin": self.env_vars.get("NFS_SHARE_MACOS", "/"),
        }

        self.config_dir = self._get_config_dir()
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.vpn_config_file = os.path.join(self.config_dir, "vpn_config.ovpn")

        os.makedirs(self.config_dir, exist_ok=True)

        self.config = self._load_config()

    @staticmethod
    def _get_config_dir() -> str:
        """Получить директорию конфигурации зависимо от ОС."""
        if platform.system() == "Windows":
            return os.path.join(os.environ.get("APPDATA", ""), "nfs_vpn_app")
        elif platform.system() == "Darwin":
            return os.path.expanduser("~/.config/nfs_vpn_app")
        else:
            return os.path.expanduser("~/.config/nfs_vpn_app")

    def _load_config(self) -> dict:
        """Загрузить конфигурацию."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                logger.debug("Config loaded successfully")
                return config
            except Exception as e:
                logger.error(f"Failed to load config: {str(e)}")

        os_name = platform.system().lower()
        nfs_path = self.NFS_PATHS.get(os_name, self.NFS_PATHS["linux"])

        default_config = {
            "last_mount_point": None,
            "auto_reconnect": True,
            "reconnect_interval": 10,
            "max_reconnect_attempts": 3,
            "nfs_server": self.NFS_SERVER,
            "nfs_path": nfs_path,
        }

        logger.debug(f"Using default config for {os_name}: NFS path = {nfs_path}")
        return default_config

    def save_config(self) -> bool:
        """Сохранить конфигурацию."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            logger.debug("Config saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {str(e)}")
            return False

    def get_last_mount_point(self) -> str:
        """Получить последнюю выбранную точку монтирования."""
        return self.config.get("last_mount_point")

    def save_last_mount_point(self, mount_point: str):
        """Сохранить последнюю выбранную точку монтирования."""
        self.config["last_mount_point"] = mount_point
        self.save_config()

    def get_vpn_config(self) -> str:
        """Получить встроенный VPN конфиг из приложения."""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            vpn_config_path = os.path.join(base_dir, "resources", "vpn_config.ovpn")

            if os.path.exists(vpn_config_path):
                logger.info(f"VPN config found at: {vpn_config_path}")
                with open(vpn_config_path, "r", encoding="utf-8") as f:
                    config_content = f.read()
                logger.info("VPN config loaded from resources")
                return config_content

            logger.debug(f"Trying alternative paths for VPN config...")
            alternative_paths = [
                os.path.join(base_dir, "resources", "vpn_config.ovpn"),
                os.path.join(os.path.dirname(base_dir), "resources", "vpn_config.ovpn"),
            ]

            for alt_path in alternative_paths:
                alt_path = os.path.abspath(alt_path)
                logger.debug(f"Checking: {alt_path}")
                if os.path.exists(alt_path):
                    logger.info(f"VPN config found at alternative path: {alt_path}")
                    with open(alt_path, "r", encoding="utf-8") as f:
                        config_content = f.read()
                    return config_content

            for path in sys.path:
                vpn_path = os.path.join(path, "resources", "vpn_config.ovpn")
                vpn_path = os.path.abspath(vpn_path)
                logger.debug(f"Checking in sys.path: {vpn_path}")
                if os.path.exists(vpn_path):
                    logger.info(f"VPN config found in sys.path: {vpn_path}")
                    with open(vpn_path, "r", encoding="utf-8") as f:
                        config_content = f.read()
                    return config_content

            logger.error(f"VPN config not found")
            logger.error(f"Base dir: {base_dir}")
            logger.error(f"sys.path: {sys.path}")
            logger.error(f"Current __file__: {__file__}")

            return None

        except Exception as e:
            logger.error(f"Failed to get VPN config: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def get_setting(self, key: str, default=None):
        """Получить значение конфига."""
        return self.config.get(key, default)

    def set_setting(self, key: str, value):
        """Установить значение конфига."""
        self.config[key] = value
        self.save_config()

    def get_nfs_server(self) -> str:
        """Получить адрес NFS сервера."""
        return self.config.get("nfs_server", self.NFS_SERVER)

    def get_nfs_path(self) -> str:
        """Получить путь NFS на сервере."""
        return self.config.get(
            "nfs_path",
            self.NFS_PATHS.get(platform.system().lower(), self.NFS_PATHS["linux"]),
        )
