from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QSpinBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
import re
from nfs_vpn_app.core.logger import Logger

logger = Logger(__name__)


class LoginDialog(QDialog):
    """Окно авторизации для доступа в приложение."""

    login_success = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NFS VPN Connect - Authorization")
        self.setGeometry(100, 100, 400, 250)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #ffffff;
                font-size: 12pt;
            }
            QLineEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 2px solid #4db8ff;
                padding: 8px;
                font-size: 11pt;
            }
            QLineEdit:focus {
                border: 2px solid #00ff00;
            }
            QPushButton {
                background-color: #4db8ff;
                color: #000000;
                font-weight: bold;
                border: none;
                padding: 10px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #00ff00;
            }
        """
        )

        self._setup_ui()

    def _setup_ui(self):
        """Подготовить UI."""
        layout = QVBoxLayout()

        title = QLabel("HSE Authorization")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        email_label = QLabel("Email:")
        layout.addWidget(email_label)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("example@edu.hse.ru")
        layout.addWidget(self.email_input)

        password_label = QLabel("Password:")
        layout.addWidget(password_label)
        self.password_label = QLineEdit()
        self.password_label.setPlaceholderText("password")
        self.password_label.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_label)

        button_layout = QHBoxLayout()

        login_btn = QPushButton("Login")
        login_btn.clicked.connect(self._on_login_clicked)
        button_layout.addWidget(login_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("QPushButton:hover { background-color: #aa2222; }")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.email_input.setFocus()

        self.email_input.returnPressed.connect(self._on_login_clicked)

    def _on_login_clicked(self):
        """Обработчик нажатия кнопки Login."""
        email = self.email_input.text().strip()

        if not email:
            self._show_error("Please enter your email address")
            return

        if not self._validate_email(email):
            self._show_error("Invalid email format.\nPlease use: name@edu.hse.ru")
            return

        username = email.split("@")[0]

        logger.info(f"Login attempt with email: {email}, username: {username}")

        self.login_success.emit(email, username)

    def _validate_email(self, email: str) -> bool:
        """Проверить email на валидность."""
        pattern = r"^[a-zA-Z0-9._-]+@edu\.hse\.ru$"
        return re.match(pattern, email) is not None

    def _show_error(self, message: str):
        """Показать диалог ошибки."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Authorization Error")
        msg.setText(message)
        msg.setStyleSheet(
            "QMessageBox { background-color: #aaaaaa; } "
            "QMessageBox QLabel { color: #000000; } "
            "QPushButton { color: #000000; background-color: #4db8ff; border: none; padding: 5px; }"
        )
        msg.exec_()
