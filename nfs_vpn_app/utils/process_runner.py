"""Запуск системных команд с поддержкой async операций."""

import subprocess
import threading
from typing import Tuple, Callable, Optional
import platform
import time
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


class ProcessRunner:
    """Запуск системных команд с поддержкой async операций."""

    def __init__(self):
        self.processes = {}

    def run_command(
        self,
        command: list,
        is_sudo: bool = False,
        timeout: int = 30,
        shell: bool = False,
    ) -> Tuple[bool, str, str]:
        """
        Запустить команду синхронно.

        Args:
            command: список аргументов команды
            is_sudo: добавить sudo (для Linux/macOS)
            timeout: таймаут в секундах
            shell: использовать shell

        Returns:
            (успех, stdout, stderr)
        """
        try:
            if is_sudo and platform.system() != "Windows":
                command = ["sudo"] + command

            logger.debug(f"Running command: {' '.join(command)}")

            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, shell=shell
            )

            success = result.returncode == 0
            if success:
                logger.debug("Command succeeded")
            else:
                logger.warning(f"Command failed with code {result.returncode}")

            return success, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            logger.error(f"Command timeout: {' '.join(command)}")
            return False, "", "Command timeout"

        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            return False, "", str(e)

    def run_command_async(
        self,
        command: list,
        callback: Callable,
        is_sudo: bool = False,
        process_id: str = None,
    ) -> str:
        """
        Запустить команду асинхронно.

        Args:
            command: список аргументов команды
            callback: функция для обработки результата
            is_sudo: добавить sudo
            process_id: уникальный ID процесса

        Returns:
            ID процесса
        """
        if process_id is None:
            process_id = f"proc_{len(self.processes)}"

        def run():
            success, stdout, stderr = self.run_command(command, is_sudo=is_sudo)
            callback(success, stdout, stderr)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.processes[process_id] = thread

        return process_id

    def start_long_running_process(
        self, command: list, is_sudo: bool = False, requires_admin: bool = False
    ) -> Optional[subprocess.Popen]:
        """
        Запустить долгоживущий процесс (e.g., OpenVPN).

        Args:
            command: список аргументов команды
            is_sudo: добавить sudo (для Linux/macOS)
            requires_admin: требуются ли права администратора (Windows)

        Returns:
            объект процесса или None
        """
        try:
            if platform.system() == "Windows" and requires_admin:
                # На Windows используем ctypes для запуска с админ правами
                return self._start_process_with_admin_rights(command)
            elif is_sudo and platform.system() != "Windows":
                command = ["sudo"] + command

            logger.debug(f"Starting long-running process: {' '.join(command)}")

            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            return process

        except Exception as e:
            logger.error(f"Failed to start process: {str(e)}")
            return None

    def _start_process_with_admin_rights(
        self, command: list
    ) -> Optional[subprocess.Popen]:
        """
        Запустить процесс с правами администратора на Windows.
        Использует Windows API через ctypes.
        """
        import ctypes
        import os

        try:
            # Преобразуем команду в строку
            cmd_string = " ".join(f'"{arg}"' if " " in arg else arg for arg in command)
            logger.debug(f"Starting process with admin rights: {cmd_string}")

            # Используем ShellExecuteEx через ctypes
            # Код операции: 'runas' = запуск с правами администратора
            SEE_MASK_NO_CONSOLE = 0x00008000
            SEE_MASK_NOCLOSEPROCESS = 0x00000040

            class ShellExecuteInfo(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("fMask", ctypes.c_ulong),
                    ("hwnd", ctypes.c_void_p),
                    ("lpVerb", ctypes.c_wchar_p),
                    ("lpFile", ctypes.c_wchar_p),
                    ("lpParameters", ctypes.c_wchar_p),
                    ("lpDirectory", ctypes.c_wchar_p),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", ctypes.c_void_p),
                    ("lpIDList", ctypes.c_void_p),
                    ("lpClass", ctypes.c_wchar_p),
                    ("hkeyClass", ctypes.c_void_p),
                    ("dwHotKey", ctypes.c_ulong),
                    ("hIcon", ctypes.c_void_p),
                    ("hProcess", ctypes.c_void_p),
                ]

            sei = ShellExecuteInfo()
            sei.cbSize = ctypes.sizeof(ShellExecuteInfo)
            sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
            sei.hwnd = None
            sei.lpVerb = "runas"  # Запуск с правами администратора
            sei.lpFile = command[0]  # Полный путь к исполняемому файлу
            sei.lpParameters = " ".join(
                f'"{arg}"' if " " in arg else arg for arg in command[1:]
            )
            sei.lpDirectory = None
            sei.nShow = 0  # SW_HIDE - скрыть окно консоли

            # Вызываем ShellExecuteEx
            ret = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
            if not ret:
                logger.error("ShellExecuteEx failed")
                return None

            # Получаем handle процесса
            if sei.hProcess:
                # Преобразуем handle в объект Popen-подобный
                # Используем os.dup для clone handle
                process_handle = sei.hProcess

                # Создаем Popen-подобный объект
                class ProcessWrapper:
                    def __init__(self, handle):
                        self.pid = ctypes.windll.kernel32.GetProcessId(handle)
                        self.returncode = None
                        self._handle = handle
                        self.stdout = None
                        self.stderr = None

                    def poll(self):
                        code = ctypes.c_long()
                        if ctypes.windll.kernel32.GetExitCodeProcess(
                            self._handle, ctypes.byref(code)
                        ):
                            if code.value != 259:  # STILL_ACTIVE = 259
                                self.returncode = code.value
                                return code.value
                        return None

                    def wait(self):
                        ctypes.windll.kernel32.WaitForSingleObject(
                            self._handle, 0xFFFFFFFF
                        )
                        return self.poll()

                    def terminate(self):
                        """Завершить процесс gracefully."""
                        try:
                            ctypes.windll.kernel32.TerminateProcess(self._handle, 1)
                            logger.debug("Process terminated")
                        except Exception as e:
                            logger.error(f"Failed to terminate process: {str(e)}")

                    def kill(self):
                        """Убить процесс."""
                        self.terminate()

                logger.debug(
                    f"Process started with PID: {ProcessWrapper(process_handle).pid}"
                )
                return ProcessWrapper(process_handle)
            else:
                logger.error("Failed to get process handle")
                return None

        except Exception as e:
            logger.error(f"Failed to start process with admin rights: {str(e)}")
            return None

    def terminate_process(self, process: subprocess.Popen) -> bool:
        """Завершить процесс."""
        try:
            if process and process.poll() is None:
                process.terminate()
                logger.info("Process terminated")
                time.sleep(0.5)
                if process.poll() is None:
                    process.kill()
                    logger.info("Process killed")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to terminate process: {str(e)}")
            return False
