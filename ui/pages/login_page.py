# ui/pages/login_page.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QMessageBox
)
from PySide6.QtCore import Qt
from ..components.buttons import create_button, SPACING
from utils.constants import TECH_PASSWORD


class TechnicianLoginPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("👨‍🔧 Technician Login")
        title.setStyleSheet("font-size:48px;font-weight:bold;color:#4b5563;")
        layout.addWidget(title)

        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setFixedHeight(70)
        self.input.setStyleSheet("font-size:32px;padding:10px;border:2px solid #ccc;border-radius:8px;")
        self.input.setPlaceholderText("Enter password")
        layout.addWidget(self.input)

        layout.addWidget(create_button("🔓 Login", "#FF9933", self.check))
        layout.addWidget(create_button("← Back", "#999999", self.main.go_back))

        self.setLayout(layout)

    def check(self):
        if self.input.text() == TECH_PASSWORD:
            self.input.clear()
            self.main.go_to(self.main.tech_page)
        else:
            QMessageBox.warning(self, "❌ Error", "Wrong password")
            self.input.clear()