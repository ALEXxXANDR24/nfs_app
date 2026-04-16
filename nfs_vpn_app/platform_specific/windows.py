"""Команды для Windows."""

import subprocess
import ctypes
import time
import platform
import os
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)

# Флаг для скрытия окна консоли
CREATE_NO_WINDOW = 0x08000000


class WindowsCommands:
    """Команды для Windows."""

    # Требуемые компоненты
    REQUIRED_FEATURES = ["NFS-Client"]

    @staticmethod
    def _run_as_admin(command: list) -> tuple:
        """
        Выполнить команду с правами администратора.

        Args:
            command: Команда в виде списка

        Returns:
            (success, message)
        """
        try:
            import tempfile

            if command[0].lower() == "powershell":
                # Формируем аргументы PowerShell
                ps_args = " ".join(command[2:])  # Пропускаем "powershell" и "-Command"

                # Создаем временный батник для выполнения команды
                batch_content = f"""@echo off
REM Выполнить PowerShell команду с правами администратора (без видимого окна)
powershell -NoProfile -WindowStyle Hidden -Command "{ps_args}"
"""

                # Создаем временный файл батника
                fd, batch_file = tempfile.mkstemp(suffix=".bat", text=True)
                try:
                    os.write(fd, batch_content.encode("utf-8"))
                    os.close(fd)

                    logger.debug(f"Created temporary batch file: {batch_file}")

                    # Запускаем батник через PowerShell Start-Process с Verb RunAs
                    # Это гарантирует появление UAC диалога и ожидание завершения
                    ps_cmd = (
                        f'Start-Process -FilePath "{batch_file}" '
                        "-Verb RunAs -Wait -WindowStyle Hidden"
                    )

                    result = subprocess.run(
                        ["powershell", "-Command", ps_cmd],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        creationflags=CREATE_NO_WINDOW,
                    )

                    logger.info(f"Admin command execution result: {result.returncode}")

                    if result.returncode == 0:
                        logger.info("Admin command executed successfully")
                        return True, "Command executed with admin rights"
                    else:
                        # Если returncode != 0, это может быть просто потому, что пользователь отказал в UAC
                        error_msg = (
                            result.stderr.strip()
                            if result.stderr
                            else "User may have cancelled UAC dialog"
                        )
                        logger.warning(f"Admin command result: {error_msg}")
                        return False, error_msg

                finally:
                    # Удаляем временный файл
                    try:
                        if os.path.exists(batch_file):
                            time.sleep(0.5)  # Даем время на отпуск файла
                            os.remove(batch_file)
                            logger.debug(f"Removed temporary batch file: {batch_file}")
                    except Exception as e:
                        logger.warning(f"Could not remove temporary file: {e}")
            else:
                logger.error(
                    "Only PowerShell commands are supported for admin execution"
                )
                return False, "Only PowerShell commands supported"

        except subprocess.TimeoutExpired:
            error_msg = "Admin command execution timeout"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Failed to run as admin: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def check_nfs_client_installed() -> bool:
        """Проверить установку NFS Client компонента."""
        try:
            # Метод 1: Проверить наличие mount.exe в System32
            import os

            mount_path = os.path.join(
                os.environ.get("SystemRoot", "C:\\Windows"), "system32", "mount.exe"
            )

            if os.path.exists(mount_path):
                logger.info("NFS Client is installed (mount.exe found in System32)")
                return True

            # Метод 2: Попробуем запустить mount.exe с явным путем
            try:
                result = subprocess.run(
                    [mount_path, "-h"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    logger.info("NFS Client is installed (mount.exe works)")
                    return True
            except:
                pass

            # Метод 3: Проверим через PowerShell с точным парсингом
            try:
                result = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "(Get-WindowsFeature NFS-Client).Installed",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=CREATE_NO_WINDOW,
                )
                if "True" in result.stdout:
                    logger.info(
                        "NFS Client is installed (verified via Get-WindowsFeature)"
                    )
                    return True
            except:
                pass

            logger.warning("NFS Client is not installed")
            return False

        except Exception as e:
            logger.warning(f"Failed to check NFS Client: {str(e)}")
            return False

    @staticmethod
    def ensure_nfs_client_installed() -> tuple:
        """
        Проверить и установить NFS Client если необходимо.

        Returns:
            (success, message)
        """
        # Проверить установлен ли уже
        if WindowsCommands.check_nfs_client_installed():
            logger.info("NFS Client is already installed")
            return True, "NFS Client is already installed"

        logger.info("Attempting to install NFS Client...")

        try:
            # Команда включения компонента NFS
            command = [
                "powershell",
                "-Command",
                "Enable-WindowsOptionalFeature -FeatureName ServicesForNFS-ClientOnly, ClientForNFS-Infrastructure -Online -NoRestart",
            ]

            logger.debug(
                f"Running install command with admin rights: {' '.join(command)}"
            )

            # Запускаем с правами администратора
            success, output = WindowsCommands._run_as_admin(command)

            if success:
                logger.info("NFS Client installed successfully")
                # Проверяем еще раз
                if WindowsCommands.check_nfs_client_installed():
                    return (
                        True,
                        "NFS Client installed successfully. May require restart.",
                    )
                else:
                    return (
                        True,
                        "NFS Client installation completed. Please restart your computer.",
                    )
            else:
                error_msg = output.strip() if output else "Unknown error"
                logger.error(f"Installation failed: {error_msg}")

                # Если недостаточно прав, предлагаем руководство
                if "Access Denied" in error_msg or "denied" in error_msg.lower():
                    msg = (
                        "NFS Client installation requires administrator privileges.\n"
                        "Please run this application as administrator."
                    )
                    return False, msg
                else:
                    return False, f"Installation failed: {error_msg}"

        except subprocess.TimeoutExpired:
            msg = "NFS Client installation timeout"
            logger.error(msg)
            return False, msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Installation error: {error_msg}")
            return False, f"Installation error: {error_msg}"

    @staticmethod
    def get_available_drives() -> list:
        """Получить доступные буквы диска."""
        drives = []
        try:
            for letter in range(ord("D"), ord("Z") + 1):  # D-Z
                drive = chr(letter)
                try:
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}:\\")
                    if drive_type == 1:  # DRIVE_NO_ROOT_DIR - свободный диск
                        drives.append(drive)
                        logger.debug(f"Drive {drive} is available")
                except:
                    pass
        except Exception as e:
            logger.error(f"Failed to get available drives: {str(e)}")

        logger.info(f"Available drives: {drives}")
        return drives

    @staticmethod
    def mount_nfs(server: str, share: str, drive_letter: str) -> tuple:
        """
        Смонтировать NFS.

        Returns:
            (success, message)
        """
        # Проверить и подключить VPN если необходимо
        logger.info(f"Checking VPN connection before mounting NFS...")

        vpn_connected = False
        try:
            # Попытаемся пинганть VPN сервер
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", "172.18.130.50"],
                capture_output=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            vpn_connected = result.returncode == 0
            logger.info(
                f"VPN connection check: {'Connected' if vpn_connected else 'Not connected'}"
            )
        except Exception as e:
            logger.warning(f"Could not check VPN connection: {str(e)}")

        # Если VPN не подключен, пытаемся подключиться
        if not vpn_connected:
            logger.info("VPN is not connected, attempting to connect...")
            try:
                # Импортируем VPNManager здесь чтобы избежать циклических импортов
                from nfs_vpn_app.core.vpn_manager import VPNManager

                vpn_manager = VPNManager()
                if vpn_manager.connect():
                    logger.info("VPN connected successfully")
                    vpn_connected = True
                    # Даем время на установку соединения
                    time.sleep(2)
                else:
                    logger.error("Failed to connect to VPN")
                    return (
                        False,
                        "Failed to establish VPN connection. Please connect manually and try again.",
                    )
            except Exception as e:
                error_msg = f"VPN connection error: {str(e)}"
                logger.error(error_msg)
                return False, error_msg

        if not vpn_connected:
            msg = "VPN is not connected and connection failed. Please ensure VPN is set up correctly."
            logger.error(msg)
            return False, msg

        # Проверить доступность сервера перед монтированием
        logger.info(f"Checking server availability: {server}")
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "3000", server],
                capture_output=True,
                timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                msg = f"Server {server} is not reachable. VPN may not be connected properly."
                logger.error(msg)
                return False, msg
            logger.info(f"Server {server} is reachable")
        except Exception as e:
            logger.warning(f"Could not verify server availability: {str(e)}")

        # Проверить синтаксис пути
        nfs_path = f"\\\\{server}\\{share}"
        logger.debug(f"NFS path syntax: {nfs_path}")

        # Монтируем через mount.exe
        command = [
            "mount.exe",
            "-o",
            "anon,vers=4,port=2049,timeout=60,retry=3,soft",
            nfs_path,
            f"{drive_letter}:",
        ]

        logger.info(f"Mounting NFS: {nfs_path} -> {drive_letter}:")
        logger.debug(f"Mount command: {' '.join(command)}")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                logger.info(f"Successfully mounted NFS on {drive_letter}:")
                return True, f"Mounted on {drive_letter}:"
            else:
                error_msg = (
                    result.stderr.strip()
                    if result.stderr
                    else result.stdout.strip() if result.stdout else "Unknown error"
                )
                logger.error(f"Mount failed: {error_msg}")
                logger.debug(f"stdout: {result.stdout}")
                logger.debug(f"stderr: {result.stderr}")
                return False, error_msg

        except subprocess.TimeoutExpired:
            msg = "Mount command timeout"
            logger.error(msg)
            return False, msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Mount command failed: {error_msg}")
            return False, error_msg

    @staticmethod
    def unmount_nfs(drive_letter: str) -> tuple:
        """Размонтировать NFS."""
        command = ["net", "use", f"{drive_letter}:", "/delete", "/yes"]

        logger.info(f"Unmounting NFS from {drive_letter}:")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                logger.info(f"Successfully unmounted {drive_letter}:")
                return True, "Unmounted"
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"Unmount failed: {error_msg}")
                return False, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unmount command failed: {error_msg}")
            return False, error_msg

    @staticmethod
    def check_mount(drive_letter: str) -> bool:
        """Проверить, смонтирован ли диск."""
        try:
            import os

            result = os.path.exists(f"{drive_letter}:\\")
            logger.debug(f"Mount check for {drive_letter}: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to check mount: {str(e)}")
            return False

    @staticmethod
    def get_openvpn_command(config_path: str) -> list:
        """Получить команду для запуска OpenVPN."""
        return ["openvpn", "--config", config_path]
