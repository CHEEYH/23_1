# ui/components/buttons.py
from PySide6.QtWidgets import QPushButton, QScrollArea, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from utils.constants import BTN_HEIGHT, BTN_FONT, BTN_WIDTH, SPACING, TITLE_FONT

def create_button(text, color, callback=None):
    """创建标准按钮"""
    btn = QPushButton(text)
    btn.setFixedHeight(BTN_HEIGHT)
    btn.setMinimumWidth(BTN_WIDTH)
    btn.setStyleSheet(f"""
        QPushButton {{
            font-size:{BTN_FONT}px;
            background-color:{color};
            border-radius:10px;
        }}
        QPushButton:pressed {{
            background-color:#444;
        }}
    """)
    if callback:
        btn.clicked.connect(callback)
    return btn

def build_page(title_text, buttons):
    """构建标准页面"""
    root = QWidget()
    layout = QVBoxLayout(root)
    layout.setAlignment(Qt.AlignCenter)
    layout.setSpacing(SPACING)

    title = QLabel(title_text)
    title.setAlignment(Qt.AlignCenter)
    title.setStyleSheet(f"font-size:{TITLE_FONT}px;font-weight:600;")
    layout.addWidget(title)

    for t, c, cb in buttons:
        layout.addWidget(create_button(t, c, cb))

    layout.addStretch()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(root)

    wrapper = QWidget()
    QVBoxLayout(wrapper).addWidget(scroll)
    return wrapper