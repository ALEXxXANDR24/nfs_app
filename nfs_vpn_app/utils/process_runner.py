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
        self, command: list, is_sudo: bool = False
    ) -> Optional[subprocess.Popen]:
        """
        Запустить долгоживущий процесс (e.g., OpenVPN).

        Returns:
            объект процесса или None
        """
        try:
            if is_sudo and platform.system() != "Windows":
                command = ["sudo"] + command

            logger.debug(f"Starting long-running process: {' '.join(command)}")

            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            return process

        except Exception as e:
            logger.error(f"Failed to start process: {str(e)}")
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
