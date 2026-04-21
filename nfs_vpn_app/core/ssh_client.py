import paramiko
import socket
import threading
from typing import Tuple, Optional
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


class SSHClient:
    def __init__(self, hostname: str, port: int, username: str, password: str):
        """
        Инициализировать SSH клиент.

        Args:
            hostname: адрес сервера
            port: порт SSH
            username: имя пользователя
            password: пароль
        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.ssh = None
        self.connected = False

    def connect(self) -> Tuple[bool, str]:
        """
        Подключиться к серверу.

        Returns:
            (успех, сообщение)
        """
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            logger.info(
                f"Connecting to SSH: {self.username}@{self.hostname}:{self.port}"
            )

            self.ssh.connect(
                self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10,
                auth_timeout=10,
            )

            self.connected = True
            logger.info("SSH connection established")
            return True, "Connected to server"

        except socket.timeout:
            msg = "Connection timeout - server not responding"
            logger.error(msg)
            return False, msg
        except paramiko.AuthenticationException:
            msg = "Authentication failed - invalid username or password"
            logger.error(msg)
            return False, msg
        except paramiko.SSHException as e:
            msg = f"SSH error: {str(e)}"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Connection failed: {str(e)}"
            logger.error(msg)
            return False, msg

    def disconnect(self):
        """Отключиться от сервера."""
        if self.ssh:
            try:
                self.ssh.close()
                self.connected = False
                logger.info("SSH connection closed")
            except Exception as e:
                logger.error(f"Error closing SSH connection: {str(e)}")

    def execute_command(
        self, command: str, use_sudo_password: bool = False
    ) -> Tuple[bool, str, str]:
        """
        Выполнить команду на сервере.

        Args:
            command: команда для выполнения
            use_sudo_password: передать ли пароль sudo через stdin

        Returns:
            (успех, stdout, stderr)
        """
        if not self.connected or not self.ssh:
            return False, "", "Not connected to server"

        try:
            logger.debug(f"Executing command: {command}")

            if use_sudo_password and command.strip().startswith("sudo "):
                command = command.replace("sudo ", "sudo -S ", 1)

            stdin, stdout, stderr = self.ssh.exec_command(command)

            if use_sudo_password:
                stdin.write(self.password + "\n")
                stdin.flush()

            out = stdout.read().decode("utf-8")
            err = stderr.read().decode("utf-8")
            exit_code = stdout.channel.recv_exit_status()

            success = exit_code == 0
            if success:
                logger.debug(f"Command succeeded: {out}")
            else:
                logger.warning(f"Command failed (exit code {exit_code}): {err}")

            return success, out, err

        except Exception as e:
            msg = f"Command execution failed: {str(e)}"
            logger.error(msg)
            return False, "", msg

    def check_gid_exists(self, gid_name: str) -> Tuple[bool, Optional[int]]:
        """
        Проверить существует ли GID (группа).

        Returns:
            (существует ли, числовое значение GID или None)
        """
        success, out, err = self.execute_command(f"getent group {gid_name}")

        if not success or not out:
            return False, None

        parts = out.strip().split(":")
        if len(parts) >= 3:
            try:
                gid_number = int(parts[2])
                logger.info(f"GID '{gid_name}' exists with number: {gid_number}")
                return True, gid_number
            except ValueError:
                pass

        return False, None

    def create_gid(self, gid_name: str, gid_number: int) -> Tuple[bool, str]:
        """
        Создать GID (группу) на сервере.

        Args:
            gid_name: имя группы
            gid_number: числовое значение GID

        Returns:
            (успех, сообщение)
        """
        exists, _ = self.check_gid_exists(gid_name)
        if exists:
            msg = f"GID '{gid_name}' already exists"
            logger.info(msg)
            return True, msg

        success, out, err = self.execute_command(
            f"sudo groupadd -g {gid_number} {gid_name}", use_sudo_password=True
        )

        if success:
            msg = f"GID '{gid_name}' created with number {gid_number}"
            logger.info(msg)
            return True, msg
        else:
            msg = f"Failed to create GID: {err}"
            logger.error(msg)
            return False, msg

    def check_directory_exists(self, path: str) -> bool:
        """Проверить существует ли директория."""
        success, _, _ = self.execute_command(f"test -d {path}")
        return success

    def create_directory(self, path: str, gid_name: str) -> Tuple[bool, str]:
        """
        Создать директорию и установить права для GID.

        Args:
            path: полный путь к директории
            gid_name: имя группы для установки прав

        Returns:
            (успех, сообщение)
        """
        if self.check_directory_exists(path):
            logger.info(f"Directory '{path}' already exists")
            return True, f"Directory '{path}' already exists"

        success, out, err = self.execute_command(
            f"sudo mkdir -p {path}", use_sudo_password=True
        )
        if not success:
            msg = f"Failed to create directory: {err}"
            logger.error(msg)
            return False, msg

        success, out, err = self.execute_command(
            f"sudo chown :{gid_name} {path}", use_sudo_password=True
        )
        if not success:
            msg = f"Failed to set group owner: {err}"
            logger.error(msg)
            return False, msg

        success, out, err = self.execute_command(
            f"sudo chmod 774 {path}", use_sudo_password=True
        )
        if not success:
            msg = f"Failed to set permissions: {err}"
            logger.error(msg)
            return False, msg

        msg = f"Directory '{path}' created and configured"
        logger.info(msg)
        return True, msg
