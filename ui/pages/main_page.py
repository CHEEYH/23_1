# ui/pages/main_page.py
import json
import socket
import os
from datetime import datetime
from typing import Dict
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QFrame, QGridLayout, QScrollArea,
    QApplication, QDialog, QTextEdit, QListWidget, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor

from config_manager import config_manager
from ui.components.pipeline_runner import PipelineRunner
from ui.components.mes_client import MESClient
from ui.pages.deep_learning_page import CameraWorker, CAMERA_AVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
#  HIGH-CONTRAST Color tokens
#  Rule: text must be bright/light, backgrounds stay dark, NO near-matches
# ─────────────────────────────────────────────────────────────────────────────
C = {
    "bg0": "#030810",  # deepest black-blue
    "bg1": "#070E18",  # topbar
    "bg2": "#060C14",  # page body
    "bg3": "#08111E",  # panel base
    "bg4": "#050D18",  # panel header / inset
    "bg_hover": "#0C1A2E",  # row hover

    "border0": "#1A3A5C",  # panel border
    "border1": "#162E4A",  # dividers
    "border2": "#1A3A5C",  # field border
    "border_hi": "#00AAFF",  # active / accent cyan

    "text0": "#FFFFFF",
    "text1": "#CCDDEE",
    "text2": "#AACCEE",
    "text3": "#6699BB",

    "cyan": "#00AAFF",  # primary tech accent
    "cyan_hi": "#44CCFF",
    "cyan_bg": "#041828",
    "cyan_bd": "#1A5A80",

    "green": "#00FF88",  # READY / OK
    "green_bg": "#031410",
    "green_bd": "#0A5030",
    "green_text": "#00FF88",

    "amber": "#FFAA00",  # WAITING
    "amber_bg": "#1A1000",
    "amber_bd": "#553300",
    "amber_text": "#FFAA00",

    "red": "#FF3344",  # FAULT
    "red_bg": "#1A0508",
    "red_bd": "#661020",
    "red_text": "#FF3344",

    "dim_bg": "#0A1828",
    "dim_bd": "#1A3A5C",
    "dim_text": "#6699BB",
}


# ─────────────────────────────────────────────────────────────────────────────
#  QR Worker
# ─────────────────────────────────────────────────────────────────────────────

class QRCheckWorker(QThread):
    message_received = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    finished_scan = Signal()

    def __init__(self, host="127.0.0.1", port=1220, parent=None):
        super().__init__(parent)
        self.host = host;
        self.port = port
        self.running = True;
        self.sock = None

    def run(self):
        try:
            self.status_changed.emit(f"Connecting to {self.host}:{self.port}…")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            self.status_changed.emit("Connected — awaiting scan…")
            self.sock.sendall(b"check\n")
            self.sock.settimeout(0.2)
            while self.running:
                try:
                    data = self.sock.recv(1024)
                    if not data: break
                    text = data.decode("utf-8", errors="ignore").strip()
                    if text: self.message_received.emit(text)
                except socket.timeout:
                    continue
                except Exception as e:
                    self.error_occurred.emit(f"Read error: {e}");
                    break
        except Exception as e:
            self.error_occurred.emit(f"Connection failed: {e}")
        finally:
            self.cleanup();
            self.finished_scan.emit()

    def stop_scan(self):
        self.running = False
        try:
            if self.sock: self.sock.sendall(b"ok\n")
        except Exception:
            pass

    def cleanup(self):
        try:
            if self.sock: self.sock.close()
        except Exception:
            pass
        self.sock = None


# ─────────────────────────────────────────────────────────────────────────────
#  QR Dialog
# ─────────────────────────────────────────────────────────────────────────────

class QRScanDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Barcode Verification")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setMinimumWidth(820)
        self.setMinimumHeight(700)
        self.setModal(True)
        self.setStyleSheet("QDialog { background-color: #070E18; border: 2px solid #00AAFF; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(80)
        hdr.setStyleSheet(f"QFrame {{ background-color: {C['bg0']}; border-bottom: 1px solid {C['border0']}; }}")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(22, 0, 22, 0)
        icon = QLabel("▣")
        icon.setStyleSheet(f"color: {C['cyan']}; font-size: 26px; background: transparent;")
        title = QLabel("BARCODE VERIFICATION")
        title.setStyleSheet(
            f"color: #FFFFFF; font-size: 26px; font-weight: 700; "
            f"letter-spacing: 2px; font-family: Consolas; background: transparent;"
        )
        hdr_row.addWidget(icon);
        hdr_row.addSpacing(12);
        hdr_row.addWidget(title);
        hdr_row.addStretch()
        root.addWidget(hdr)

        # Body
        body = QWidget()
        body.setStyleSheet(f"background-color: {C['bg1']};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(26, 20, 26, 24)
        bl.setSpacing(14)

        # Status row — no frame, no dot, just clean text
        self.pulse_dot = QLabel("")  # kept for compatibility, hidden
        self.pulse_dot.hide()
        self.status_label = QLabel("Initialising…")
        self.status_label.setStyleSheet(
            "color: #00AAFF; font-size: 26px; font-weight: 700; font-family: Consolas; background: transparent;")
        bl.addWidget(self.status_label)

        out_lbl = QLabel("SCAN OUTPUT")
        out_lbl.setStyleSheet(
            f"color: #AACCEE; font-size: 26px; font-weight: 700; letter-spacing: 2px; background: transparent;")
        bl.addWidget(out_lbl)

        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setPlaceholderText("Awaiting barcode data…")
        self.result_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: {C['bg0']}; color: {C['green']};
                border: 1px solid {C['border0']}; border-radius: 8px;
                padding: 18px; font-size: 22px;
                line-height: 1.8;
                font-family: Consolas, 'Courier New', monospace;
            }}
            QScrollBar:vertical {{ background: {C['bg0']}; width: 6px; border: none; }}
            QScrollBar::handle:vertical {{ background: {C['border_hi']}; border-radius: 3px; }}
        """)
        bl.addWidget(self.result_box)

        btn_row = QHBoxLayout();
        btn_row.addStretch()
        self.confirm_btn = QPushButton("Confirm")
        self.confirm_btn.setFixedSize(220, 70)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #004D28;
                color: #FFFFFF;
                border: 3px solid #00AA55;
                border-bottom: 6px solid #006633;
                border-radius: 10px;
                font-size: 26px; font-weight: 800;
            }
            QPushButton:hover {
                background-color: #006633;
                border-color: #00FF88;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                border-bottom: 3px solid #006633;
                padding-top: 3px;
            }
            QPushButton:disabled {
                background-color: #0A1A12;
                color: #2A4A36;
                border: 3px solid #1A3A28;
                border-bottom: 6px solid #102A1C;
            }
        """)
        btn_row.addWidget(self.confirm_btn);
        btn_row.addSpacing(10)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(220, 70)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A0A14;
                color: #FFFFFF;
                border: 3px solid #CC2233;
                border-bottom: 6px solid #880018;
                border-radius: 10px;
                font-size: 26px; font-weight: 800;
            }
            QPushButton:hover {
                background-color: #5A0E18;
                border-color: #FF4455;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                border-bottom: 3px solid #880018;
                padding-top: 3px;
            }
        """)
        btn_row.addWidget(self.cancel_btn)
        bl.addLayout(btn_row)
        root.addWidget(body)


# ─────────────────────────────────────────────────────────────────────────────
#  Main Page
# ─────────────────────────────────────────────────────────────────────────────

class MainPage(QWidget):

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("MainPage")
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.main = parent
        self.mes = MESClient()

        self.pending_jobs = []
        self.current_recipe = None
        self.current_job_title = None
        self.current_job_details = None
        self.mes_recipe_override = False
        self.waiting_for_mes = True
        self.last_valid_mes_time = None
        self.mes_outage_start = None
        self.pipeline_running = False
        self.pending_run_after_qr = False
        self.has_active_mes_job = False
        self.qr_worker = None
        self.qr_dialog = None
        self.last_qr_job_id = None
        self.qr_check_passed = False
        self.qr_result_ok = False
        self._spinner_frame = 0
        self._pulse_on = True

        self.time_timer = QTimer()
        self.mes_recipe_timer = QTimer()
        self.spinner_timer = QTimer()

        self._apply_palette()
        self._apply_stylesheet()
        self.init_ui()
        self.init_timers()
        self.start_spinner()
        self._apply_host_theme()

        self.pipeline_precheck_running = False
        self.pending_run_after_precheck = False
        self.last_precheck_image = None
        self._original_prediction_finished_handler_swapped = False

    # ── Theme ──────────────────────────────────────────────────────────────

    def _apply_palette(self):
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(C["bg2"]))
        pal.setColor(QPalette.WindowText, QColor(C["text0"]))
        pal.setColor(QPalette.Base, QColor(C["bg4"]))
        pal.setColor(QPalette.AlternateBase, QColor(C["bg3"]))
        pal.setColor(QPalette.Text, QColor(C["text0"]))
        pal.setColor(QPalette.Button, QColor(C["bg3"]))
        pal.setColor(QPalette.ButtonText, QColor(C["text0"]))
        pal.setColor(QPalette.Highlight, QColor(C["cyan"]))
        pal.setColor(QPalette.HighlightedText, QColor(C["bg0"]))
        self.setPalette(pal)

    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
            QWidget#MainPage, QWidget {{
                background-color: {C['bg2']};
                color: #FFFFFF;
                font-family: 'Segoe UI';
                font-size: 26px;
            }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {C['bg0']}; width: 7px; border: none; }}
            QScrollBar::handle:vertical {{ background: {C['border_hi']}; border-radius: 3px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QToolTip {{
                background: {C['bg1']}; color: #FFFFFF;
                border: 1px solid {C['border_hi']}; padding: 6px 12px; font-size: 25px;
            }}
            QMessageBox, QDialog {{ background-color: {C['bg1']}; }}
            QMessageBox QLabel {{ color: #FFFFFF; font-size: 26px; }}
        """)

    def _apply_host_theme(self):
        style = (f"QMainWindow {{ background-color: {C['bg2']}; }} "
                 f"QWidget {{ background-color: {C['bg2']}; color: #FFFFFF; }}")
        parent = self.parentWidget()
        seen = set()
        while parent and id(parent) not in seen:
            seen.add(id(parent))
            parent.setAttribute(Qt.WA_StyledBackground, True)
            parent.setAutoFillBackground(True)
            existing = parent.styleSheet() or ""
            if C["bg2"] not in existing:
                parent.setStyleSheet(existing + "\n" + style)
            parent = parent.parentWidget()

    # ── Style helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _badge(text, color, bg, border):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {color}; background-color: {bg}; border: 1px solid {border}; "
            f"border-radius: 12px; padding: 5px 16px; "
            f"font-size: 26px; font-weight: 700; letter-spacing: 0.5px;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    @staticmethod
    def _section_label(text):
        """Bright enough to actually read — not nearly-invisible."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #FFFFFF; font-size: 22px; font-weight: 800; letter-spacing: 3px; font-family: Consolas;"
        )
        return lbl

    @staticmethod
    def _card_header_style():
        return (f"QFrame {{ background-color: {C['bg4']}; "
                f"border-bottom: 1px solid {C['border1']}; "
                f"border-radius: 10px 10px 0 0; }}")

    @staticmethod
    def _card_style():
        return ("QFrame { background-color: #08111E; "
                "border: 1px solid #1A3A5C; "
                "border-top: 2px solid #00AAFF44; "
                "border-radius: 2px; } "
                "QFrame > QWidget, QFrame > QLabel { "
                "background: transparent; border: none; }")

    @staticmethod
    def _btn_primary():
        return f"""
            QPushButton {{
                background-color: #042A14;
                color: #00FF88;
                border: 1px solid #00AA55;
                border-bottom: 5px solid #007A3D;
                border-left: 3px solid #00FF88;
                border-radius: 2px;
                font-size: 30px; font-weight: 800;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: #063A1E;
                border-color: #00FF88;
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #021A0A;
                border-bottom: 3px solid #007A3D;
                padding-top: 3px;
            }}
            QPushButton:disabled {{
                background-color: #0A1A12;
                color: #2A4A36;
                border: 3px solid #1A3A28;
                border-bottom: 6px solid #102A1C;
            }}
        """

    @staticmethod
    def _btn_secondary():
        return f"""
            QPushButton {{
                background-color: #050D1E;
                color: #00AAFF;
                border: 1px solid #1A5080;
                border-bottom: 5px solid #0A2A50;
                border-left: 3px solid #00AAFF;
                border-radius: 2px;
                font-size: 26px; font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: #081828;
                border-color: #00AAFF;
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #061825;
                border-bottom: 3px solid #0E4070;
                padding-top: 3px;
            }}
            QPushButton:disabled {{
                background-color: {C['bg0']};
                color: {C['dim_text']};
                border: 3px solid {C['border0']};
                border-bottom: 6px solid {C['border1']};
            }}
        """

    # ── Build UI ───────────────────────────────────────────────────────────

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── TOP BAR ────────────────────────────────────────────────────────
        topbar = QFrame()
        topbar.setFixedHeight(130)
        topbar.setStyleSheet("""
            QFrame {
                background-color: #070E18;
                border-bottom: 2px solid #00AAFF;
            }
        """)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(28, 0, 28, 0)
        tb.setSpacing(20)

        # Icon box
        icon_box = QFrame()
        icon_box.setFixedSize(72, 72)
        icon_box.setStyleSheet("""
            QFrame {
                background-color: #050D1E;
                border: 1px solid #00AAFF66;
                border-radius: 2px;
            }
        """)
        ib = QHBoxLayout(icon_box);
        ib.setContentsMargins(0, 0, 0, 0)
        ico = QLabel("⚙");
        ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet(f"color: {C['cyan']}; font-size: 34px; background: transparent; border: none;")
        ib.addWidget(ico)
        tb.addWidget(icon_box)

        txt = QVBoxLayout();
        txt.setSpacing(6)

        # ── BIG TITLE ── this is what was too small
        title = QLabel("Assembly System Dashboard")
        title.setFont(QFont("Segoe UI", 64, QFont.Bold))
        title.setStyleSheet("color: #FFFFFF; background: transparent;")

        txt.addWidget(title)
        tb.addLayout(txt);
        tb.addStretch()

        self.time_label = QLabel(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.time_label.setFont(QFont("Consolas", 24))
        self.time_label.setStyleSheet("color: #00AAFF; background: transparent; letter-spacing: 2px;")
        tb.addWidget(self.time_label)
        root.addWidget(topbar)

        # ── STATUS BAR ─────────────────────────────────────────────────────
        self.statusbar = QFrame()
        statusbar = self.statusbar
        statusbar.setFixedHeight(80)
        statusbar.setStyleSheet("""
            QFrame {
                background-color: #030810;
                border-bottom: 1px solid #00FF8840;
            }
        """)
        sb = QHBoxLayout(statusbar)
        sb.setContentsMargins(28, 0, 28, 0)
        sb.setSpacing(14)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {C['amber']}; font-size: 24px; background: transparent;")

        self.machine_status = QLabel("WAITING FOR MES…")
        self.machine_status.setFont(QFont("Consolas", 26, QFont.Bold))
        self.machine_status.setStyleSheet(f"color: {C['amber']}; background: transparent; letter-spacing: 0.5px;")

        sb.addWidget(self.status_dot);
        sb.addWidget(self.machine_status);
        sb.addStretch()

        self.mes_status_label = QLabel("")
        self.mes_status_label.hide()  # removed per design
        root.addWidget(statusbar)

        # ── BODY ───────────────────────────────────────────────────────────
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setFrameShape(QScrollArea.NoFrame)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        body_widget = QWidget()
        body_widget.setStyleSheet("background-color: #060C14;")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setSpacing(22)
        body_layout.setContentsMargins(24, 22, 24, 24)
        body_scroll.setWidget(body_widget)
        root.addWidget(body_scroll)

        # ── WAITING CARD ───────────────────────────────────────────────────
        self.waiting_card = QWidget()
        self.waiting_card.setObjectName("waiting_card")
        self.waiting_card.setStyleSheet("""
            QWidget#waiting_card {
                background-color: #08111E;
                border: 1px solid #1A3A5C;
                border-top: 3px solid #00AAFF;
                border-radius: 2px;
            }
        """)
        wc = QVBoxLayout(self.waiting_card)
        wc.setAlignment(Qt.AlignTop)
        wc.setSpacing(0)
        wc.setContentsMargins(0, 0, 0, 0)

        # ── Header strip (same pattern as recipe/pending cards) ────────
        wc_hdr = QWidget()
        wc_hdr.setFixedHeight(80)
        wc_hdr.setStyleSheet("background-color: #050D18; border: none; border-bottom: 1px solid #1A3A5C;")
        wch = QHBoxLayout(wc_hdr)
        wch.setContentsMargins(24, 0, 24, 0)
        wch.setSpacing(12)
        self.sys_dot = QLabel("●")
        self.sys_dot.setStyleSheet("color: #FFAA00; font-size: 22px; background: transparent;")
        wch.addWidget(self.sys_dot)
        wch.addWidget(self._section_label("SYSTEM STATUS"))
        wch.addStretch()
        wc.addWidget(wc_hdr)

        # ── Content area ───────────────────────────────────────────────
        wc_body = QWidget()
        wc_body.setStyleSheet("background: transparent; border: none;")
        wc_body_layout = QVBoxLayout(wc_body)
        wc_body_layout.setAlignment(Qt.AlignCenter)
        wc_body_layout.setSpacing(14)
        wc_body_layout.setContentsMargins(28, 20, 28, 20)

        self.waiting_title = QLabel("Waiting for MES Recipe")
        self.waiting_title.setFont(QFont("Segoe UI", 36, QFont.Bold))
        self.waiting_title.setStyleSheet("color: #FFFFFF; background: transparent;")
        self.waiting_title.setAlignment(Qt.AlignCenter)
        wc_body_layout.addWidget(self.waiting_title)

        self.spinner_label = QLabel("■  □  □  □")
        self.spinner_label.setFont(QFont("Consolas", 26))
        self.spinner_label.setStyleSheet("color: #00AAFF; background: transparent; letter-spacing: 6px;")
        self.spinner_label.setAlignment(Qt.AlignCenter)
        wc_body_layout.addWidget(self.spinner_label)

        hint = QLabel("Polling MES for the active production recipe…")
        hint.setStyleSheet("color: #CCDDEE; font-size: 27px; background: transparent;")
        hint.setAlignment(Qt.AlignCenter)
        wc_body_layout.addWidget(hint)
        wc.addWidget(wc_body)
        body_layout.addWidget(self.waiting_card)

        # ── RECIPE CARD ────────────────────────────────────────────────────
        self.recipe_card = QFrame()
        self.recipe_card.setVisible(False)
        self.recipe_card.setStyleSheet(self._card_style())

        rc = QVBoxLayout(self.recipe_card)
        rc.setContentsMargins(0, 0, 0, 0)
        rc.setSpacing(0)

        rc_hdr = QWidget();
        rc_hdr.setFixedHeight(80)
        rc_hdr.setStyleSheet("background-color: #050D18; border: none; border-bottom: 1px solid #1A3A5C;")
        rch = QHBoxLayout(rc_hdr);
        rch.setContentsMargins(24, 0, 24, 0)
        rch.setSpacing(12)
        self.recipe_dot = QLabel("●")
        self.recipe_dot.setStyleSheet("color: #00FF88; font-size: 22px; background: transparent;")
        rch.addWidget(self.recipe_dot)
        rch.addWidget(self._section_label("ACTIVE RECIPE"))
        rch.addStretch()
        self.recipe_mode_badge = QLabel("")  # removed
        rc.addWidget(rc_hdr)

        rc_body = QWidget();
        rc_body.setStyleSheet("background: transparent;")
        rcb = QVBoxLayout(rc_body);
        rcb.setContentsMargins(22, 16, 22, 20);
        rcb.setSpacing(14)

        # Combo kept hidden — used internally for recipe tracking
        self.recipe_combo = QComboBox()
        self.recipe_combo.hide()
        self.refresh_btn = QPushButton()
        self.refresh_btn.hide()
        self.refresh_btn.clicked.connect(self.refresh_recipes)

        self.pipeline_info_label = QLabel("Waiting for MES recipe…")
        self.pipeline_info_label.setStyleSheet(f"""
            color: #FFFFFF;
            background-color: #030810;
            border: 1px solid #1A3A5C;
            border-left: 4px solid #00AAFF;
            border-radius: 0px;
            padding: 14px 20px;
            font-size: 25px;
        """)
        self.pipeline_info_label.setWordWrap(True)
        rcb.addWidget(self.pipeline_info_label)
        rc.addWidget(rc_body)
        body_layout.addWidget(self.recipe_card)

        # ── PENDING CARD ───────────────────────────────────────────────────
        pending_card = QFrame()
        pending_card.setStyleSheet(self._card_style())
        pc = QVBoxLayout(pending_card);
        pc.setContentsMargins(0, 0, 0, 0);
        pc.setSpacing(0)

        pc_hdr = QWidget();
        pc_hdr.setFixedHeight(80)
        pc_hdr.setStyleSheet("background-color: #050D18; border: none; border-bottom: 1px solid #1A3A5C;")
        pch = QHBoxLayout(pc_hdr);
        pch.setContentsMargins(24, 0, 24, 0)
        pch.setSpacing(12)
        self.result_dot = QLabel("●")
        self.result_dot.setStyleSheet("color: #88BBDD; font-size: 24px; background: transparent;")
        pch.addWidget(self.result_dot)
        pch.addWidget(self._section_label("LATEST RESULT"))
        pch.addStretch()
        self.pending_count = self._badge("0 JOBS", C["dim_text"], C["dim_bg"], C["dim_bd"])
        pch.addWidget(self.pending_count)
        pc.addWidget(pc_hdr)

        self.pending_widget = QWidget()
        self.pending_widget.setStyleSheet("background-color: transparent;")
        self.pending_layout = QVBoxLayout(self.pending_widget)
        self.pending_layout.setSpacing(0)
        self.pending_layout.setContentsMargins(0, 0, 0, 0)
        self.pending_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.pending_widget)
        scroll.setMinimumHeight(110)
        scroll.setMaximumHeight(320)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        pc.addWidget(scroll)
        body_layout.addWidget(pending_card)

        # ── COMMAND ────────────────────────────────────────────────────────
        body_layout.addSpacing(8)
        cmd_lbl = QLabel("▸  COMMAND")
        cmd_lbl.setStyleSheet(
            "color: #00AAFF; font-size: 22px; font-weight: 800; letter-spacing: 3px; font-family: Consolas;")
        body_layout.addWidget(cmd_lbl)
        # (replaced _section_label call above)
        body_layout.addSpacing(8)

        grid = QGridLayout();
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1);
        grid.setColumnStretch(1, 2)

        tech_btn = QPushButton("👨‍🔧  TECHNICIAN LOGIN")
        tech_btn.setFixedHeight(150)
        tech_btn.setFont(QFont("Segoe UI", 26, QFont.DemiBold))
        tech_btn.setToolTip("Open technician panel")
        tech_btn.setStyleSheet(self._btn_secondary())
        tech_btn.clicked.connect(self.open_technician)
        grid.addWidget(tech_btn, 0, 0)

        self.run_button = QPushButton("▶  START PIPELINE")
        self.run_button.setFixedHeight(150)
        self.run_button.setFont(QFont("Segoe UI", 32, QFont.Bold))
        self.run_button.setToolTip("Execute the selected recipe")
        self.run_button.setEnabled(False)
        self.run_button.setStyleSheet(self._btn_primary())
        self.run_button.clicked.connect(self.run_pipeline)
        grid.addWidget(self.run_button, 0, 1)

        body_layout.addLayout(grid)
        body_layout.addStretch()

        self.refresh_recipes()
        self.load_pending_jobs()

    # ── Timers ─────────────────────────────────────────────────────────────

    def init_timers(self):
        self.time_timer.timeout.connect(self.update_time);
        self.time_timer.start(300)
        self.spinner_timer.timeout.connect(self.animate_spinner);
        self.spinner_timer.start(500)
        self.mes_recipe_timer.timeout.connect(self.try_fetch_mes_recipe);
        self.mes_recipe_timer.start(5000)

    _SPIN = ["■  □  □  □", "□  ■  □  □", "□  □  ■  □", "□  □  □  ■", "□  □  ■  □", "□  ■  □  □"]

    def animate_spinner(self):
        if not self.waiting_for_mes: return
        self.spinner_label.setText(self._SPIN[self._spinner_frame])
        self._spinner_frame = (self._spinner_frame + 1) % len(self._SPIN)
        self._pulse_on = not self._pulse_on
        col = C["amber"] if self._pulse_on else C["amber_bg"]
        self.status_dot.setStyleSheet(f"color: {col}; font-size: 24px; background: transparent;")

    def start_spinner(self):
        self._spinner_frame = 0;
        self.waiting_for_mes = True

    def update_time(self):
        self.time_label.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    # ── Pending display ────────────────────────────────────────────────────

    def _set_count_badge(self, n):
        if n > 0:
            self.pending_count.setText(f"{n} JOB{'S' if n != 1 else ''}")
            self.pending_count.setStyleSheet(
                f"color: {C['red']}; background-color: {C['red_bg']}; border: 1px solid {C['red_bd']}; "
                f"border-radius: 14px; padding: 9px 24px; font-size: 24px; font-weight: 700;"
            )
        else:
            self.pending_count.setText("0 JOBS")
            self.pending_count.setStyleSheet(
                f"color: #88BBDD; background-color: #0C1A2C; border: 1px solid #1A3050; "
                f"border-radius: 12px; padding: 5px 16px; font-size: 24px; font-weight: 700;"
            )

    def update_pending_display(self):
        while self.pending_layout.count() > 1:
            child = self.pending_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        if not self.pending_jobs:
            empty = QWidget();
            empty.setStyleSheet("background: transparent; border: none;")
            el = QVBoxLayout(empty);
            el.setContentsMargins(0, 30, 0, 30);
            el.setAlignment(Qt.AlignCenter)
            ico = QLabel("✓")
            ico.setStyleSheet("color: #4A8A4A; font-size: 48px; background: transparent;")
            ico.setAlignment(Qt.AlignCenter)
            msg = QLabel("Queue is clear — no pending jobs")
            msg.setStyleSheet("color: #FFFFFF; font-size: 26px; background: transparent;")
            msg.setAlignment(Qt.AlignCenter)
            el.addWidget(ico);
            el.addWidget(msg)
            self.pending_layout.insertWidget(0, empty)
            self._set_count_badge(0);
            return

        for job in self.pending_jobs:
            self.pending_layout.insertWidget(self.pending_layout.count() - 1, self._job_row(job))
        self._set_count_badge(len(self.pending_jobs))

    def _job_row(self, job):
        w = QFrame();
        w.setFixedHeight(110)
        w.setCursor(Qt.PointingHandCursor)
        w.setStyleSheet(f"""
            QFrame {{
                background-color: transparent; border: none;
                border-bottom: 1px solid {C['border1']}; border-radius: 0;
            }}
            QFrame:hover {{ background-color: {C['bg_hover']}; }}
        """)
        row = QHBoxLayout(w);
        row.setContentsMargins(18, 0, 22, 0);
        row.setSpacing(18)

        stripe = QFrame();
        stripe.setFixedWidth(4);
        stripe.setFixedHeight(40)
        stripe.setStyleSheet("background-color: #00AAFF; border: none;")
        row.addWidget(stripe)

        mes = bool(job.get('mes_job_details', {}))
        badge = self._badge(
            "MES" if mes else "LOCAL",
            C["cyan"] if mes else C["dim_text"],
            C["cyan_bg"] if mes else C["dim_bg"],
            C["cyan_bd"] if mes else C["dim_bd"]
        )
        row.addWidget(badge)

        title = (job.get('mes_job_details') or {}).get('title', job.get('job_id', 'Unknown'))
        display = title[:30] if len(title) > 30 else title
        completed = len(job.get('completed_steps', []))
        total = job.get('total_steps', 0)
        skipped = len(job.get('skipped_steps', []))

        info = QVBoxLayout();
        info.setSpacing(5)
        n = QLabel(display)
        n.setStyleSheet("color: #FFFFFF; font-size: 27px; font-weight: 700; background: transparent;")
        parts = [f"{completed}/{total} steps"]
        if skipped: parts.append(f"{skipped} skipped")
        s = QLabel("  ·  ".join(parts))
        s.setStyleSheet(f"color: #AACCEE; font-size: 22px; background: transparent;")
        info.addWidget(n);
        info.addWidget(s)
        row.addLayout(info);
        row.addStretch()

        pct = int(completed / total * 100) if total > 0 else 0
        pl = QLabel(f"{pct}%");
        pl.setFont(QFont("Consolas", 26, QFont.Bold))
        pl.setStyleSheet("color: #22AAFF; font-weight: 900; background: transparent;")
        row.addWidget(pl)
        return w

    # ── MES ────────────────────────────────────────────────────────────────

    def fetch_mes_recipe_once(self, force=False):
        try:
            job_details = self.mes.get_job_details()
            print(f"DEBUG job_details: {job_details}")
            mes_recipe = ""
            if job_details:
                mes_recipe = (job_details.get('recipe') or job_details.get('recipeName') or "").strip()
            if job_details and mes_recipe:
                available = config_manager.get_available_recipes()
                if mes_recipe in available:
                    self.force_ui_update(mes_recipe, job_details);
                    self.has_active_mes_job = True
                else:
                    print(f"⚠️ Recipe '{mes_recipe}' not in local recipes")
            else:
                print("⚠️ MES returned no valid job/recipe");
                self.has_active_mes_job = False
        except Exception as e:
            print(f"❌ MES error: {e}")
            import traceback;
            traceback.print_exc()

    def try_fetch_mes_recipe(self):
        if not self.pipeline_running: self.fetch_mes_recipe_once()

    def force_ui_update(self, recipe_name, job_details):
        job_title = job_details.get('title') or job_details.get('workOrder') or 'Unknown'
        self.current_recipe = recipe_name;
        self.current_job_details = job_details
        self.current_job_title = job_title;
        self.waiting_for_mes = False
        self.mes_recipe_override = True;
        self.has_active_mes_job = True
        if config_manager.current_recipe != recipe_name:
            config_manager.set_current_recipe(recipe_name)

        self.waiting_card.setVisible(False);
        self.recipe_card.setVisible(True)
        self.refresh_recipes()

        idx = self.recipe_combo.findText(f"📦  {recipe_name}")
        if idx >= 0:
            self.recipe_combo.blockSignals(True);
            self.recipe_combo.setCurrentIndex(idx);
            self.recipe_combo.blockSignals(False)

        short = job_title[:32] if len(job_title) > 32 else job_title
        self.machine_status.setText(f"READY  ·  {recipe_name}  ·  {short}")
        self.machine_status.setStyleSheet(f"color: {C['green']}; background: transparent; letter-spacing: 0.5px;")
        self.status_dot.setStyleSheet(f"color: {C['green']}; font-size: 24px; background: transparent;")
        self.mes_status_label.setText(f"MES  ·  {job_title[:28]}")
        self.mes_status_label.setStyleSheet(
            f"color: {C['green']}; background-color: {C['green_bg']}; border: 1px solid {C['green_bd']}; "
            f"border-radius: 14px; padding: 9px 24px; font-size: 24px; font-weight: 700;"
        )

        job_id = job_details.get('title') or job_details.get('workOrder') or 'Unknown'
        if self.last_qr_job_id != job_id:
            self.last_qr_job_id = job_id;
            self.qr_check_passed = False;
            self.qr_result_ok = False

        if hasattr(self, 'run_button'): self.run_button.setEnabled(True)
        if hasattr(self, 'sys_dot'): self.sys_dot.setStyleSheet(
            "color: #00DD66; font-size: 24px; background: transparent;")
        self.update_pipeline_info();
        self.load_pending_jobs()
        self.machine_status.repaint();
        QApplication.processEvents()

    def enable_mes_recipe_mode(self, recipe_name, job_details=None):
        self.force_ui_update(recipe_name, job_details)
        self.debug_timer = QTimer();
        self.debug_timer.timeout.connect(self.debug_status);
        self.debug_timer.start(2000)

    def debug_status(self):
        print(f"🔍 UI: '{self.machine_status.text()}' | Recipe: {self.current_recipe} | Job: {self.current_job_title}")

    def handle_mes_disconnect(self):
        if self.current_recipe and not self.waiting_for_mes: return
        self.waiting_for_mes = True;
        self.mes_recipe_override = False
        self.current_recipe = None;
        config_manager.current_recipe = None
        self.waiting_card.setVisible(True);
        self.recipe_card.setVisible(False)
        self.current_job_title = None;
        self.current_job_details = None
        self.qr_check_passed = False;
        self.qr_result_ok = False
        self.last_qr_job_id = None;
        self.has_active_mes_job = False
        self.waiting_title.setText("Waiting for MES Recipe")
        if hasattr(self, 'run_button'): self.run_button.setEnabled(False)
        self.machine_status.setText("WAITING FOR MES…")
        self.machine_status.setStyleSheet("color: #FFCC44; background: transparent;")
        self.status_dot.setStyleSheet("color: #FFAA00; font-size: 24px; background: transparent;")
        if hasattr(self, "statusbar"): self.statusbar.setStyleSheet(
            "QFrame { background-color: #030810; border-bottom: 1px solid #FFAA0040; }")
        self.statusbar.setStyleSheet("QFrame { background-color: #0E1800; border-bottom: 2px solid #2A3A00; }")
        self.mes_status_label.setText("MES  ·  Awaiting Recipe")
        self.mes_status_label.setStyleSheet(
            f"color: {C['amber']}; background-color: {C['amber_bg']}; border: 1px solid {C['amber_bd']}; "
            f"border-radius: 14px; padding: 9px 24px; font-size: 24px; font-weight: 700;"
        )
        QApplication.processEvents()

    def refresh_recipes(self):
        if not self.mes_recipe_override: return
        recipes = config_manager.get_available_recipes();
        current_text = self.recipe_combo.currentText()
        self.recipe_combo.blockSignals(True);
        self.recipe_combo.clear()
        self.recipe_combo.addItem("— Select a Recipe —")
        for r in recipes: self.recipe_combo.addItem(f"📦  {r}")
        if current_text in [f"📦  {r}" for r in recipes]:
            self.recipe_combo.setCurrentText(current_text)
        elif config_manager.current_recipe:
            t = f"📦  {config_manager.current_recipe}"
            if t in [self.recipe_combo.itemText(i) for i in range(self.recipe_combo.count())]:
                self.recipe_combo.setCurrentText(t)
        self.recipe_combo.blockSignals(False);
        self.update_pipeline_info()

    def on_recipe_changed(self, recipe_name):
        if not self.mes_recipe_override: return
        if recipe_name and recipe_name != "— Select a Recipe —":
            clean = recipe_name.replace("📦  ", "");
            config_manager.set_current_recipe(clean)
            self.current_recipe = clean;
            self.update_pipeline_info();
            self.load_pending_jobs()
            self.machine_status.setText(f"READY  ·  {clean}")
        else:
            self.current_recipe = None;
            config_manager.current_recipe = None
            self.pipeline_info_label.setText("No recipe selected")
            self.pending_jobs = [];
            self.update_pending_display()

    def update_pipeline_info(self):
        if self.waiting_for_mes: self.pipeline_info_label.setText("Waiting for MES recipe…"); return
        name = self.recipe_combo.currentText()
        if name == "— Select a Recipe —" or not name:
            self.pipeline_info_label.setText("Select a recipe to view details");
            return
        clean = name.replace("📦  ", "");
        summary = PipelineRunner.get_pipeline_summary(clean)
        if "error" in summary:
            self.pipeline_info_label.setText(f"⚠  {summary['error']}")
        else:
            self.pipeline_info_label.setText(

                f"<span style='color:#FFFFFF;font-size:20px;font-weight:700;'>{summary['recipe']}</span>"
                f"<span style='color:#AACCEE;font-size:18px;'>  ·  {summary['total_blocks']} steps"
                f"  ·  {len(summary['execution_order'])} executable</span>"
            )

    def load_pending_jobs(self):
        if not self.current_recipe or self.waiting_for_mes:
            self.pending_jobs = [];
            self.update_pending_display();
            return
        self.pending_jobs = PipelineRunner.get_pending_jobs(self.current_recipe);
        self.update_pending_display()

    # ── QR ─────────────────────────────────────────────────────────────────

    def show_qr_check_popup(self):
        if self.qr_dialog and self.qr_dialog.isVisible(): return
        self.qr_result_ok = False;
        self.qr_dialog = QRScanDialog(self)
        self.qr_dialog.status_label.setText("Initialising scanner…")
        self.qr_dialog.confirm_btn.setEnabled(False)
        self.qr_dialog.confirm_btn.clicked.connect(self.confirm_qr_scan)
        self.qr_dialog.cancel_btn.clicked.connect(self.cancel_qr_scan)
        self.qr_worker = QRCheckWorker(host="127.0.0.1", port=1220, parent=self)
        self.qr_worker.status_changed.connect(self.on_qr_status_changed)
        self.qr_worker.message_received.connect(self.on_qr_message_received)
        self.qr_worker.error_occurred.connect(self.on_qr_error)
        self.qr_worker.finished_scan.connect(self.on_qr_finished)
        self.qr_worker.start();
        self.qr_dialog.exec()

    def on_qr_status_changed(self, text):
        if self.qr_dialog: self.qr_dialog.status_label.setText(text)

    def on_qr_message_received(self, text):
        if not self.qr_dialog: return
        clean = text.strip()
        if not clean: return
        self.qr_result_ok = True
        self.qr_dialog.status_label.setText("✓  Barcode received — ready to confirm")
        self.qr_dialog.status_label.setStyleSheet(
            "color: #00FF88; font-size: 26px; font-weight: 700; font-family: Consolas; background: transparent;")
        self.qr_dialog.confirm_btn.setEnabled(True);
        self.qr_dialog.result_box.append(clean)

    def on_qr_error(self, text):
        if not self.qr_dialog: return
        self.qr_dialog.status_label.setText("✕  Connection error")
        self.qr_dialog.status_label.setStyleSheet(
            "color: #FF3344; font-size: 26px; font-weight: 700; font-family: Consolas; background: transparent;")
        self.qr_dialog.result_box.append(f"[ERROR]  {text}")

    def on_qr_finished(self):
        if self.qr_dialog:
            cur = self.qr_dialog.status_label.text()
            if "received" not in cur and "error" not in cur: self.qr_dialog.status_label.setText("Scan stopped")

    def confirm_qr_scan(self):
        if not self.qr_result_ok:
            QMessageBox.warning(self, "No QR Data", "No QR data received yet.", QMessageBox.Ok)
            return

        self.qr_check_passed = True

        if self.qr_dialog:
            self.qr_dialog.accept()
            self.qr_dialog.deleteLater()
            self.qr_dialog = None

        if hasattr(self, 'run_button'):
            self.run_button.setEnabled(True)

        if self.current_recipe and self.current_job_title:
            self.machine_status.setText(f"READY  ·  {self.current_recipe}  ·  {self.current_job_title}")
        else:
            self.machine_status.setText("READY")

        QApplication.processEvents()

        if self.qr_worker:
            self.qr_worker.stop_scan()
            self.qr_worker.wait(300)
            self.qr_worker.deleteLater()
            self.qr_worker = None

        if self.pending_run_after_qr:
            self.pending_run_after_qr = False
            QTimer.singleShot(0, self.start_pipeline_precheck)

    def cancel_qr_scan(self):
        self.qr_check_passed = False;
        self.qr_result_ok = False;
        self.pending_run_after_qr = False
        if self.qr_dialog: self.qr_dialog.reject(); self.qr_dialog.deleteLater(); self.qr_dialog = None
        if hasattr(self, 'run_button'): self.run_button.setEnabled(True)
        if self.qr_worker:
            self.qr_worker.stop_scan();
            self.qr_worker.wait(500)
            self.qr_worker.deleteLater();
            self.qr_worker = None
        QApplication.processEvents()

    # ── Pipeline ───────────────────────────────────────────────────────────

    def get_inventory(self) -> Dict[str, int]:
        try:
            if hasattr(PipelineRunner, '_api_client') and PipelineRunner._api_client:
                return PipelineRunner._api_client.get_all_inventory()
        except Exception as e:
            print(f"Inventory fetch error: {e}")
        return {k: 0 for k in 'ABCDEFGH'}

    def save_pending(self, recipe: str, job: Dict):
        PipelineRunner.save_pending_job(recipe, job)

    def run_pipeline(self):
        if self.waiting_for_mes:
            QMessageBox.warning(self, "Waiting for MES", "Still waiting for a recipe from MES.")
            return

        if not self.current_recipe:
            QMessageBox.warning(self, "No Recipe", "Please select a recipe first.")
            return

        if self.pipeline_running or self.pipeline_precheck_running:
            return

        if not self.qr_check_passed:
            self.pending_run_after_qr = True
            self.show_qr_check_popup()
            return

        self.start_pipeline_precheck()

    def _find_deep_learning_page(self):
        """
        Try to locate the DeepLearningPage instance from main window.
        Change this if your real attribute name is different.
        """
        candidate_names = [
            "deep_learning_page",
            "deeplearning_page",
            "dl_page",
            "deepLearningPage",
        ]

        for name in candidate_names:
            page = getattr(self.main, name, None)
            if page and hasattr(page, "auto_load_latest_model") and hasattr(page, "predict_current_image"):
                return page

        # fallback: scan main's attributes
        for name in dir(self.main):
            try:
                obj = getattr(self.main, name)
            except Exception:
                continue
            if obj and hasattr(obj, "auto_load_latest_model") and hasattr(obj, "predict_current_image"):
                return obj

        return None

    def run_pipeline_after_precheck(self):
        if self.pipeline_running:
            return

        self.machine_status.setText("RUNNING…")
        self.pipeline_running = True
        try:
            success = PipelineRunner.run_pipeline_operator_mode(
                self.current_recipe,
                self,
                pending_callback=lambda j: self.save_pending(self.current_recipe, j)
            )
        finally:
            self.pipeline_running = False

        self._post_run(success)

    def start_pipeline_precheck(self):
        if self.pipeline_precheck_running:
            return

        try:
            from ui.pages.deep_learning_page import CameraWorker, CAMERA_AVAILABLE
        except Exception as e:
            QMessageBox.warning(self, "AI Check Error", f"Cannot import DeepLearningPage camera tools:\n{str(e)}")
            return

        if not CAMERA_AVAILABLE:
            QMessageBox.warning(self, "Camera Error", "Camera not available.")
            return

        dl_page = self._find_deep_learning_page()
        if dl_page is None:
            QMessageBox.warning(
                self,
                "AI Check Error",
                "DeepLearningPage instance not found.\n"
                "Please check the attribute name in _find_deep_learning_page()."
            )
            return

        try:
            dl_page.update_paths_from_recipe()
        except Exception as e:
            QMessageBox.warning(self, "AI Check Error", f"Failed to update AI paths:\n{str(e)}")
            return

        try:
            if not hasattr(dl_page, "current_model") or dl_page.current_model is None:
                loaded = dl_page.auto_load_latest_model()
                if not loaded:
                    QMessageBox.warning(self, "AI Check Error", "No AI model found for current recipe.")
                    return
        except Exception as e:
            QMessageBox.warning(self, "AI Check Error", f"Failed to load model:\n{str(e)}")
            return

        if not getattr(dl_page, "capture_folder", None):
            QMessageBox.warning(self, "AI Check Error", "Capture folder is not ready.")
            return

        self.pipeline_precheck_running = True
        self.pending_run_after_precheck = True
        self._precheck_dl_page = dl_page

        if self.current_recipe and self.current_job_title:
            self.machine_status.setText(f"AI CHECK  ·  {self.current_recipe}  ·  Capturing image")
        elif self.current_recipe:
            self.machine_status.setText(f"AI CHECK  ·  {self.current_recipe}  ·  Capturing image")
        else:
            self.machine_status.setText("AI CHECK  ·  Capturing image")

        self._precheck_camera_worker = CameraWorker(dl_page.capture_folder)
        self._precheck_camera_worker.finished.connect(self.on_pipeline_precheck_capture_finished)

        thread = threading.Thread(
            target=self._precheck_camera_worker.capture_image,
            daemon=True
        )
        thread.start()

    def on_pipeline_precheck_capture_finished(self, success, message, image_path):
        dl_page = self._precheck_dl_page

        if not success or not image_path or dl_page is None:
            self.pipeline_precheck_running = False
            self.pending_run_after_precheck = False
            if self.current_recipe and self.current_job_title:
                self.machine_status.setText(f"READY  ·  {self.current_recipe}  ·  {self.current_job_title}")
            elif self.current_recipe:
                self.machine_status.setText(f"READY  ·  {self.current_recipe}")
            else:
                self.machine_status.setText("READY")

            QMessageBox.warning(self, "AI Check Failed", f"Capture failed:\n{message}")
            return

        try:
            if image_path not in dl_page.image_files:
                dl_page.image_files.append(image_path)
                dl_page.image_files.sort()

            dl_page.current_index = dl_page.image_files.index(image_path)
            dl_page.load_current_image()
        except Exception as e:
            self.pipeline_precheck_running = False
            self.pending_run_after_precheck = False
            QMessageBox.warning(self, "AI Check Failed", f"Failed to load captured image:\n{str(e)}")
            return

        # Temporarily reroute prediction finished signal to MainPage precheck handler
        try:
            dl_page.prediction_signals.finished.disconnect(dl_page.on_prediction_finished)
        except Exception:
            pass

        try:
            dl_page.prediction_signals.finished.connect(self.on_pipeline_precheck_prediction_finished)
            self._original_prediction_finished_handler_swapped = True
            QTimer.singleShot(300, lambda: dl_page.predict_current_image(None))
        except Exception as e:
            self.pipeline_precheck_running = False
            self.pending_run_after_precheck = False
            QMessageBox.warning(self, "AI Check Failed", f"Failed to hook prediction signal:\n{str(e)}")
            return

        if self.current_recipe and self.current_job_title:
            self.machine_status.setText(f"AI CHECK  ·  {self.current_recipe}  ·  Predicting all objects")
        elif self.current_recipe:
            self.machine_status.setText(f"AI CHECK  ·  {self.current_recipe}  ·  Predicting all objects")
        else:
            self.machine_status.setText("AI CHECK  ·  Predicting all objects")

        # None = predict all classes
        QTimer.singleShot(200, lambda: dl_page.predict_current_image(None, show_progress=False))

    def get_expected_object_names_for_precheck(self, dl_page):
        """
        Expected objects = all valid classes defined in current YOLO model
        Ignore placeholders like '?'
        """
        try:
            if hasattr(dl_page, "current_model") and dl_page.current_model is not None:
                names = getattr(dl_page.current_model, "names", {})

                if isinstance(names, dict):
                    result = []
                    for k in sorted(names.keys()):
                        name = str(names[k]).strip()
                        if not name or name == "?":
                            continue
                        result.append(name)
                    return result

                if isinstance(names, list):
                    result = []
                    for x in names:
                        name = str(x).strip()
                        if not name or name == "?":
                            continue
                        result.append(name)
                    return result

        except Exception as e:
            print(f"[AI CHECK] Failed to read model classes: {e}")

        return []

    def on_pipeline_precheck_prediction_finished(self, success, message, predictions):
        dl_page = self._precheck_dl_page

        if dl_page is not None and getattr(self, "_original_prediction_finished_handler_swapped", False):
            try:
                dl_page.prediction_signals.finished.disconnect(self.on_pipeline_precheck_prediction_finished)
            except Exception:
                pass

            try:
                dl_page.prediction_signals.finished.connect(dl_page.on_prediction_finished)
            except Exception:
                pass

        self._original_prediction_finished_handler_swapped = False
        self.pipeline_precheck_running = False

        if not success:
            self.pending_run_after_precheck = False
            if self.current_recipe and self.current_job_title:
                self.machine_status.setText(f"READY  ·  {self.current_recipe}  ·  {self.current_job_title}")
            elif self.current_recipe:
                self.machine_status.setText(f"READY  ·  {self.current_recipe}")
            else:
                self.machine_status.setText("READY")

            QMessageBox.warning(self, "AI Check Failed", message)
            return

        detected_names = {
            str(p.get("class_name", "")).strip()
            for p in (predictions or [])
            if str(p.get("class_name", "")).strip()
        }

        expected_names = self.get_expected_object_names_for_precheck(dl_page)
        missing = [name for name in expected_names if name not in detected_names]

        print("EXPECTED =", expected_names)
        print("DETECTED =", sorted(detected_names))
        print("MISSING =", missing)

        if not expected_names:
            self.pending_run_after_precheck = False
            if self.current_recipe and self.current_job_title:
                self.machine_status.setText(f"READY  ·  {self.current_recipe}  ·  {self.current_job_title}")
            elif self.current_recipe:
                self.machine_status.setText(f"READY  ·  {self.current_recipe}")
            else:
                self.machine_status.setText("READY")

            QMessageBox.warning(
                self,
                "AI Check Failed",
                "No expected object list found.\nPlease add expected_objects.json in the recipe folder, or make sure model classes are available."
            )
            return

        if missing:
            if self.current_recipe and self.current_job_title:
                self.machine_status.setText(f"AI CHECK WARNING  ·  {self.current_recipe}  ·  {self.current_job_title}")
            elif self.current_recipe:
                self.machine_status.setText(f"AI CHECK WARNING  ·  {self.current_recipe}")
            else:
                self.machine_status.setText("AI CHECK WARNING")

            missing_text = "\n".join(f"• {name}" for name in missing)

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Missing Objects Detected")
            msg.setText(
                "The following expected object(s) were not detected:\n\n"
                f"{missing_text}\n\n"
                "Do you want to continue the pipeline anyway?"
            )

            continue_btn = msg.addButton("Continue", QMessageBox.AcceptRole)
            stop_btn = msg.addButton("Stop", QMessageBox.RejectRole)
            msg.setDefaultButton(stop_btn)

            msg.exec()

            self.pending_run_after_precheck = False

            if msg.clickedButton() == continue_btn:
                if self.current_recipe and self.current_job_title:
                    self.machine_status.setText(
                        f"AI CHECK OVERRIDE  ·  {self.current_recipe}  ·  {self.current_job_title}")
                elif self.current_recipe:
                    self.machine_status.setText(f"AI CHECK OVERRIDE  ·  {self.current_recipe}")
                else:
                    self.machine_status.setText("AI CHECK OVERRIDE")

                QTimer.singleShot(0, self.run_pipeline_after_precheck)
                return
            else:
                if self.current_recipe and self.current_job_title:
                    self.machine_status.setText(f"READY  ·  {self.current_recipe}  ·  {self.current_job_title}")
                elif self.current_recipe:
                    self.machine_status.setText(f"READY  ·  {self.current_recipe}")
                else:
                    self.machine_status.setText("READY")

                QMessageBox.information(
                    self,
                    "Pipeline Stopped",
                    "Pipeline was stopped because expected objects were missing."
                )
                return

        self.pending_run_after_precheck = False

        if self.current_recipe and self.current_job_title:
            self.machine_status.setText(f"AI CHECK PASS  ·  {self.current_recipe}  ·  {self.current_job_title}")
        elif self.current_recipe:
            self.machine_status.setText(f"AI CHECK PASS  ·  {self.current_recipe}")
        else:
            self.machine_status.setText("AI CHECK PASS")

        QTimer.singleShot(0, self.run_pipeline_after_precheck)

    def _post_run(self, success):
        if success:
            self.machine_status.setText(f"READY  ·  {self.current_recipe}")
            self.has_active_mes_job = False;
            self.qr_check_passed = False
            self.qr_result_ok = False;
            self.last_qr_job_id = None
            self.try_fetch_mes_recipe()
        else:
            self.machine_status.setText("PAUSED")
        self.load_pending_jobs()

    def continue_job(self, job):
        if self.waiting_for_mes:
            QMessageBox.warning(self, "Cannot Continue", "Waiting for MES.", QMessageBox.Ok);
            return
        skipped = [s.get('step') for s in job.get('skipped_steps', []) if isinstance(s, dict)]
        if not skipped: self.remove_from_pending(job); return
        self.pipeline_running = True
        self.machine_status.setText(f"RUNNING  ·  Continuing {job.get('job_id', '')[:8]}…")
        self.machine_status.repaint();
        QApplication.processEvents()
        try:
            success = PipelineRunner.continue_skipped_steps(
                self.current_recipe, job, self,
                pending_callback=lambda j: self.save_pending(self.current_recipe, j))
        finally:
            self.pipeline_running = False
        self._post_run(success)

    def remove_from_pending(self, job):
        job_id = job.get('job_id')
        self.pending_jobs = [j for j in self.pending_jobs if j.get('job_id') != job_id]
        PipelineRunner.remove_pending_job(self.current_recipe, job_id);
        self.update_pending_display()

    def start_new_pipeline(self):
        job_info = ""
        if hasattr(self, 'current_job_details') and self.current_job_details:
            job_info = f"\n\nJob: {self.current_job_details.get('title', 'Unknown')}"
        if QMessageBox.question(self, "Start New Pipeline",
                                f"Start new pipeline for <b>{self.current_recipe}</b>?{job_info}",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.No: return
        self.pipeline_running = True;
        self.machine_status.setText("RUNNING…")
        try:
            success = PipelineRunner.run_pipeline_operator_mode(
                self.current_recipe, self, pending_callback=lambda j: self.save_pending(self.current_recipe, j))
        finally:
            self.pipeline_running = False
        self._post_run(success)

    def show_pending_selection_dialog(self):
        if not self.pending_jobs:
            QMessageBox.information(self, "No Pending Jobs", "No pending jobs found.", QMessageBox.Ok)
            self.start_new_pipeline();
            return
        dialog = QDialog(self);
        dialog.setWindowTitle("Select Pending Job")
        dialog.setMinimumWidth(580);
        dialog.setStyleSheet(f"QDialog {{ background-color: {C['bg1']}; }}")
        layout = QVBoxLayout(dialog);
        layout.setContentsMargins(20, 20, 20, 20)
        lbl = QLabel("Select a job to continue:")
        lbl.setStyleSheet(f"font-size: 26px; font-weight: 700; color: #FFFFFF;");
        layout.addWidget(lbl)
        job_list = QListWidget()
        job_list.setStyleSheet(f"""
            QListWidget {{ background-color: {C['bg4']}; color: #FFFFFF; border: 1px solid {C['border0']};
                border-radius: 8px; padding: 4px; font-size: 26px; outline: none; }}
            QListWidget::item {{ padding: 10px; border-bottom: 1px solid {C['border1']}; border-radius: 4px; }}
            QListWidget::item:selected {{ background-color: #1A4A70; color: #FFFFFF; }}
        """)
        for job in self.pending_jobs:
            jid = job.get('job_id', 'Unknown');
            comp = len(job.get('completed_steps', []));
            tot = job.get('total_steps', 0)
            skip = len(job.get('skipped_steps', []));
            mes = bool(job.get('mes_job_details', {}))
            t = f"{'🏭' if mes else '📋'}  {jid}  —  {comp}/{tot} steps" + (f"  ({skip} skipped)" if skip else "")
            job_list.addItem(t);
            job_list.item(job_list.count() - 1).setData(Qt.UserRole, job)
        layout.addWidget(job_list)
        br = QHBoxLayout();
        br.setSpacing(10)
        cb = QPushButton("Continue Selected");
        cb.setStyleSheet(self._btn_primary())
        nb = QPushButton("Start New");
        nb.setStyleSheet(self._btn_secondary())
        xb = QPushButton("Cancel");
        xb.setStyleSheet(self._btn_secondary())
        br.addWidget(cb);
        br.addWidget(nb);
        br.addWidget(xb);
        layout.addLayout(br)
        cb.clicked.connect(lambda: self._continue_selected(job_list, dialog))
        nb.clicked.connect(lambda: [dialog.accept(), self.start_new_pipeline()])
        xb.clicked.connect(dialog.reject);
        dialog.exec()

    def _continue_selected(self, job_list, dialog):
        item = job_list.currentItem()
        if not item: QMessageBox.warning(self, "No Selection", "Please select a job.", QMessageBox.Ok); return
        dialog.accept();
        self.continue_job(item.data(Qt.UserRole))

    def show_continue_job_dialog(self, job):
        jid = job.get('job_id', 'Unknown');
        comp = len(job.get('completed_steps', []));
        tot = job.get('total_steps', 0);
        skip = len(job.get('skipped_steps', []))
        dlg = QMessageBox(self);
        dlg.setWindowTitle("Job Already Exists");
        dlg.setIcon(QMessageBox.Question)
        dlg.setText(
            f"Job <b>{jid}</b>:<br><br>• Completed: {comp}/{tot}<br>• Skipped: {skip}<br><br>What would you like to do?")
        dlg.setStandardButtons(QMessageBox.NoButton)
        c = dlg.addButton("Continue Job", QMessageBox.ActionRole);
        c.setStyleSheet(self._btn_primary())
        n = dlg.addButton("Start Fresh", QMessageBox.ActionRole);
        n.setStyleSheet(self._btn_secondary())
        dlg.addButton("Cancel", QMessageBox.RejectRole);
        dlg.exec()
        if dlg.clickedButton() == c:
            self.continue_job(job)
        elif dlg.clickedButton() == n:
            self.archive_and_start_new(job)

    def archive_and_start_new(self, old_job):
        if QMessageBox.question(self, "Archive Job", "Archive old job and start fresh?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.No: return
        old_job['status'] = 'archived';
        old_job['archived_time'] = datetime.now().isoformat()
        self.save_archived_job(old_job)
        self.pending_jobs = [j for j in self.pending_jobs if j.get('job_id') != old_job.get('job_id')]
        PipelineRunner.save_pending_job(self.current_recipe, None);
        self.start_new_pipeline()

    def save_archived_job(self, job):
        folder = config_manager.get_recipe_folder(self.current_recipe)
        if not folder: return
        archive_file = os.path.join(folder, 'archived_jobs.json');
        archives = []
        if os.path.exists(archive_file):
            try:
                with open(archive_file, 'r', encoding='utf-8') as f:
                    archives = json.load(f)
            except Exception:
                archives = []
        archives.append(job)
        if len(archives) > 100: archives = archives[-100:]
        try:
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump(archives, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Archive error: {e}")

    def show_pending_dialog(self):
        if self.waiting_for_mes: return
        dlg = QMessageBox(self);
        dlg.setWindowTitle("Pending Jobs");
        dlg.setIcon(QMessageBox.Question)
        dlg.setText(f"You have {len(self.pending_jobs)} incomplete job(s).")
        dlg.setStandardButtons(QMessageBox.NoButton)
        c = dlg.addButton("Continue Pending", QMessageBox.ActionRole);
        c.setStyleSheet(self._btn_primary())
        n = dlg.addButton("Start New", QMessageBox.ActionRole);
        n.setStyleSheet(self._btn_secondary())
        dlg.addButton("Cancel", QMessageBox.RejectRole);
        dlg.exec()
        if dlg.clickedButton() == c and self.pending_jobs:
            self.continue_job(self.pending_jobs[0])
        elif dlg.clickedButton() == n:
            self.force_new_job()

    def force_new_job(self):
        if self.waiting_for_mes: return
        if QMessageBox.question(self, "Start New Job", "Keep pending jobs and start a new one?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.machine_status.setText("RUNNING…");
            self.pipeline_running = True
            try:
                success = PipelineRunner.run_pipeline_operator_mode(
                    self.current_recipe, self, pending_callback=lambda j: self.save_pending(self.current_recipe, j))
            finally:
                self.pipeline_running = False
            self._post_run(success)

    def open_technician(self):
        self.stop_background_tasks();
        self.main.go_to(self.main.login_page)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.spinner_timer.isActive():    self.spinner_timer.start(500)
        if not self.mes_recipe_timer.isActive(): self.mes_recipe_timer.start(5000)
        self.try_fetch_mes_recipe()
        if not self.waiting_for_mes: self.refresh_recipes(); self.load_pending_jobs()

    def closeEvent(self, event):
        self.time_timer.stop()
        self.mes_recipe_timer.stop()
        self.spinner_timer.stop()

        if self.qr_worker:
            self.qr_worker.stop_scan()
            self.qr_worker.wait(1000)
            self.qr_worker = None

        if self._precheck_camera_worker:
            try:
                self._precheck_camera_worker.stop()
            except Exception:
                pass
            self._precheck_camera_worker = None

        super().closeEvent(event)

    def stop_background_tasks(self):
        if self.mes_recipe_timer.isActive(): self.mes_recipe_timer.stop()
        if self.spinner_timer.isActive():    self.spinner_timer.stop()
        if self.qr_dialog: self.qr_dialog.reject(); self.qr_dialog.deleteLater(); self.qr_dialog = None
        if self.qr_worker:
            self.qr_worker.stop_scan();
            self.qr_worker.wait(500)
            self.qr_worker.deleteLater();
            self.qr_worker = None