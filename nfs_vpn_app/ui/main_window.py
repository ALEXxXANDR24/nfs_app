"""Главное окно приложения с темным стилем."""

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QPlainTextEdit,
    QLabel,
    QMessageBox,
    QProgressBar,
    QGroupBox,
    QFormLayout,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QColor
import platform
from typing import List
from nfs_vpn_app.core.vpn_manager import VPNManager
from nfs_vpn_app.core.nfs_manager import NFSManager
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()

        self.vpn_manager = VPNManager()
        self.nfs_manager = NFSManager()
        self.platform = platform.system().lower()

        self.init_ui()
        self.setup_signals()

        # Таймер для обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)

        logger.info("Main window initialized")

    def init_ui(self):
        """Инициализировать UI."""
        self.setWindowTitle("NFS VPN Connect - Network File System VPN Manager")
        self.setGeometry(100, 100, 1000, 750)

        # Темный стиль
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #1a1a1a;
            }
            QPushButton {
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
                border: none;
                font-size: 13pt;
                min-height: 40px;
            }
            QPushButton:hover {
                opacity: 0.85;
            }
            QPushButton:pressed {
                opacity: 0.75;
            }
            QGroupBox {
                border: 2px solid #404040;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                background-color: #2a2a2a;
                font-weight: 600;
                color: #ffffff;
                font-size: 12pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #4db8ff;
            }
            QComboBox {
                border: 2px solid #404040;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #2a2a2a;
                color: #ffffff;
                font-size: 12pt;
                min-height: 32px;
            }
            QComboBox:focus {
                border: 2px solid #4db8ff;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #ffffff;
                selection-background-color: #4db8ff;
            }
            QPlainTextEdit {
                background-color: #1a1a1a;
                color: #00ff00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11pt;
                border: 2px solid #404040;
                border-radius: 6px;
                padding: 8px;
            }
            QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #505050;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #606060;
            }
            QProgressBar {
                border: 2px solid #404040;
                border-radius: 6px;
                text-align: center;
                background-color: #2a2a2a;
                height: 10px;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #4db8ff, stop:1 #0099ff);
                border-radius: 4px;
            }
            QLabel {
                color: #ffffff;
            }
        """
        )

        # Главный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)
        central_widget.setLayout(main_layout)

        # Заголовок
        header_layout = QHBoxLayout()
        title_label = QLabel("NFS VPN Connection Manager")
        title_font = title_label.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #4db8ff; padding: 10px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Информационное сообщение
        info_label = QLabel("Connect to VPN and mount NFS file system automatically")
        info_font = info_label.font()
        info_font.setPointSize(11)
        info_label.setFont(info_font)
        info_label.setStyleSheet("color: #b0b0b0; padding: 5px 10px;")
        main_layout.addWidget(info_label)

        # Главный контейнер с двух-колончным макетом
        content_layout = QHBoxLayout()

        # Левая колонна (управление)
        left_column = QVBoxLayout()
        left_column.setSpacing(12)

        # Группа выбора точки монтирования
        mount_group = QGroupBox("Mount Configuration")
        mount_layout = QFormLayout()
        mount_layout.setSpacing(8)

        mount_label = QLabel("Mount Point:")
        mount_label.setStyleSheet("font-weight: 600; color: #ffffff; font-size: 12pt;")
        self.mount_point_selector = QComboBox()
        self.mount_point_selector.setMinimumWidth(320)
        self.mount_point_selector.setMinimumHeight(36)
        self._populate_mount_points()

        last_mount_point = self.nfs_manager.config_manager.get_last_mount_point()
        if last_mount_point:
            index = self.mount_point_selector.findText(last_mount_point)
            if index >= 0:
                self.mount_point_selector.setCurrentIndex(index)

        mount_layout.addRow(mount_label, self.mount_point_selector)
        mount_group.setLayout(mount_layout)
        left_column.addWidget(mount_group)

        # Кнопки управления
        button_group = QGroupBox("Connection Control")
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.on_connect_clicked)
        self.connect_button.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #2196F3, stop:1 #1565C0);
                color: white;
                font-weight: bold;
                font-size: 13pt;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #42A5F5, stop:1 #2196F3);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #1565C0, stop:1 #0D47A1);
            }
        """
        )
        self.connect_button.setMinimumHeight(48)
        self.connect_button.setMinimumWidth(180)
        button_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #F44336, stop:1 #C62828);
                color: white;
                font-weight: bold;
                font-size: 13pt;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #EF5350, stop:1 #F44336);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #C62828, stop:1 #B71C1C);
            }
            QPushButton:disabled {
                background-color: #505050;
                color: #808080;
            }
        """
        )
        self.disconnect_button.setMinimumHeight(48)
        self.disconnect_button.setMinimumWidth(180)
        button_layout.addWidget(self.disconnect_button)

        button_group.setLayout(button_layout)
        left_column.addWidget(button_group)

        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(14)
        left_column.addWidget(self.progress_bar)

        # Статус-карточки
        status_group = QGroupBox("Connection Status")
        status_layout = QHBoxLayout()
        status_layout.setSpacing(15)

        # NFS Статус
        nfs_card_layout = QVBoxLayout()
        nfs_label = QLabel("NFS Status")
        nfs_label.setStyleSheet("font-weight: 600; color: #4db8ff; font-size: 12pt;")
        self.nfs_status_label = QLabel("Unmounted")
        self.nfs_status_label.setStyleSheet(
            "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
        )
        nfs_card_layout.addWidget(nfs_label)
        nfs_card_layout.addWidget(self.nfs_status_label)
        status_layout.addLayout(nfs_card_layout)

        # Общий статус
        general_card_layout = QVBoxLayout()
        general_label = QLabel("Overall Status")
        general_label.setStyleSheet(
            "font-weight: 600; color: #4db8ff; font-size: 12pt;"
        )
        self.general_status_label = QLabel("Disconnected")
        self.general_status_label.setStyleSheet(
            "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
        )
        general_card_layout.addWidget(general_label)
        general_card_layout.addWidget(self.general_status_label)
        status_layout.addLayout(general_card_layout)

        status_layout.addStretch()
        status_group.setLayout(status_layout)
        left_column.addWidget(status_group)

        left_column.addStretch()
        content_layout.addLayout(left_column, 2)

        # Разделитель
        separator = QWidget()
        separator.setStyleSheet("background-color: #404040;")
        separator.setMaximumWidth(2)
        content_layout.addWidget(separator)

        # Правая колонна (логи)
        right_column = QVBoxLayout()
        right_column.setSpacing(8)

        log_label = QLabel("Application Log")
        log_font = log_label.font()
        log_font.setPointSize(12)
        log_font.setBold(True)
        log_label.setFont(log_font)
        log_label.setStyleSheet("color: #4db8ff; padding: 5px;")
        right_column.addWidget(log_label)

        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMinimumWidth(450)
        right_column.addWidget(self.log_display)

        content_layout.addLayout(right_column, 3)

        main_layout.addLayout(content_layout, 1)

        # Обновить старый reference на новый статус-лейбл
        self.status_label = self.general_status_label

    def _populate_mount_points(self):
        """Заполнить список доступных точек монтирования."""
        self.mount_point_selector.clear()

        if self.platform == "windows":
            from nfs_vpn_app.platform_specific.windows import WindowsCommands

            drives = WindowsCommands.get_available_drives()
            if drives:
                for drive in drives:
                    self.mount_point_selector.addItem(f"{drive}:", f"{drive}")
            else:
                self.mount_point_selector.addItem("Z", "Z")
                logger.warning("No available drives found, using Z as default")
        else:
            # Для Linux/macOS - предложить стандартные пути
            import os

            default_paths = [
                "/mnt/nfs_share",
                "/mnt/nfs",
                os.path.expanduser("~/nfs_share"),
                os.path.expanduser("~/nfs"),
                "/opt/nfs_mount",
            ]
            for path in default_paths:
                self.mount_point_selector.addItem(path, path)

    def setup_signals(self):
        """Установить сигналы."""
        self.vpn_manager.on_status_changed = self.on_vpn_status_changed
        self.nfs_manager.on_status_changed = self.on_nfs_status_changed

    def on_connect_clicked(self):
        """Обработчик клика кнопки Connect."""
        self.log("=" * 60)
        self.log("Starting connection process...")

        mount_point = self.mount_point_selector.currentData()
        if not mount_point:
            mount_point = self.mount_point_selector.currentText()

        # Отключить кнопки
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)

        # Показать прогресс
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # Indefinite progress

        self.log("Connecting to VPN...")
        self.general_status_label.setText("Connecting...")
        self.general_status_label.setStyleSheet(
            "color: #FFB74D; font-size: 14pt; font-weight: bold;"
        )

        # Подключение к VPN
        if not self.vpn_manager.connect():
            self.log("ERROR: Failed to connect to VPN")
            self.general_status_label.setText("VPN Connection Failed")
            self.general_status_label.setStyleSheet(
                "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
            )

            QMessageBox.critical(
                self,
                "VPN Connection Failed",
                "Could not establish VPN connection.\nPlease check:\n"
                "- Internet connection\n"
                "- OpenVPN is installed\n"
                "- Try manual connection first",
            )

            self.connect_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.log("Connection aborted")
            return

        self.log("VPN connected successfully")

        # Монтирование NFS
        self.log(f"Mounting NFS to {mount_point}...")

        if not self.nfs_manager.mount(mount_point):
            self.log("ERROR: Failed to mount NFS")
            self.general_status_label.setText("NFS Mount Failed")
            self.general_status_label.setStyleSheet(
                "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
            )
            self.nfs_status_label.setText("Failed")
            self.nfs_status_label.setStyleSheet(
                "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
            )

            error_msg = "Could not mount NFS.\nPlease check:\n"
            if self.platform == "windows":
                error_msg += "- NFS Client is installed\n"
            else:
                error_msg += "- nfs-common is installed\n"
            error_msg += "- Mount point is available\n"
            error_msg += "- Check logs for details"

            QMessageBox.critical(self, "NFS Mount Failed", error_msg)

            # Отключиться от VPN если монтирование не удалось
            self.log("Disconnecting VPN due to mount failure...")
            self.vpn_manager.disconnect()

            self.connect_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.log("Connection aborted")
            return

        self.log("NFS mounted successfully")
        self.general_status_label.setText("Connected")
        self.general_status_label.setStyleSheet(
            "color: #4CAF50; font-size: 14pt; font-weight: bold;"
        )
        self.nfs_status_label.setText("Mounted")
        self.nfs_status_label.setStyleSheet(
            "color: #4CAF50; font-size: 14pt; font-weight: bold;"
        )

        # Обновить кнопки
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.progress_bar.setVisible(False)

        # Сохранить выбранную точку монтирования
        self.nfs_manager.config_manager.save_last_mount_point(mount_point)

        # Запустить таймер обновления статуса
        self.status_timer.start(5000)  # Проверять каждые 5 секунд

        self.log("=" * 60)
        self.log(f"Successfully connected!")
        self.log(f"Mount Point: {mount_point}")
        self.log("=" * 60)

    def on_disconnect_clicked(self):
        """Обработчик клика кнопки Disconnect."""
        self.log("=" * 60)
        self.log("Starting disconnection process...")

        self.disconnect_button.setEnabled(False)
        self.status_timer.stop()

        self.log("Disconnecting...")
        self.general_status_label.setText("Disconnecting...")
        self.general_status_label.setStyleSheet(
            "color: #FFB74D; font-size: 14pt; font-weight: bold;"
        )

        # Размонтировать NFS
        self.log("Unmounting NFS...")
        if not self.nfs_manager.unmount():
            self.log("Warning: Could not unmount NFS properly")
        else:
            self.log("NFS unmounted")

        # Отключиться от VPN
        self.log("Disconnecting VPN...")
        if not self.vpn_manager.disconnect():
            self.log("Warning: Could not disconnect VPN properly")
        else:
            self.log("VPN disconnected")

        self.general_status_label.setText("Disconnected")
        self.general_status_label.setStyleSheet(
            "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
        )
        self.nfs_status_label.setText("Unmounted")
        self.nfs_status_label.setStyleSheet(
            "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
        )

        # Обновить кнопки
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

        self.log("=" * 60)
        self.log("Disconnected successfully!")
        self.log("=" * 60)

    def update_status(self):
        """Обновить статус соединения."""
        if not (self.vpn_manager.is_connected and self.nfs_manager.is_mounted):
            if self.vpn_manager.is_connected or self.nfs_manager.is_mounted:
                self.log("Connection inconsistent")
            else:
                self.log("Connection lost")
                self.general_status_label.setText("Disconnected")
                self.general_status_label.setStyleSheet(
                    "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
                )
                self.nfs_status_label.setText("Unmounted")
                self.nfs_status_label.setStyleSheet(
                    "color: #FF6B6B; font-size: 14pt; font-weight: bold;"
                )
                self.connect_button.setEnabled(True)
                self.disconnect_button.setEnabled(False)
                self.status_timer.stop()

    def log(self, message: str, error: bool = False):
        """Логировать сообщение в UI."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")
        colored_message = f"[{timestamp}] {message}"

        self.log_display.appendPlainText(colored_message)
        logger.info(message)

        # Автопрокрутка
        self.log_display.verticalScrollBar().setValue(
            self.log_display.verticalScrollBar().maximum()
        )

    def on_vpn_status_changed(self, message: str, level: str = "info"):
        """Обработчик изменения статуса VPN."""
        prefix = "VPN: "
        if level == "error":
            prefix = "VPN [ERROR]: "
        elif level == "warning":
            prefix = "VPN [WARNING]: "

        self.log(f"{prefix}{message}")

    def on_nfs_status_changed(self, message: str, level: str = "info"):
        """Обработчик изменения статуса NFS."""
        prefix = "NFS: "
        if level == "error":
            prefix = "NFS [ERROR]: "
        elif level == "warning":
            prefix = "NFS [WARNING]: "

        self.log(f"{prefix}{message}")

    def closeEvent(self, event):
        """Обработчик закрытия окна."""
        if self.disconnect_button.isEnabled():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "NFS is still mounted. Do you want to disconnect before exiting?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self.on_disconnect_clicked()
                event.accept()
            else:
                event.accept()
        else:
            event.accept()
