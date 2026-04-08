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
        self.openvpn_path = self._find_openvpn_path()

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
                # На Windows запускаем OpenVPN напрямую
                if not self.openvpn_path:
                    logger.error("OpenVPN not found in system PATH")
                    self._emit_status("OpenVPN not found in system PATH", "error")
                    return False
                command = [self.openvpn_path, "--config", config_path]
            else:
                command = ["openvpn", "--config", config_path]

            logger.debug(f"Starting OpenVPN with command: {' '.join(command)}")

            self.process = self.process_runner.start_long_running_process(
                command,
                is_sudo=(self.platform != "windows"),
                requires_admin=(self.platform == "windows"),
            )

            if self.process is None:
                logger.error("Failed to start OpenVPN")
                self._emit_status("Failed to start OpenVPN", "error")
                return False

            logger.info("OpenVPN process started")
            self._emit_status("Connecting to VPN...", "info")

            # Ждем подключения (проверяем каждую секунду)
            max_attempts = 60  # Увеличено для Windows (может быть медленнее)
            for i in range(max_attempts):
                if self._check_vpn_connection():
                    self.is_connected = True
                    logger.info("VPN connection established")
                    self._emit_status("VPN connected", "info")

                    # Ждем инициализации адаптера
                    logger.info("Waiting for VPN adapter initialization...")
                    wait_time = 2
                    for i in range(wait_time):
                        time.sleep(1)
                        if not self._check_vpn_connection():
                            logger.warning(
                                "VPN connection lost during initialization wait"
                            )
                            self.is_connected = False
                            return False

                    logger.info("VPN adapter initialization complete")

                    # Запустить мониторинг соединения
                    self._start_monitoring()

                    return True

                time.sleep(1)
                if (i + 1) % 5 == 0:  # Логировать каждые 5 секунд
                    logger.debug(f"Waiting for VPN connection ({i+1}/{max_attempts}s)")

            # Проверим вывод ошибок процесса
            if self.process:
                try:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    if stderr:
                        logger.error(f"OpenVPN stderr: {stderr}")
                except:
                    pass

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
            # Проверяем несколько способов:
            # 1. Основная проверка - пинг к VPN серверу
            # 2. Проверка процесса OpenVPN живой
            # 3. Проверка через netstat/ipconfig на Windows

            if self.process and self.process.poll() is not None:
                logger.debug("OpenVPN process is not running")
                return False

            # Пинг к VPN серверу
            if self.platform == "windows":
                command = ["ping", "-n", "1", "-w", "2000", "172.18.130.50"]
            else:
                command = ["ping", "-c", "1", "-W", "2", "172.18.130.50"]

            result = subprocess.run(command, capture_output=True, timeout=5)

            if result.returncode == 0:
                logger.debug("VPN ping successful")
                return True

            logger.debug(
                f"VPN ping failed (code {result.returncode}), checking alternative methods..."
            )

            # Альтернативная проверка - проверим есть ли маршрут на VPN сеть
            if self.platform == "windows":
                # На Windows используем ipconfig
                result = subprocess.run(
                    ["ipconfig"], capture_output=True, text=True, timeout=5
                )
                # Ищем VPN адапт или TUN адапт
                if (
                    "OpenVPN" in result.stdout
                    or "TUN" in result.stdout
                    or "TAP" in result.stdout
                ):
                    logger.debug("Found VPN adapter in ipconfig")
                    return True
            else:
                # На Linux/macOS используем ip route
                cmd = (
                    "ip route | grep -i tun"
                    if self.platform == "linux"
                    else "netstat -rn | grep tun"
                )
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5, shell=True
                )
                if result.returncode == 0:
                    logger.debug("Found VPN route")
                    return True

            return False

        except Exception as e:
            logger.debug(f"VPN check failed: {str(e)}")
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

    def _find_openvpn_path(self) -> str:
        """Найти путь к openvpn.exe на Windows."""
        if self.platform != "windows":
            return None

        import shutil
        import glob

        # Пытаемся найти в стандартных местах (сначала обычная инсталляция)
        possible_paths = [
            "C:\\Program Files\\OpenVPN\\bin\\openvpn.exe",
            "C:\\Program Files (x86)\\OpenVPN\\bin\\openvpn.exe",
            "C:\\Users\\Public\\Programs\\OpenVPN\\bin\\openvpn.exe",
        ]

        # Сначала проверим стандартные места
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logger.info(f"Found OpenVPN at: {path}")
                    return path
            except Exception as e:
                logger.debug(f"Failed to check path {path}: {str(e)}")

        # Попробуем найти через which (если PATH настроена правильно)
        try:
            result = shutil.which("openvpn")
            if result:
                logger.info(f"Found OpenVPN via PATH: {result}")
                return result
        except Exception as e:
            logger.debug(f"shutil.which failed: {str(e)}")

        # Попытаемся поискать в Program Files используя glob
        try:
            programs_dir = os.environ.get("ProgramFiles", "C:\\Program Files")
            pattern = os.path.join(programs_dir, "*OpenVPN*", "bin", "openvpn.exe")
            matches = glob.glob(pattern, recursive=False)
            if matches:
                logger.info(f"Found OpenVPN via glob: {matches[0]}")
                return matches[0]
        except Exception as e:
            logger.debug(f"Glob search failed: {str(e)}")

        # Попытаемся поискать в Program Files (x86)
        try:
            programs_dir_x86 = os.environ.get(
                "ProgramFiles(x86)", "C:\\Program Files (x86)"
            )
            pattern = os.path.join(programs_dir_x86, "*OpenVPN*", "bin", "openvpn.exe")
            matches = glob.glob(pattern, recursive=False)
            if matches:
                logger.info(f"Found OpenVPN via glob (x86): {matches[0]}")
                return matches[0]
        except Exception as e:
            logger.debug(f"Glob search (x86) failed: {str(e)}")

        # Попробуем запустить openvpn напрямую из PATH
        try:
            result = subprocess.run(
                ["openvpn", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("OpenVPN found via direct command execution")
                return "openvpn"
        except Exception as e:
            logger.debug(f"Direct execution test failed: {str(e)}")

        logger.error("OpenVPN not found in system")
        return None
