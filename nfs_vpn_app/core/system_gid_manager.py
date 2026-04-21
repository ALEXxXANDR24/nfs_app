import platform
import subprocess
from typing import Tuple
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


class SystemGIDManager:
    """Менеджер для управления GID на локальной системе."""

    def __init__(self):
        self.platform = platform.system()
        logger.info(f"Initializing SystemGIDManager for {self.platform}")

    def set_anonymous_gid(self, gid_number: int) -> Tuple[bool, str]:
        """
        Установить Anonymous GID для NFS на локальной системе.

        Args:
            gid_number: числовое значение GID

        Returns:
            (успех, сообщение)
        """
        if self.platform == "Windows":
            current_gid = self._get_current_windows_gid()
            if current_gid == gid_number:
                msg = f"Windows AnonymousGid is already set to {gid_number}, no changes needed"
                logger.info(msg)
                return True, msg
            return self._set_windows_gid(gid_number)
        elif self.platform == "Linux":
            return self._set_linux_gid(gid_number)
        elif self.platform == "Darwin":
            return self._set_macos_gid(gid_number)
        else:
            msg = f"Unsupported platform: {self.platform}"
            logger.error(msg)
            return False, msg

    def _get_current_windows_gid(self) -> int:
        """
        Получить текущее значение AnonymousGid из реестра Windows.

        Returns:
            Текущее значение GID или -1 если не найдено/ошибка
        """
        try:
            import winreg

            logger.debug("Reading current Windows AnonymousGid from registry...")

            registry = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
            key = winreg.OpenKey(
                registry, r"SOFTWARE\Microsoft\ClientForNFS\CurrentVersion\Default"
            )

            value, _ = winreg.QueryValueEx(key, "AnonymousGid")
            winreg.CloseKey(key)

            logger.debug(f"Current Windows AnonymousGid: {value}")
            return int(value)

        except FileNotFoundError:
            logger.debug("AnonymousGid not found in registry")
            return -1
        except PermissionError:
            logger.warning(
                "Permission denied reading registry (might need admin rights)"
            )
            return -1
        except Exception as e:
            logger.debug(f"Error reading Windows GID: {str(e)}")
            return -1

    def _set_windows_gid(self, gid_number: int) -> Tuple[bool, str]:
        """Установить GID на Windows через реестр от администратора."""
        try:
            logger.info(f"Setting Windows AnonymousGid to {gid_number}")

            from nfs_vpn_app.utils.process_runner import ProcessRunner

            process_runner = ProcessRunner()

            ps_command = (
                f"Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\ClientForNFS\\CurrentVersion\\Default' "
                f"-Name 'AnonymousGid' -Value {gid_number} -Type DWord"
            )

            command = ["powershell", "-Command", ps_command]

            process = process_runner.start_long_running_process(
                command, requires_admin=True
            )

            if process is None:
                msg = "Failed to start PowerShell with admin rights"
                logger.error(msg)
                return False, msg

            process.wait()

            if process.returncode == 0:
                logger.info(f"Windows registry updated successfully")

                logger.info("Requesting system reboot to apply NFS GID changes...")

                try:
                    from PyQt5.QtWidgets import QMessageBox, QApplication

                    app = QApplication.instance()

                    if app:
                        msg = QMessageBox()
                        msg.setIcon(QMessageBox.Information)
                        msg.setWindowTitle("System Reboot Required")
                        msg.setText(
                            "NFS Client GID has been configured successfully.\n\n"
                            "Please restart your computer to apply the changes.\n\n"
                            "After reboot, you'll be able to use the NFS mount."
                        )
                        msg.setStandardButtons(QMessageBox.Ok)
                        msg.setStyleSheet(
                            "QMessageBox { background-color: #2a2a2a; } "
                            "QMessageBox QLabel { color: #ffffff; } "
                            "QPushButton { color: #000000; background-color: #4db8ff; border: none; padding: 5px; }"
                        )
                        msg.exec_()
                except Exception as e:
                    logger.warning(f"Could not show dialog: {str(e)}")

                msg = f"Windows AnonymousGid set to {gid_number}. Computer reboot required."
                logger.info(msg)
                return True, msg
            else:
                msg = (
                    f"Failed to set Windows registry (exit code: {process.returncode})"
                )
                logger.error(msg)
                return False, msg

        except Exception as e:
            msg = f"Error setting Windows GID: {str(e)}"
            logger.error(msg)
            return False, msg

    def _set_linux_gid(self, gid_number: int) -> Tuple[bool, str]:
        """Установить GID на Linux."""
        try:
            import os
            import getpass

            current_user = getpass.getuser()
            logger.info(f"Setting Linux GID {gid_number} for user {current_user}")

            current_gid = os.getgid()
            if current_gid == gid_number:
                msg = f"User '{current_user}' already has GID {gid_number}"
                logger.info(msg)
                return True, msg

            check_group = subprocess.run(
                ["getent", "group", str(gid_number)], capture_output=True, timeout=5
            )

            if check_group.returncode != 0:
                logger.info(f"Creating group with GID {gid_number}")
                create_group = subprocess.run(
                    [
                        "sudo",
                        "groupadd",
                        "-g",
                        str(gid_number),
                        f"{current_user}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if create_group.returncode != 0:
                    msg = f"Failed to create group: {create_group.stderr}"
                    logger.error(msg)
                    return False, msg
                logger.info(f"Group created successfully")
            else:
                logger.debug(f"Group with GID {gid_number} already exists")

            logger.info(f"Setting GID {gid_number} as primary group for {current_user}")

            home_dir = os.path.expanduser("~")

            set_gid = subprocess.run(
                [
                    "sudo",
                    "usermod",
                    "-g",
                    str(gid_number),
                    "-d",
                    home_dir,
                    current_user,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if set_gid.returncode != 0:
                msg = f"Failed to set GID: {set_gid.stderr}"
                logger.error(msg)
                return False, msg

            logger.info(f"Linux GID {gid_number} set successfully for {current_user}")
            msg = f"GID {gid_number} has been set for user '{current_user}'. You may need to log out and log in again for changes to take effect."
            return True, msg

        except Exception as e:
            msg = f"Error setting Linux GID: {str(e)}"
            logger.error(msg)
            return False, msg

    def _set_macos_gid(self, gid_number: int) -> Tuple[bool, str]:
        """Установить GID на macOS."""
        try:
            import os
            import getpass

            current_user = getpass.getuser()
            logger.info(f"Setting macOS GID {gid_number} for user {current_user}")

            current_gid = os.getgid()
            if current_gid == gid_number:
                msg = f"User '{current_user}' already has GID {gid_number}"
                logger.info(msg)
                return True, msg

            check_group = subprocess.run(
                ["dscl", ".", "search", "/Groups", "PrimaryGroupID", str(gid_number)],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if check_group.returncode != 0:
                logger.info(f"Creating group with GID {gid_number}")

                create_group_cmds = [
                    ["sudo", "dscl", ".", "-create", f"/Groups/{current_user}"],
                    [
                        "sudo",
                        "dscl",
                        ".",
                        "-create",
                        f"/Groups/{current_user}",
                        "PrimaryGroupID",
                        str(gid_number),
                    ],
                    [
                        "sudo",
                        "dscl",
                        ".",
                        "-create",
                        f"/Groups/{current_user}",
                        "RealName",
                        f"NFS Group {gid_number}",
                    ],
                ]

                for cmd in create_group_cmds:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30
                    )
                    if result.returncode != 0:
                        logger.debug(
                            f"Command {' '.join(cmd)} returned {result.returncode}"
                        )

                logger.info(f"Group creation attempted")
            else:
                logger.debug(f"Group with GID {gid_number} already exists")

            logger.info(f"Setting GID {gid_number} for {current_user}")

            get_current_gid = subprocess.run(
                ["dscl", ".", "-read", f"/Users/{current_user}", "PrimaryGroupID"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if get_current_gid.returncode == 0:
                output_lines = get_current_gid.stdout.strip().split("\n")
                if len(output_lines) > 0:
                    old_gid = (
                        output_lines[0].split()[-1]
                        if output_lines[0].split()
                        else str(current_gid)
                    )
                    logger.debug(f"Current GID for {current_user}: {old_gid}")

                    set_gid = subprocess.run(
                        [
                            "sudo",
                            "dscl",
                            ".",
                            "-change",
                            f"/Users/{current_user}",
                            "PrimaryGroupID",
                            old_gid,
                            str(gid_number),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                else:
                    set_gid = subprocess.run(
                        [
                            "sudo",
                            "dscl",
                            ".",
                            "-create",
                            f"/Users/{current_user}",
                            "PrimaryGroupID",
                            str(gid_number),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
            else:
                logger.debug(
                    f"PrimaryGroupID not found for {current_user}, creating new"
                )
                set_gid = subprocess.run(
                    [
                        "sudo",
                        "dscl",
                        ".",
                        "-create",
                        f"/Users/{current_user}",
                        "PrimaryGroupID",
                        str(gid_number),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

            if set_gid.returncode != 0:
                msg = f"Failed to set GID: {set_gid.stderr}"
                logger.error(msg)
                return False, msg

            logger.info(f"macOS GID {gid_number} set successfully for {current_user}")
            msg = f"GID {gid_number} has been set for user '{current_user}'. You may need to log out and log in again for changes to take effect."
            return True, msg

        except Exception as e:
            msg = f"Error setting macOS GID: {str(e)}"
            logger.error(msg)
            return False, msg


class ServerGIDManager:
    STARTING_GID = 2001
    BASE_PATH = "/srv/nfs4/students"

    def __init__(self, ssh_client):
        """
        Инициализировать менеджер.

        Args:
            ssh_client: объект SSHClient для подключения к серверу
        """
        self.ssh = ssh_client
        self.used_gids = set()
        self._load_used_gids()

    def _load_used_gids(self):
        """Загрузить список уже используемых GID с сервера."""
        try:
            success, out, err = self.ssh.execute_command(
                "getent group | awk -F: '{print $3}'"
            )
            if success:
                self.used_gids = set(int(gid) for gid in out.strip().split("\n") if gid)
                logger.debug(f"Loaded {len(self.used_gids)} GIDs from server")
        except Exception as e:
            logger.warning(f"Failed to load used GIDs: {str(e)}")

    def get_next_available_gid(self) -> int:
        """Получить следующий доступный GID."""
        gid = self.STARTING_GID
        while gid in self.used_gids:
            gid += 1
        logger.debug(f"Next available GID: {gid}")
        return gid

    def setup_user_gid(self, username: str) -> Tuple[bool, int, str]:
        """
        Подготовить GID и директорию для пользователя.

        Args:
            username: имя пользователя (часть email до @)

        Returns:
            (успех, числовое значение GID, сообщение)
        """
        logger.info(f"Setting up GID for user: {username}")

        exists, gid_number = self.ssh.check_gid_exists(username)

        if exists:
            logger.info(f"GID for '{username}' already exists: {gid_number}")
            gid_to_use = gid_number
        else:
            gid_to_use = self.get_next_available_gid()
            success, msg = self.ssh.create_gid(username, gid_to_use)
            if not success:
                return False, 0, msg
            self.used_gids.add(gid_to_use)

        user_path = f"{self.BASE_PATH}/{username}"
        success, msg = self.ssh.create_directory(user_path, username)

        if not success:
            return False, gid_to_use, msg

        final_msg = f"User '{username}' GID setup complete (GID: {gid_to_use}, Path: {user_path})"
        logger.info(final_msg)
        return True, gid_to_use, final_msg
