"""Управление NFS монтированием."""

import platform
import subprocess
import os
import time
import threading
from typing import Callable, Optional
from nfs_vpn_app.core.logger import Logger
from nfs_vpn_app.core.config_manager import ConfigManager
from nfs_vpn_app.utils.validators import Validators

logger = Logger(__name__)


class NFSManager:
    """Управление NFS монтированием."""

    def __init__(self):
        self.mount_point = None
        self.is_mounted = False
        self.platform = platform.system().lower()
        self.config_manager = ConfigManager()

        # NFS сервер и путь
        self.nfs_server = self.config_manager.get_nfs_server()
        self.nfs_path = self.config_manager.get_nfs_path()

        # Сигнал для UI
        self.on_status_changed: Optional[Callable] = None

        # Мониторинг
        self.monitor_thread = None
        self.monitoring = False
        self.check_interval = 10  # секунд

    def mount(self, mount_point: str) -> bool:
        """
        Смонтировать NFS ФС.

        Args:
            mount_point: точка монтирования (буква диска для Windows, путь для Linux/macOS)

        Returns:
            True если успешно, иначе False
        """
        try:
            # Валидировать точку монтирования
            if not Validators.validate_mount_point(mount_point, self.platform):
                logger.error(f"Invalid mount point: {mount_point}")
                self._emit_status(f"Invalid mount point: {mount_point}", "error")
                return False

            # Проверить доступность точки монтирования
            if not Validators.is_path_available(mount_point):
                logger.error(f"Mount point not available: {mount_point}")
                self._emit_status(f"Mount point not available: {mount_point}", "error")
                return False

            self.mount_point = mount_point
            logger.info(f"Attempting to mount NFS to {mount_point}")
            self._emit_status(f"Mounting NFS to {mount_point}...", "info")

            # Выполнить монтирование в зависимости от ОС
            if self.platform == "windows":
                success, message = self._mount_windows()
            elif self.platform == "darwin":
                success, message = self._mount_macos()
            else:  # Linux
                success, message = self._mount_linux()

            if success:
                self.is_mounted = True
                logger.info(f"NFS mounted successfully")
                self._emit_status(f"NFS mounted successfully: {message}", "info")

                # Запустить мониторинг
                self._start_monitoring()

                return True
            else:
                logger.error(f"Failed to mount NFS: {message}")
                self._emit_status(f"Failed to mount NFS: {message}", "error")
                return False

        except Exception as e:
            logger.error(f"Mount operation failed with exception: {str(e)}")
            self._emit_status(f"Mount operation failed: {str(e)}", "error")
            return False

    def unmount(self) -> bool:
        """
        Размонтировать NFS ФС.

        Returns:
            True если успешно, иначе False
        """
        try:
            if not self.is_mounted or not self.mount_point:
                logger.warning("NFS is not mounted")
                return True

            logger.info(f"Attempting to unmount NFS from {self.mount_point}")
            self._emit_status(f"Unmounting NFS from {self.mount_point}...", "info")

            # Остановить мониторинг
            self._stop_monitoring()

            # Выполнить размонтирование в зависимости от ОС
            if self.platform == "windows":
                success, message = self._unmount_windows()
            elif self.platform == "darwin":
                success, message = self._unmount_macos()
            else:  # Linux
                success, message = self._unmount_linux()

            if success:
                self.is_mounted = False
                self.mount_point = None
                logger.info("NFS unmounted successfully")
                self._emit_status("NFS unmounted successfully", "info")
                return True
            else:
                logger.warning(f"Unmount with issues: {message}")
                self._emit_status(
                    f"Unmount completed with warnings: {message}", "warning"
                )
                # Все равно считаем размонтированным
                self.is_mounted = False
                self.mount_point = None
                return True

        except Exception as e:
            logger.error(f"Unmount operation failed: {str(e)}")
            self._emit_status(f"Unmount operation failed: {str(e)}", "error")
            return False

    def _mount_windows(self) -> tuple:
        """Монтирование для Windows."""
        from nfs_vpn_app.platform_specific.windows import WindowsCommands

        try:
            # Проверить и установить NFS Client если необходимо
            if not WindowsCommands.check_nfs_client_installed():
                logger.info("NFS Client not installed, attempting to install...")
                self._emit_status("Installing NFS Client component...", "info")

                success, message = WindowsCommands.ensure_nfs_client_installed()
                if not success:
                    logger.error(f"Failed to install NFS Client: {message}")
                    return False, message

                logger.info(f"NFS Client installation result: {message}")
                self._emit_status(f"NFS Client: {message}", "info")

                # Если требуется перезагрузка
                if "restart" in message.lower() or "reboot" in message.lower():
                    return False, f"{message} Please restart and try again."

            # Выполнить монтирование
            success, message = WindowsCommands.mount_nfs(
                self.nfs_server, self.nfs_path, self.mount_point
            )

            # Проверить монтирование
            if success:
                time.sleep(1)  # Дать время на завершение операции
                if WindowsCommands.check_mount(self.mount_point):
                    return True, f"Mounted on {self.mount_point}:"
                else:
                    return False, "Mount command succeeded but drive is not accessible"

            return False, message

        except Exception as e:
            logger.error(f"Windows mount failed: {str(e)}")
            return False, str(e)

    def _mount_linux(self) -> tuple:
        """Монтирование для Linux."""
        from nfs_vpn_app.platform_specific.linux import LinuxCommands

        try:
            # Проверить и установить NFS Common если необходимо
            if not LinuxCommands.check_nfs_common_installed():
                logger.info("nfs-common not installed, attempting to install...")
                self._emit_status("Installing nfs-common package...", "info")

                success, message = LinuxCommands.ensure_nfs_common_installed()
                if not success:
                    logger.error(f"Failed to install nfs-common: {message}")
                    return False, message

                logger.info(f"nfs-common installation result: {message}")
                self._emit_status(f"nfs-common: {message}", "info")

            # Выполнить монтирование
            success, message = LinuxCommands.mount_nfs(
                self.nfs_server, self.nfs_path, self.mount_point
            )

            # Проверить монтирование
            if success:
                time.sleep(1)
                if LinuxCommands.check_mount(self.mount_point):
                    return True, f"Mounted on {self.mount_point}"
                else:
                    return False, "Mount command succeeded but path is not accessible"

            return False, message

        except Exception as e:
            logger.error(f"Linux mount failed: {str(e)}")
            return False, str(e)

    def _mount_macos(self) -> tuple:
        """Монтирование для macOS."""
        from nfs_vpn_app.platform_specific.macos import MacOSCommands

        try:
            # Проверить и установить NFS tools если необходимо
            if not MacOSCommands.check_nfs_tools_installed():
                logger.info("NFS tools not installed, attempting to install...")
                self._emit_status("Installing NFS tools via Homebrew...", "info")

                success, message = MacOSCommands.ensure_nfs_tools_installed()
                if not success:
                    logger.error(f"Failed to install NFS tools: {message}")
                    return False, message

                logger.info(f"NFS tools installation result: {message}")
                self._emit_status(f"NFS tools: {message}", "info")

            # Выполнить монтирование
            success, message = MacOSCommands.mount_nfs(
                self.nfs_server, self.nfs_path, self.mount_point
            )

            # Проверить монтирование
            if success:
                time.sleep(1)
                if MacOSCommands.check_mount(self.mount_point):
                    return True, f"Mounted on {self.mount_point}"
                else:
                    return False, "Mount command succeeded but path is not accessible"

            return False, message

        except Exception as e:
            logger.error(f"macOS mount failed: {str(e)}")
            return False, str(e)

    def _unmount_windows(self) -> tuple:
        """Размонтирование для Windows."""
        from nfs_vpn_app.platform_specific.windows import WindowsCommands

        try:
            success, message = WindowsCommands.unmount_nfs(self.mount_point)

            if success:
                time.sleep(1)
                # Проверить что действительно размонтирован
                if not WindowsCommands.check_mount(self.mount_point):
                    return True, "Unmounted successfully"
                else:
                    return False, "Unmount command failed - drive still accessible"

            return False, message

        except Exception as e:
            logger.error(f"Windows unmount failed: {str(e)}")
            return False, str(e)

    def _unmount_linux(self) -> tuple:
        """Размонтирование для Linux."""
        from nfs_vpn_app.platform_specific.linux import LinuxCommands

        try:
            success, message = LinuxCommands.unmount_nfs(self.mount_point)

            if success:
                time.sleep(1)
                # Проверить что действительно размонтирован
                if not LinuxCommands.check_mount(self.mount_point):
                    return True, "Unmounted successfully"
                else:
                    return False, "Unmount command failed - path still mounted"

            return False, message

        except Exception as e:
            logger.error(f"Linux unmount failed: {str(e)}")
            return False, str(e)

    def _unmount_macos(self) -> tuple:
        """Размонтирование для macOS."""
        from nfs_vpn_app.platform_specific.macos import MacOSCommands

        try:
            success, message = MacOSCommands.unmount_nfs(self.mount_point)

            if success:
                time.sleep(1)
                # Проверить что действительно размонтирован
                if not MacOSCommands.check_mount(self.mount_point):
                    return True, "Unmounted successfully"
                else:
                    return False, "Unmount command failed - path still mounted"

            return False, message

        except Exception as e:
            logger.error(f"macOS unmount failed: {str(e)}")
            return False, str(e)

    def _start_monitoring(self):
        """Запустить мониторинг NFS соединения."""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_mount, daemon=True)
        self.monitor_thread.start()
        logger.info("NFS monitoring started")

    def _stop_monitoring(self):
        """Остановить мониторинг."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("NFS monitoring stopped")

    def _monitor_mount(self):
        """Мониторить NFS монтирование в фоне."""
        while self.monitoring:
            time.sleep(self.check_interval)

            if not self.is_mounted:
                break

            # Проверить доступность
            if not self._check_nfs_accessible():
                logger.warning("NFS mount point is not accessible")
                self._emit_status("NFS mount point is not accessible", "warning")

    def _check_nfs_accessible(self) -> bool:
        """Проверить доступность NFS монтирования."""
        try:
            if not self.mount_point:
                return False

            if self.platform == "windows":
                return os.path.exists(f"{self.mount_point}:\\")
            else:
                return os.path.exists(self.mount_point)

        except Exception as e:
            logger.warning(f"Failed to check NFS accessibility: {str(e)}")
            return False

    def _emit_status(self, message: str, level: str = "info"):
        """Отправить сигнал об изменении статуса."""
        if self.on_status_changed:
            self.on_status_changed(message, level)
