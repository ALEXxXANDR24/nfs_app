"""Управление VPN подключением."""

import platform
import subprocess
import time
import threading
import tempfile
import os
from typing import Callable, Optional
from nfs_vpn_app.core.logger import Logger
from nfs_vpn_app.core.config_manager import ConfigManager
from nfs_vpn_app.utils.process_runner import ProcessRunner
from nfs_vpn_app.utils.validators import Validators

logger = Logger(__name__)


class VPNManager:
    """Управление VPN подключением."""

    def __init__(self):
        self.process = None
        self.is_connected = False
        self.config_manager = ConfigManager()
        self.process_runner = ProcessRunner()
        self.platform = platform.system().lower()
        self.monitor_thread = None
        self.monitoring = False
        self.on_status_changed: Optional[Callable] = None
        self.temp_config_path = None

    def connect(self) -> bool:
        """Подключиться к VPN."""
        try:
            logger.info("Starting VPN connection...")

            # Получить VPN конфиг
            vpn_config = self.config_manager.get_vpn_config()
            if not vpn_config:
                logger.error("Failed to get VPN config")
                self._emit_status("VPN config not found", "error")
                return False

            # Валидировать конфиг
            if not Validators.validate_vpn_config(vpn_config):
                logger.error("VPN config validation failed")
                self._emit_status("VPN config validation failed", "error")
                return False

            # Сохранить конфиг во временный файл
            try:
                temp_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".ovpn", delete=False, encoding="utf-8"
                )
                temp_file.write(vpn_config)
                temp_file.close()
                config_path = temp_file.name
                self.temp_config_path = config_path
                logger.debug(f"VPN config saved to {config_path}")
            except Exception as e:
                logger.error(f"Failed to save VPN config: {str(e)}")
                self._emit_status(f"Failed to save VPN config: {str(e)}", "error")
                return False

            # Запустить OpenVPN
            if self.platform == "windows":
                command = ["openvpn", "--config", config_path]
            else:
                command = ["openvpn", "--config", config_path]

            self.process = self.process_runner.start_long_running_process(
                command, is_sudo=(self.platform != "windows")
            )

            if self.process is None:
                logger.error("Failed to start OpenVPN")
                self._emit_status("Failed to start OpenVPN", "error")
                return False

            logger.info("OpenVPN process started")
            self._emit_status("Connecting to VPN...", "info")

            # Ждем подключения (проверяем каждую секунду)
            max_attempts = 30
            for i in range(max_attempts):
                if self._check_vpn_connection():
                    self.is_connected = True
                    logger.info("VPN connection established")
                    self._emit_status("VPN connected", "info")

                    # Запустить мониторинг соединения
                    self._start_monitoring()

                    return True

                time.sleep(1)
                if (i + 1) % 5 == 0:  # Логировать каждые 5 секунд
                    logger.debug(f"Waiting for VPN connection ({i+1}/{max_attempts}s)")

            logger.error("VPN connection timeout")
            self._emit_status("VPN connection timeout", "error")
            self.disconnect()  # Очистить процесс
            return False

        except Exception as e:
            logger.error(f"VPN connection failed: {str(e)}")
            self._emit_status(f"VPN connection failed: {str(e)}", "error")
            return False

    def disconnect(self) -> bool:
        """Отключиться от VPN."""
        try:
            logger.info("Disconnecting from VPN...")

            # Остановить мониторинг
            self._stop_monitoring()

            # Завершить процесс
            if self.process:
                self.process_runner.terminate_process(self.process)
                self.process = None

            # Удалить временный файл конфига
            if self.temp_config_path and os.path.exists(self.temp_config_path):
                try:
                    os.remove(self.temp_config_path)
                    logger.debug(f"Removed temp config: {self.temp_config_path}")
                except:
                    pass

            self.is_connected = False
            logger.info("VPN disconnected")
            self._emit_status("VPN disconnected", "info")

            return True

        except Exception as e:
            logger.error(f"VPN disconnection failed: {str(e)}")
            self._emit_status(f"VPN disconnection failed: {str(e)}", "error")
            return False

    def _check_vpn_connection(self) -> bool:
        """Проверить, подключен ли VPN (пинг к серверу)."""
        try:
            if self.platform == "windows":
                command = ["ping", "-n", "1", "172.18.130.50"]
            else:
                command = ["ping", "-c", "1", "172.18.130.50"]

            result = subprocess.run(command, capture_output=True, timeout=5)

            return result.returncode == 0

        except Exception as e:
            logger.debug(f"Ping failed: {str(e)}")
            return False

    def _start_monitoring(self):
        """Запустить мониторинг VPN соединения."""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_connection, daemon=True
        )
        self.monitor_thread.start()
        logger.info("VPN monitoring started")

    def _stop_monitoring(self):
        """Остановить мониторинг."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("VPN monitoring stopped")

    def _monitor_connection(self):
        """Мониторить VPN соединение в фоне."""
        reconnect_attempts = 0
        max_reconnect_attempts = self.config_manager.get_setting(
            "max_reconnect_attempts", 3
        )
        reconnect_interval = self.config_manager.get_setting("reconnect_interval", 10)

        while self.monitoring:
            time.sleep(reconnect_interval)

            if not self._check_vpn_connection():
                logger.warning("VPN connection lost")
                self._emit_status("VPN connection lost", "warning")

                # Пытаться переподключиться
                if reconnect_attempts < max_reconnect_attempts:
                    reconnect_attempts += 1
                    logger.info(
                        f"Attempting reconnect ({reconnect_attempts}/{max_reconnect_attempts})"
                    )
                    self._emit_status(
                        f"Reconnecting... ({reconnect_attempts}/{max_reconnect_attempts})",
                        "warning",
                    )

                else:
                    logger.error("Max reconnection attempts exceeded")
                    self.is_connected = False
                    self._emit_status(
                        "Connection lost - max reconnection attempts exceeded", "error"
                    )
                    self._stop_monitoring()

    def _emit_status(self, message: str, level: str = "info"):
        """Отправить сигнал об изменении статуса."""
        if self.on_status_changed:
            self.on_status_changed(message, level)
