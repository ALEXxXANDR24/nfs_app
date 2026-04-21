import logging
import sys
import platform as platform_module
import os
from datetime import datetime


def get_platform():
    """Определение операционной системы."""
    system = platform_module.system()
    if system == "Windows":
        return "windows"
    elif system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


class Logger:
    """Логирование с выводом в консоль и файл."""

    def __init__(self, name="nfs_vpn_app"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        self.logger.handlers = []

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        log_dir = os.path.expanduser("~/.nfs_vpn_app")
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, "app.log")
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
        except:
            file_handler = None

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        if file_handler:
            file_handler.setFormatter(formatter)

        self.logger.addHandler(console_handler)
        if file_handler:
            self.logger.addHandler(file_handler)

    def info(self, msg):
        """Логировать информацию."""
        self.logger.info(msg)

    def error(self, msg):
        """Логировать ошибку."""
        self.logger.error(msg)

    def debug(self, msg):
        """Логировать отладку."""
        self.logger.debug(msg)

    def warning(self, msg):
        """Логировать предупреждение."""
        self.logger.warning(msg)


logger = Logger(__name__)
