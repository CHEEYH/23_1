# ui/components/dialogs.py
from datetime import datetime

import cv2
import numpy as np
import glob
import os
import json
import shutil
import threading
import time
import socket
import re

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QFormLayout, QSpinBox,
    QGroupBox, QGridLayout, QScrollArea, QWidget, QDialogButtonBox, QMessageBox, QFrame, QTextEdit,
    QFileDialog, QProgressDialog, QSplitter, QDoubleSpinBox, QLineEdit
)
from PySide6.QtCore import Signal, Qt, QTimer, QThread
from config_manager import config_manager
from ui.components.prediction_manager import PredictionManager
from ui.components.heartbeat_manager import HeartbeatManager

CAMERA_AVAILABLE = False
camera_module = None

try:
    from camera.camera import AutoCaptureFlow
    CAMERA_AVAILABLE = True
    camera_module = AutoCaptureFlow
except ImportError as e:
    import traceback
    print(f"Camera module import failed: {e}")
    print("Camera functionality will be disabled.")
except Exception as e:
    print(f"Error loading camera module: {e}")
    print("Camera functionality will be disabled.")

# ── Tech HMI palette ─────────────────────────────────────────────────────
_T = {
    "bg0": "#030810", "bg1": "#060C14", "bg2": "#08111E", "bg3": "#050D18",
    "cyan": "#00AAFF", "green": "#00AAFF", "amber": "#00AAFF", "red": "#FF3344",
    "bd": "#1A3A5C", "bd_dim": "#0E2A40",
    "t0": "#FFFFFF", "t1": "#CCDDEE", "t2": "#7AAAD4",
    # All action buttons use the same cyan style
    "green_bg": "#003A6A", "green_bd": "#00AAFF",
    "amber_bg": "#003A6A", "amber_bd": "#00AAFF",
    "red_bg": "#4A0A14", "red_bd": "#FF3344",
}

def _btn(color, bg, bd, hover_bg, min_width=100):
    """Primary 3D action button — raised green with gradient + shadow edge."""
    return (
        f"QPushButton {{"
        f"font-size:22px;font-weight:900;"
        f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"  stop:0 #0A3020, stop:0.45 #052818, stop:1 #020C08);"
        f"color:#00FF88;"
        f"border:1px solid #00FF8833;"
        f"border-top:1px solid #00FF8866;"
        f"border-bottom:4px solid #010804;"
        f"border-radius:3px;"
        f"min-width:{min_width}px;"
        f"font-family:Consolas;letter-spacing:3px;padding:10px 20px;}}"
        f"QPushButton:hover{{"
        f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"  stop:0 #0F4030, stop:0.45 #073020, stop:1 #020C08);"
        f"border:1px solid #00FF8866;"
        f"border-top:1px solid #00FF88;"
        f"border-bottom:4px solid #010804;"
        f"color:#FFFFFF;}}"
        f"QPushButton:pressed{{"
        f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"  stop:0 #021008, stop:1 #041810);"
        f"border-bottom:1px solid #010804;"
        f"padding-top:13px;}}"
        f"QPushButton:disabled{{"
        f"background:#0A1820;color:#1A3A1A;"
        f"border:1px solid #0E2A0E;border-bottom:4px solid #050A05;}}"
    )

def _btn_flat(label_color, min_width=120):
    """Secondary 3D button — raised outlined with shadow edge."""
    if label_color in ("#FF3344", "#FF3355"):
        return (
            f"QPushButton {{"
            f"font-size:22px;font-weight:900;"
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"  stop:0 #200810, stop:0.45 #150508, stop:1 #080204);"
            f"color:#FF3344;"
            f"border:1px solid #FF334433;"
            f"border-top:1px solid #FF334466;"
            f"border-bottom:4px solid #050104;"
            f"border-radius:3px;"
            f"min-width:{min_width}px;"
            f"font-family:Consolas;letter-spacing:2px;padding:10px 20px;}}"
            f"QPushButton:hover{{"
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"  stop:0 #2A1018, stop:0.45 #1A0810, stop:1 #080204);"
            f"border:1px solid #FF334466;"
            f"border-top:1px solid #FF3344;"
            f"border-bottom:4px solid #050104;"
            f"color:#FFFFFF;}}"
            f"QPushButton:pressed{{"
            f"background:#100408;border-bottom:1px solid #050104;"
            f"padding-top:13px;}}"
        )
    return (
        f"QPushButton {{"
        f"font-size:22px;font-weight:900;"
        f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"  stop:0 #0A1828, stop:0.45 #071020, stop:1 #030810);"
        f"color:{label_color};"
        f"border:1px solid {label_color}33;"
        f"border-top:1px solid {label_color}55;"
        f"border-bottom:4px solid #020408;"
        f"border-radius:3px;"
        f"min-width:{min_width}px;"
        f"font-family:Consolas;letter-spacing:2px;padding:10px 20px;}}"
        f"QPushButton:hover{{"
        f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        f"  stop:0 #0E2038, stop:0.45 #0A1828, stop:1 #030810);"
        f"border:1px solid {label_color}55;"
        f"border-top:1px solid {label_color};"
        f"border-bottom:4px solid #020408;"
        f"color:#FFFFFF;}}"
        f"QPushButton:pressed{{"
        f"background:#050D18;border-bottom:1px solid #020408;"
        f"padding-top:13px;}}"
    )


def _panel_hdr(color="#00AAFF"):
    return (
        f"font-size:11px;font-weight:900;color:{color};"
        f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"  stop:0 #0A1828, stop:1 #060C14);"
        f"border-bottom:1px solid {color}44;"
        f"padding:10px 14px;letter-spacing:4px;font-family:Consolas;"
    )

def _info_row(accent="#1A3A5C"):
    return (
        f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"  stop:0 #050D18, stop:1 #030810);"
        f"border-left:3px solid {accent};"
        f"padding:6px 12px;font-family:Consolas;font-size:13px;color:#CCDDEE;"
    )


class Calibration:
    def __init__(self):
        self.pixel_points = []
        self.world_points = []
        self.calibration_matrix = None
        self.is_calibrated = False
        self.calibration_file = None

    def load_calibration(self, filepath):
        try:
            with open(filepath, 'r') as f:
                calibration_data = json.load(f)
            self.calibration_matrix = np.array(calibration_data['calibration_matrix'])
            self.pixel_points = calibration_data['pixel_points']
            self.world_points = calibration_data['world_points']
            self.is_calibrated = True
            self.calibration_file = filepath
            return True, f"Calibration loaded from {filepath}"
        except Exception as e:
            return False, f"Failed to load calibration: {str(e)}"

    def pixel_to_world(self, pixel_point):
        if not self.is_calibrated or self.calibration_matrix is None:
            return None
        try:
            pixel_array = np.array([[pixel_point[0], pixel_point[1]]], dtype=np.float32)
            world_array = cv2.perspectiveTransform(pixel_array.reshape(-1, 1, 2), self.calibration_matrix)
            world_point = world_array[0][0]
            return (float(world_point[0]), float(world_point[1]))
        except Exception as e:
            print(f"Conversion error: {e}")
            return None


class CaptureWorker(QThread):
    finished = Signal(bool, str, str)

    def __init__(self, block_folder, step_number, product_name, filename, save_image=True):
        super().__init__()
        self.block_folder = block_folder
        self.step_number = step_number
        self.product_name = product_name
        self.filename = filename
        self.save_image = save_image
        self.is_running = True

    def run(self):
        try:
            def capture_callback(success, message, image_path):
                if success and image_path:
                    if self.save_image:
                        save_path = os.path.join(self.block_folder, self.filename)
                        try:
                            shutil.copy2(image_path, save_path)
                            if os.path.exists(image_path):
                                os.remove(image_path)
                            self.finished.emit(True, f"Image captured successfully", save_path)
                        except Exception as e:
                            self.finished.emit(False, f"Failed to save image: {str(e)}", None)
                    else:
                        self.finished.emit(True, f"Image captured (temporary)", image_path)
                else:
                    self.finished.emit(success, message, None)

            if CAMERA_AVAILABLE:
                AutoCaptureFlow(callback=capture_callback)
            else:
                self.finished.emit(False, "Camera module not available", None)
        except Exception as e:
            self.finished.emit(False, f"Capture error: {str(e)}", None)

    def stop(self):
        self.is_running = False


class AssemblyDialog(QDialog):
    prediction_success = Signal(int, str, list, str, str, object)
    prediction_failed = Signal(int, str, str, object)

    _heartbeat_manager = None
    _heartbeat_reference_count = 0

    def __init__(self, parent=None, initial_config=None, block_id=None, block_name=None):
        super().__init__(parent)
        self.block_id = block_id or "1"
        self.block_name = block_name or f"Block_{self.block_id}"
        self.prediction_success.connect(self._on_prediction_success)
        self.prediction_failed.connect(self._on_prediction_failed)
        self._init_heartbeat_manager()

        if initial_config and 'block_id' in initial_config:
            self.block_id = initial_config['block_id']
            if 'block_name' in initial_config:
                self.block_name = initial_config['block_name']
            else:
                self.block_name = f"Block_{self.block_id}"

        self.capture_worker = None
        self.progress_dialog = None
        self.step_selections = {}
        self.selected_thumbnails = {}
        self.available_products = []
        self.thumbnail_widgets = {}
        self.step_widgets = {}
        self.current_active_step = 1
        self.total_steps = 1
        self.annotation_folder = None
        self.assembly_folder = None
        self.initial_config = initial_config or {}
        self.assembly_tool_window = None
        self.video_folder = None
        self.uploaded_video_path = None
        self.prediction_manager = PredictionManager()
        self.is_predicting = False
        self.tcp_socket = None
        self.tcp_connected = False
        self.tcp_connection_attempted = False
        self.calibration = Calibration()
        self.calibration_path = "C:\\Users\\PC_AI_DS\\Pictures\\LaserCalibration\\calibration.json"

        if os.path.exists(self.calibration_path):
            success, message = self.calibration.load_calibration(self.calibration_path)
            if success:
                print(f"✅ Calibration loaded from: {self.calibration_path}")
            else:
                print(f"⚠️ Failed to load calibration: {message}")
        else:
            print(f"⚠️ Calibration file not found at: {self.calibration_path}")

        self.setWindowTitle("Assembly Configuration")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.showFullScreen()
        # ── Tech HMI dialog style ──────────────────────────────────────────
        self.setStyleSheet("""
            QDialog {
                background-color: #060C14;
                border: 1px solid #00AAFF44;
            }
            QLabel {
                color: #CCDDEE;
                background-color: transparent;
            }
            QGroupBox {
                color: #00AAFF;
                font-family: Consolas;
                font-weight: 900;
                font-size: 13px;
                border: 1px solid #1A3A5C;
                border-left: 3px solid #00AAFF;
                border-radius: 0px;
                padding-top: 18px;
                margin-top: 6px;
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #070F1C,stop:1 #060C14);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #00AAFF;
                font-family: Consolas;
                letter-spacing: 2px;
            }
            QScrollArea {
                border: 1px solid #0E2A40;
                border-radius: 0px;
                background-color: #050D18;
            }
            QScrollBar:vertical {
                background: #030810;
                width: 6px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #1A3A5C;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.init_ui()

        if self.initial_config:
            QTimer.singleShot(100, self.load_initial_configuration)

        if self.block_name:
            self.setWindowTitle(f"Assembly Configuration — {self.block_name}")
        else:
            self.setWindowTitle("Assembly Configuration")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Header bar ────────────────────────────────────────────────────
        recipe_info = self.get_current_recipe_info()
        hdr_bar = QWidget()
        hdr_bar.setFixedHeight(72)
        hdr_bar.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0A1828,stop:0.6 #060C14,stop:1 #050D18); border-bottom:2px solid #00AAFF;")
        hdr_row = QHBoxLayout(hdr_bar)
        hdr_row.setContentsMargins(14, 0, 14, 0); hdr_row.setSpacing(12)
        hdr_title = QLabel(f"ASSEMBLY CONFIGURATION  —  {recipe_info}")
        hdr_title.setStyleSheet("font-size:18px;font-weight:900;color:#FFFFFF;letter-spacing:2px;font-family:Consolas;background:transparent;")
        hdr_row.addWidget(hdr_title); hdr_row.addStretch()
        layout.addWidget(hdr_bar)

        # ── Assembly Result toolbar ───────────────────────────────────────
        prediction_toolbar = QGroupBox("ASSEMBLY RESULT")
        prediction_toolbar.setFixedHeight(100)
        toolbar_layout = QHBoxLayout(prediction_toolbar)
        toolbar_layout.setSpacing(10)

        self.assembly_tool_btn = QPushButton("⬡  ASSEMBLY LOCATION")
        self.assembly_tool_btn.setFixedHeight(60)
        self.assembly_tool_btn.setStyleSheet("QPushButton{font-size:22px;font-weight:900;background-color:#031A10;color:#00FF88;""border:none;border-top:2px solid #00FF88;border-radius:0px;min-width:200px;""font-family:Consolas;letter-spacing:3px;}""QPushButton:hover{background-color:#052A18;color:#FFFFFF;}""QPushButton:pressed{background-color:#021008;}")
        self.assembly_tool_btn.clicked.connect(self.open_assembly_tool)
        self.assembly_tool_btn.setToolTip("Open Assembly Annotation Tool")
        toolbar_layout.addWidget(self.assembly_tool_btn)

        self.upload_video_btn = QPushButton("▶  UPLOAD VIDEO")
        self.upload_video_btn.setFixedHeight(60)
        self.upload_video_btn.setStyleSheet("QPushButton{font-size:22px;font-weight:900;background-color:#031A10;color:#00FF88;""border:none;border-top:2px solid #00FF88;border-radius:0px;min-width:180px;""font-family:Consolas;letter-spacing:3px;}""QPushButton:hover{background-color:#052A18;color:#FFFFFF;}""QPushButton:pressed{background-color:#021008;}")
        self.upload_video_btn.clicked.connect(self.upload_video)
        self.upload_video_btn.setToolTip("Upload a video file for this Assembly block")
        toolbar_layout.addWidget(self.upload_video_btn)

        self.model_status_label = QLabel("NO MODEL LOADED")
        self.model_status_label.setStyleSheet(
            "font-size:12px;color:#7AAAD4;padding:6px 10px;background:#050D18;"
            "border:1px solid #0E2A40;border-radius:0px;min-width:200px;font-family:Consolas;")
        toolbar_layout.addWidget(self.model_status_label)

        self.prediction_status_label = QLabel("PREDICTION: READY")
        self.prediction_status_label.setStyleSheet(
            "font-size:12px;color:#00FF88;padding:6px 10px;background:#031A10;"
            "border:1px solid #0A5030;border-radius:0px;min-width:150px;font-family:Consolas;")
        toolbar_layout.addWidget(self.prediction_status_label)
        toolbar_layout.addStretch()
        layout.addWidget(prediction_toolbar)

        # ── Main content ──────────────────────────────────────────────────
        main_content = QHBoxLayout()
        main_content.setSpacing(12)

        # Left: step config
        left_column = QVBoxLayout()

        step_group = QGroupBox("ASSEMBLY STEP")
        step_layout = QFormLayout(step_group)

        fixed_step_label = QLabel("1")
        fixed_step_label.setStyleSheet(
            "font-size:16px;padding:8px 12px;background:#050D18;color:#FFFFFF;"
            "border:1px solid #1A3A5C;border-radius:0px;min-width:80px;font-family:Consolas;")
        step_layout.addRow("TOTAL STEPS:", fixed_step_label)
        left_column.addWidget(step_group)

        self.steps_container = QWidget()
        self.steps_container.setStyleSheet("background:#060C14;")
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setSpacing(8)
        self.steps_layout.setContentsMargins(0, 8, 0, 8)

        self.steps_scroll = QScrollArea()
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setWidget(self.steps_container)
        self.steps_scroll.setMinimumHeight(350)
        left_column.addWidget(self.steps_scroll)

        # Right: gallery
        right_column = QVBoxLayout()

        gallery_header = QLabel("PRODUCT IMAGES  —  CLICK TO SELECT")
        gallery_header.setStyleSheet(
            "font-size:14px;font-weight:900;color:#FFFFFF;padding:10px 14px;"
            "background:#050D18;border-bottom:2px solid #00AAFF;border-left:4px solid #00AAFF;"
            "border-radius:0px;margin-bottom:0px;font-family:Consolas;letter-spacing:2px;")
        gallery_header.setAlignment(Qt.AlignCenter)
        right_column.addWidget(gallery_header)

        self.step_indicator = QLabel(f"▸  SELECTING FOR: STEP {self.current_active_step}")
        self.step_indicator.setStyleSheet(
            "font-size:13px;font-weight:900;color:#FFAA00;padding:8px 12px;"
            "background:#1A1000;border:1px solid #553300;border-left:3px solid #FFAA00;"
            "border-radius:0px;margin-bottom:0px;font-family:Consolas;letter-spacing:1px;")
        self.step_indicator.setAlignment(Qt.AlignCenter)
        right_column.addWidget(self.step_indicator)

        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)

        self.gallery_container = QWidget()
        self.gallery_container.setStyleSheet("background:#060C14;")
        self.gallery_layout = QGridLayout(self.gallery_container)
        self.gallery_layout.setAlignment(Qt.AlignTop)
        self.gallery_layout.setSpacing(8)
        self.gallery_layout.setContentsMargins(12, 12, 12, 12)

        self.gallery_scroll.setWidget(self.gallery_container)
        self.gallery_scroll.setMinimumHeight(400)
        right_column.addWidget(self.gallery_scroll)
        right_column.addStretch()

        main_content.addLayout(left_column, 45)
        main_content.addLayout(right_column, 55)
        layout.addLayout(main_content)

        # ── Bottom button footer strip ────────────────────────────────────
        btn_footer = QWidget()
        btn_footer.setFixedHeight(100)
        btn_footer.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0A1828,stop:1 #060C14);border-top:2px solid #00AAFF44;")
        button_layout = QHBoxLayout(btn_footer)
        button_layout.setContentsMargins(16, 12, 16, 12)
        button_layout.setSpacing(12)

        refresh_btn = QPushButton("↺  LOAD ANNOTATION IMAGES")
        refresh_btn.setFixedHeight(66)
        refresh_btn.setStyleSheet("QPushButton{font-size:22px;font-weight:900;background:transparent;color:#FF3344;""border:1px solid #FF334455;border-radius:2px;min-width:280px;""font-family:Consolas;letter-spacing:2px;}""QPushButton:hover{background:#1A0508;border:1px solid #FF3344;color:#FFFFFF;}""QPushButton:pressed{background:#220810;}")
        refresh_btn.clicked.connect(self.load_bmp_from_annotation)

        self.ok_btn = QPushButton("✓  COMPLETE SELECTION")
        self.ok_btn.setFixedHeight(66)
        self.ok_btn.setStyleSheet("QPushButton{font-size:22px;font-weight:900;background-color:#031A10;color:#00FF88;""border:none;border-top:2px solid #00FF88;border-radius:0px;min-width:260px;""font-family:Consolas;letter-spacing:3px;}""QPushButton:hover{background-color:#052A18;color:#FFFFFF;}""QPushButton:disabled{background-color:#0A1820;color:#1A4A2A;}""QPushButton:pressed{background-color:#021008;}")
        self.ok_btn.clicked.connect(self.validate_and_accept)
        self.ok_btn.setEnabled(False)

        cancel_btn = QPushButton("✕  CANCEL")
        cancel_btn.setFixedHeight(66)
        cancel_btn.setStyleSheet("QPushButton{font-size:22px;font-weight:900;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3A0A10,stop:0.45 #220810,stop:1 #0C0204);color:#FF3344;border:1px solid #FF334433;border-top:1px solid #FF334488;border-bottom:4px solid #050104;border-radius:3px;font-family:Consolas;letter-spacing:2px;padding:10px 20px;}QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4A1020,stop:0.45 #2A1018,stop:1 #0C0204);border-top:1px solid #FF3344;border-bottom:4px solid #050104;color:#FFFFFF;}QPushButton:pressed{background:#150408;border-bottom:1px solid #050104;padding-top:13px;}min-width:180px;")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addWidget(btn_footer)

        self.create_step_widget(1)
        QTimer.singleShot(100, self.load_bmp_from_annotation)

    def create_step_widget(self, step_number):
        step_frame = QFrame()
        step_frame.setFrameStyle(QFrame.Box)
        self.step_widgets[step_number] = {'frame': step_frame, 'capture_counter': 0, 'capture_folder': None}

        if step_number == self.current_active_step:
            step_frame.setStyleSheet(
                "QFrame { border:1px solid #1A3A5C; border-left:3px solid #00AAFF; "
                "border-top:2px solid #00AAFF; border-radius:0px; background:#07111E; padding:10px; }")
        else:
            step_frame.setStyleSheet(
                "QFrame { border:1px solid #0E2A40; border-radius:0px; background:#060C14; padding:10px; }")

        layout = QVBoxLayout(step_frame)
        layout.setSpacing(8)

        header = QLabel(f"STEP {step_number}")
        header.setStyleSheet(
            "font-size:13px;font-weight:900;color:#AACCEE;padding-bottom:4px;"
            "border-bottom:1px solid #1A3A5C;font-family:Consolas;letter-spacing:3px;")
        layout.addWidget(header)

        selection_display = QLabel("  NOT SELECTED")
        selection_display.setStyleSheet(
            "font-size:13px;color:#7AAAD4;padding:8px 10px;background:#050D18;"
            "border:1px solid #0E2A40;border-radius:0px;min-height:36px;font-family:Consolas;")
        selection_display.setWordWrap(True)
        selection_display.setObjectName(f"step_{step_number}_display")
        layout.addWidget(selection_display)

        step_frame.setProperty("step_number", step_number)
        self.steps_layout.addWidget(step_frame)

    def update_step_display(self, step_number, product):
        if step_number not in self.step_widgets:
            return
        step_frame = self.step_widgets[step_number]['frame']
        display_label = step_frame.findChild(QLabel, f"step_{step_number}_display")
        if display_label:
            if product:
                display_label.setText(f"✓  {product['name']}\n    {product['filename']}")
                display_label.setStyleSheet(
                    "font-size:13px;color:#00FF88;padding:8px 10px;background:#031A10;"
                    "border:1px solid #1A3A5C;border-left:3px solid #00AAFF;"
                    "border-radius:0px;min-height:36px;font-weight:900;font-family:Consolas;")
                step_frame.setStyleSheet(
                    "QFrame { border:1px solid #1A3A5C; border-left:3px solid #00AAFF; "
                    "border-radius:0px; background:#031A10; padding:10px; }")
            else:
                display_label.setText("  NOT SELECTED")
                display_label.setStyleSheet(
                    "font-size:13px;color:#7AAAD4;padding:8px 10px;background:#050D18;"
                    "border:1px solid #0E2A40;border-radius:0px;min-height:36px;font-family:Consolas;")
                if step_number == self.current_active_step:
                    step_frame.setStyleSheet(
                        "QFrame { border:1px solid #1A3A5C; border-left:3px solid #00AAFF; "
                        "border-top:2px solid #00AAFF; border-radius:0px; background:#07111E; padding:10px; }")
                else:
                    step_frame.setStyleSheet(
                        "QFrame { border:1px solid #0E2A40; border-radius:0px; background:#060C14; padding:10px; }")

    def update_gallery(self):
        while self.gallery_layout.count():
            child = self.gallery_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.thumbnail_widgets = {}

        if not self.available_products:
            if self.annotation_folder:
                empty_text = f"NO IMAGES FOUND\n{os.path.basename(self.annotation_folder)}\n(Supported: BMP, JPG, PNG, TIFF, WEBP)"
            else:
                empty_text = "NO ANNOTATION FOLDER FOUND"
            empty_label = QLabel(empty_text)
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(
                "font-size:14px;color:#2A5A7A;padding:60px;background:#050D18;"
                "border:1px solid #0E2A40;font-family:Consolas;letter-spacing:2px;")
            self.gallery_layout.addWidget(empty_label, 0, 0, 1, 4)
            return

        row = 0; col = 0; max_cols = 4
        for product in self.available_products:
            thumbnail_widget = self.create_thumbnail_widget(product)
            self.thumbnail_widgets[product['id']] = thumbnail_widget
            self.gallery_layout.addWidget(thumbnail_widget, row, col)
            col += 1
            if col >= max_cols:
                col = 0; row += 1

    def create_thumbnail_widget(self, product):
        widget = QFrame()
        widget.setFrameStyle(QFrame.Box)
        is_selected = product['id'] in self.selected_thumbnails.values()

        if is_selected:
            widget.setStyleSheet(
                "QFrame { border:1px solid #0A5030; border-left:4px solid #00FF88; "
                "border-top:2px solid #00FF88; border-radius:2px; background:#031A10; padding:6px; }")
        else:
            widget.setStyleSheet(
                "QFrame { border:1px solid #0E2A40; border-radius:2px; background:#060C14; padding:6px; }"
                "QFrame:hover { border:1px solid #1A5080; border-left:3px solid #00AAFF; background:#07111E; }")

        widget.setCursor(Qt.PointingHandCursor)
        widget.setFixedSize(180, 200)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        thumbnail = QLabel()
        thumbnail.setAlignment(Qt.AlignCenter)
        thumbnail.setFixedSize(150, 100)

        try:
            pixmap = QPixmap(product['image_path'])
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(140, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
                thumbnail.setPixmap(scaled_pixmap)
                thumbnail.setStyleSheet("border:1px solid #1A3A5C; border-radius:2px;")
            else:
                thumbnail.setText("❌\nInvalid BMP")
                thumbnail.setStyleSheet(
                    "background:#1A0508;color:#FF3344;font-size:10px;border:1px solid #661020;border-radius:2px;")
        except:
            thumbnail.setText("⚠\nLoad Error")
            thumbnail.setStyleSheet(
                "background:#1A1000;color:#FFAA00;font-size:10px;border:1px solid #553300;border-radius:2px;")

        name_label = QLabel(product['name'])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(
            "font-weight:900;font-size:12px;color:#FFFFFF;padding:2px;font-family:Consolas;")
        name_label.setWordWrap(True)
        name_label.setToolTip(f"Original: {product['original_name']}")

        file_label = QLabel(product['filename'])
        file_label.setAlignment(Qt.AlignCenter)
        file_label.setStyleSheet("font-size:10px;color:#7AAAD4;padding:1px;font-family:Consolas;")
        file_label.setWordWrap(True)

        status_label = QLabel(" ")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setFixedHeight(20)

        if is_selected:
            for step, pid in self.selected_thumbnails.items():
                if pid == product['id']:
                    status_label.setText(f"✓ STEP {step}")
                    status_label.setStyleSheet(
                        "color:#00AAFF;font-weight:900;font-size:11px;"
                        "background:#071828;border-radius:2px;padding:2px;font-family:Consolas;")
                    break

        layout.addWidget(thumbnail)
        layout.addWidget(name_label)
        layout.addWidget(file_label)
        layout.addWidget(status_label)

        widget.mousePressEvent = lambda event, pid=product['id']: self.select_image_for_step(pid)
        return widget

    def update_thumbnail_selection(self, product_id, step_number):
        self.selected_thumbnails[step_number] = product_id
        for pid, widget in self.thumbnail_widgets.items():
            layout = widget.layout()
            if layout and layout.count() >= 4:
                status_label = layout.itemAt(3).widget()
                if pid == product_id:
                    widget.setStyleSheet(
                        "QFrame { border:1px solid #0A5030; border-left:4px solid #00FF88; "
                        "border-top:2px solid #00FF88; border-radius:2px; background:#031A10; padding:6px; }")
                    status_label.setText(f"✓ STEP {step_number}")
                    status_label.setStyleSheet(
                        "color:#00AAFF;font-weight:900;font-size:11px;"
                        "background:#071828;border-radius:2px;padding:2px;font-family:Consolas;")
                elif pid in self.selected_thumbnails.values():
                    for step, selected_pid in self.selected_thumbnails.items():
                        if selected_pid == pid:
                            widget.setStyleSheet(
                                "QFrame { border:1px solid #553300; border-left:3px solid #FFAA00; "
                                "border-radius:2px; background:#0A0800; padding:6px; }")
                            status_label.setText(f"✓ STEP {step}")
                            status_label.setStyleSheet(
                                "color:#FFAA00;font-weight:900;font-size:11px;"
                                "background:#1A1000;border-radius:2px;padding:2px;font-family:Consolas;")
                            break
                else:
                    widget.setStyleSheet(
                        "QFrame { border:1px solid #0E2A40; border-radius:2px; background:#060C14; padding:6px; }"
                        "QFrame:hover { border:1px solid #1A5080; border-left:3px solid #00AAFF; background:#07111E; }")
                    status_label.setText(" ")
                    status_label.setStyleSheet("")

    def update_step_indicator(self):
        self.step_indicator.setText(f"▸  SELECTING FOR: STEP {self.current_active_step}")

    def set_active_step(self, step_number):
        if step_number > self.total_steps:
            return
        self.current_active_step = step_number
        self.update_step_indicator()
        for step, data in self.step_widgets.items():
            step_frame = data['frame']
            if step == step_number:
                if step in self.step_selections:
                    step_frame.setStyleSheet(
                        "QFrame { border:1px solid #1A3A5C; border-left:3px solid #00AAFF; "
                        "border-top:2px solid #00AAFF; border-radius:0px; background:#071828; padding:10px; }")
                else:
                    step_frame.setStyleSheet(
                        "QFrame { border:1px solid #1A3A5C; border-left:3px solid #00AAFF; "
                        "border-top:2px solid #00AAFF; border-radius:0px; background:#07111E; padding:10px; }")
            elif step in self.step_selections:
                step_frame.setStyleSheet(
                    "QFrame { border:1px solid #1A3A5C; border-left:3px solid #00AAFF; "
                    "border-radius:0px; background:#031A10; padding:10px; }")
            else:
                step_frame.setStyleSheet(
                    "QFrame { border:1px solid #0E2A40; border-radius:0px; background:#060C14; padding:10px; }")

    def update_capture_status(self, step_number, status_text):
        if step_number not in self.step_widgets:
            return
        step_frame = self.step_widgets[step_number]['frame']
        status_label = step_frame.findChild(QLabel, f"step_{step_number}_capture_status")
        if not status_label:
            return
        step_folder = self.step_widgets[step_number].get('capture_folder')
        if step_folder and os.path.exists(step_folder):
            pattern = os.path.join(step_folder, f"Step_{step_number}_*.bmp")
            existing_images = glob.glob(pattern)
            if existing_images:
                status_text = "1 image captured"
        status_label.setText(status_text)
        if "1 image" in status_text:
            status_label.setStyleSheet("font-size:12px;color:#00FF88;padding:4px 8px;background:#031A10;border-radius:2px;font-weight:900;font-family:Consolas;")
        elif "failed" in status_text.lower():
            status_label.setStyleSheet("font-size:12px;color:#FF3344;padding:4px 8px;background:#1A0508;border-radius:2px;font-weight:900;font-family:Consolas;")
        else:
            status_label.setStyleSheet("font-size:12px;color:#7AAAD4;padding:4px 8px;background:#050D18;border-radius:2px;font-family:Consolas;")

    # ── All remaining methods unchanged (business logic only) ─────────────
    def ensure_video_folder(self):
        recipe_path = self.get_current_recipe_path()
        if not recipe_path:
            return None
        self.video_folder = os.path.join(recipe_path, "Assembly", f"Block_{self.block_id}", "uploaded_videos")
        os.makedirs(self.video_folder, exist_ok=True)
        return self.video_folder

    def upload_video(self):
        try:
            video_folder = self.ensure_video_folder()
            if not video_folder:
                QMessageBox.warning(self, "⚠️ No Recipe", "Current recipe not found.")
                return
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", "",
                "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.mpeg *.mpg);;All Files (*.*)")
            if not file_path or not os.path.exists(file_path):
                return
            original_name = os.path.basename(file_path)
            ext = os.path.splitext(original_name)[1]
            recipe_name = "unknown_recipe"
            try:
                if hasattr(config_manager, 'current_recipe_name') and config_manager.current_recipe_name:
                    recipe_name = str(config_manager.current_recipe_name)
                elif hasattr(config_manager, 'current_recipe') and config_manager.current_recipe:
                    recipe_name = str(config_manager.current_recipe)
            except:
                pass
            safe_recipe_name = re.sub(r'[^\w\-\.]', '_', str(recipe_name))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_filename = f"{safe_recipe_name}_Block_{self.block_id}_{timestamp}{ext}"
            target_path = os.path.join(video_folder, target_filename)
            shutil.copy2(file_path, target_path)
            self.uploaded_video_path = target_path
            recipe_path = self.get_current_recipe_path()
            rel_path = target_path
            if recipe_path:
                try:
                    rel_path = os.path.relpath(target_path, recipe_path)
                except:
                    pass
            QMessageBox.information(self, "✅ Video Uploaded", f"Video uploaded successfully.\n\nSaved to:\n{rel_path}")
        except Exception as e:
            QMessageBox.critical(self, "❌ Upload Failed", f"Failed to upload video:\n\n{str(e)}")

    def open_assembly_tool(self):
        self.disconnect_tcp()
        self.update_tcp_messages("🔌 TCP disconnected for Assembly Tool")
        try:
            from ui.components.assembly_laser import MainWindow as AssemblyLaserMainWindow
            if self.assembly_tool_window and self.assembly_tool_window.isVisible():
                self.assembly_tool_window.raise_()
                self.assembly_tool_window.activateWindow()
                self.hide()
                return
            self.assembly_tool_window = AssemblyLaserMainWindow(
                block_id=str(self.block_id), block_name=str(self.block_name), mode="assembly")
            self.assembly_tool_window.setParent(None)
            self.assembly_tool_window.setWindowFlags(
                Qt.Window | Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint |
                Qt.WindowTitleHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
            self.assembly_tool_window.setWindowModality(Qt.NonModal)
            self.assembly_tool_window.setAttribute(Qt.WA_DeleteOnClose)
            if hasattr(self.assembly_tool_window, 'set_recipe_info'):
                recipe_path = self.get_current_recipe_path()
                self.assembly_tool_window.set_recipe_info(recipe_path, self.block_name)
            self.assembly_tool_window.destroyed.connect(self._on_assembly_tool_closed)
            self.assembly_tool_window.show()
            self.assembly_tool_window.raise_()
            self.assembly_tool_window.activateWindow()
            self.hide()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to open Assembly Tool:\n\n{str(e)}")

    def _on_assembly_tool_closed(self):
        self.update_tcp_messages("✅ Assembly Tool closed")
        self.assembly_tool_window = None
        self.show(); self.raise_(); self.activateWindow()

    def _init_heartbeat_manager(self):
        if AssemblyDialog._heartbeat_manager is None:
            AssemblyDialog._heartbeat_manager = HeartbeatManager()
            AssemblyDialog._heartbeat_manager.connection_status_changed.connect(self._on_heartbeat_connection_changed)
            AssemblyDialog._heartbeat_manager.heartbeat_sent.connect(self._on_heartbeat_sent)
        AssemblyDialog._heartbeat_reference_count += 1
        self._ensure_heartbeat_connected()

    def _on_heartbeat_connection_changed(self, connected, message):
        self.update_tcp_messages(f"{'✅ Heartbeat connected' if connected else '🔴 Heartbeat disconnected'}: {message}")

    def _on_heartbeat_sent(self, message):
        self.update_tcp_messages(f"💓 {message}")

    def _ensure_heartbeat_connected(self):
        if AssemblyDialog._heartbeat_manager and not AssemblyDialog._heartbeat_manager.is_connected():
            server_ip = self.get_server_address()
            server_port = self.get_server_port()
            success, message = AssemblyDialog._heartbeat_manager.connect(server_ip, server_port)
            if success:
                self.update_tcp_messages(f"✅ Heartbeat started (interval: 5s)")
            else:
                self.update_tcp_messages(f"❌ Heartbeat failed: {message}")

    def ensure_tcp_connected(self):
        if hasattr(AssemblyDialog, '_global_tcp_socket') and AssemblyDialog._global_tcp_socket:
            self.tcp_socket = AssemblyDialog._global_tcp_socket
            self.tcp_connected = True
            return True
        try:
            server_ip = self.get_server_address()
            server_port = self.get_server_port()
            if not server_ip:
                return False
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(5)
            self.tcp_socket.connect((server_ip, server_port))
            self.tcp_connected = True
            AssemblyDialog._global_tcp_socket = self.tcp_socket
            return True
        except Exception as e:
            self.tcp_connected = False
            self.tcp_socket = None
            AssemblyDialog._global_tcp_socket = None
            return False

    def get_server_address(self):
        try:
            if hasattr(config_manager, 'get_tcp_server'):
                return config_manager.get_tcp_server()
        except:
            pass
        return "127.0.0.1"

    def get_server_port(self):
        try:
            if hasattr(config_manager, 'get_tcp_port'):
                return config_manager.get_tcp_port()
        except:
            pass
        return 8888

    def update_tcp_messages(self, message):
        try:
            if hasattr(self, 'tcp_messages_display'):
                current_text = self.tcp_messages_display.toPlainText()
                timestamp = time.strftime("%H:%M:%S")
                new_text = f"[{timestamp}] {message}\n{current_text}"
                self.tcp_messages_display.setPlainText(new_text)
        except:
            print(f"[TCP] {message}")

    def select_image_for_step(self, product_id):
        try:
            self.ensure_tcp_connected()
        except Exception as e:
            print(f"⚠️ TCP connection attempt failed (non-critical): {e}")

        if product_id in self.selected_thumbnails.values():
            current_step = None
            for step, pid in self.selected_thumbnails.items():
                if pid == product_id:
                    current_step = step
                    break
            if current_step:
                reply = QMessageBox.question(self, "⚠️ Product Already Selected",
                    f"This image is already selected for Step {current_step}.\n\nDo you want to reassign it to Step {self.current_active_step}?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    return
                del self.step_selections[current_step]
                del self.selected_thumbnails[current_step]
                self.update_step_display(current_step, None)
                if current_step in self.step_widgets:
                    self.step_widgets[current_step]['capture_counter'] = 0
                    self.step_widgets[current_step]['capture_folder'] = None
                    self.update_capture_status(current_step, "No images captured")

        product = None
        for p in self.available_products:
            if p['id'] == product_id:
                product = p
                break
        if not product:
            return

        self.step_selections[self.current_active_step] = {
            'product_id': product_id,
            'product_data': {
                'name': product['name'], 'original_name': product['original_name'],
                'image_path': product['image_path'], 'filename': product['filename'],
                'annotation_path': product['relative_path'],
                'model_path': self.get_model_path(product_id),
                'trained': self.is_model_trained(product_id)
            }
        }

        self.update_step_display(self.current_active_step, product)
        self.update_thumbnail_selection(product_id, self.current_active_step)

        if self.current_active_step in self.step_widgets:
            step_frame = self.step_widgets[self.current_active_step]['frame']
            capture_btn = step_frame.findChild(QPushButton, f"step_{self.current_active_step}_capture_btn")
            if capture_btn:
                capture_btn.setEnabled(True)

        QTimer.singleShot(500, lambda: self.auto_capture_and_predict_for_step(
            self.current_active_step, product['name'], product['id']))

        if self.current_active_step < self.total_steps:
            self.current_active_step += 1
            self.update_step_indicator()
        else:
            self.check_completion()

    def load_initial_configuration(self):
        try:
            self.total_steps = int(self.initial_config.get('total_steps', 1) or 1)
            if 'selections' in self.initial_config and isinstance(self.initial_config['selections'], dict):
                QTimer.singleShot(200, lambda: self.restore_step_selections(self.initial_config['selections']))
            if 'uploaded_video_path' in self.initial_config:
                self.uploaded_video_path = self.initial_config.get('uploaded_video_path', '')
        except Exception as e:
            print(f"Error loading initial configuration: {e}")

    def restore_step_selections(self, selections):
        try:
            if not self.available_products:
                self.load_bmp_from_annotation()
                QTimer.singleShot(300, lambda: self._restore_selections_after_load(selections))
            else:
                self._restore_selections_after_load(selections)
        except Exception as e:
            print(f"Error restoring selections: {e}")

    def _restore_selections_after_load(self, selections):
        try:
            for step_str, selection in selections.items():
                try:
                    step_num = int(step_str)
                except ValueError:
                    continue
                product_id = selection['product_id']
                product = None
                for p in self.available_products:
                    if p['id'] == product_id:
                        product = p
                        break
                if product:
                    assembly_folder = self.ensure_assembly_folder()
                    capture_info = {}
                    if assembly_folder:
                        pattern = f"Step_{step_num}_*.bmp"
                        existing_images = glob.glob(os.path.join(assembly_folder, pattern))
                        if existing_images:
                            existing_images.sort(key=os.path.getmtime, reverse=True)
                            capture_info = {'capture_folder': assembly_folder, 'current_image': existing_images[0],
                                            'assembly_folder': assembly_folder, 'block_name': self.block_name}
                        else:
                            capture_info = {'capture_folder': assembly_folder, 'current_image': None,
                                            'assembly_folder': assembly_folder, 'block_name': self.block_name}
                    else:
                        capture_info = selection.get('capture_info', {})
                    self.step_selections[step_num] = {
                        'product_id': product_id,
                        'product_data': selection.get('product_data', {
                            'name': product['name'], 'original_name': product['original_name'],
                            'image_path': product['image_path'], 'filename': product['filename'],
                            'annotation_path': product['relative_path'],
                            'model_path': self.get_model_path(product_id),
                            'trained': self.is_model_trained(product_id)
                        }),
                        'capture_info': capture_info
                    }
                    self.update_step_display(step_num, product)
                    self.update_thumbnail_selection(product_id, step_num)
                    if step_num in self.step_widgets:
                        step_frame = self.step_widgets[step_num]['frame']
                        capture_btn = step_frame.findChild(QPushButton, f"step_{step_num}_capture_btn")
                        if capture_btn:
                            capture_btn.setEnabled(True)
                        if capture_info.get('current_image'):
                            self.step_widgets[step_num]['capture_folder'] = capture_info['capture_folder']
                            self.step_widgets[step_num]['capture_counter'] = 1
                            self.step_widgets[step_num]['current_image'] = capture_info['current_image']
                            self.update_capture_status(step_num, "1 image captured")
            if selections:
                step_keys = [int(k) for k in selections.keys() if k.isdigit()]
                if step_keys:
                    last_step = max(step_keys)
                    self.current_active_step = last_step + 1 if last_step < self.total_steps else 1
            self.update_step_indicator()
            self.check_completion()
        except Exception as e:
            print(f"Error in _restore_selections_after_load: {e}")
            import traceback; traceback.print_exc()

    def ensure_assembly_folder(self):
        recipe_path = self.get_current_recipe_path()
        if not recipe_path:
            return None
        self.assembly_folder = os.path.join(recipe_path, "Assembly", f"Block_{self.block_id}")
        os.makedirs(self.assembly_folder, exist_ok=True)
        return self.assembly_folder

    def auto_capture_and_predict_for_step(self, step_number, product_name, product_id):
        if not self.prediction_manager.is_model_loaded():
            model_loaded = self.auto_load_product_model(product_id)
            if not model_loaded:
                return
        assembly_folder = self.ensure_assembly_folder()
        if not assembly_folder:
            return
        predictions_folder = os.path.join(assembly_folder, "predictions")
        os.makedirs(predictions_folder, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Step_{step_number}_{timestamp}.bmp"
        self.prediction_status_label.setText(f"CAPTURING {product_name}...")
        self.capture_worker = CaptureWorker(assembly_folder, step_number, product_name, filename, save_image=False)
        self.capture_worker.finished.connect(
            lambda success, msg, path: self.on_auto_capture_prediction_finished(
                step_number, product_name, product_id, success, msg, path))
        self.capture_worker.start()
        self.progress_dialog = QProgressDialog(
            f"Step {step_number}: Auto-capturing {product_name}\n\nCamera will open automatically...",
            "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("AUTO CAPTURE & DETECT")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.cancel_capture)
        self.progress_dialog.show()

    def on_auto_capture_prediction_finished(self, step_number, product_name, product_id, success, message, image_path):
        if self.progress_dialog:
            self.progress_dialog.close()
        if success and image_path:
            self.step_widgets[step_number]['temp_image'] = image_path
            self.update_capture_status(step_number, "Image captured (temporary)")
            self.prediction_status_label.setText(f"DETECTING OBJECTS...")
            self.run_auto_prediction_on_captured(step_number, product_name, product_id, image_path)
            QTimer.singleShot(10000, lambda: self.cleanup_temp_file(image_path))
        else:
            QMessageBox.warning(self, "❌ Capture Failed", f"Failed to capture image for Step {step_number}: {message}")
            self.update_capture_status(step_number, "Capture failed")

    def cleanup_temp_file(self, file_path):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up temp file: {e}")

    def cancel_capture(self):
        if self.capture_worker and self.capture_worker.isRunning():
            self.capture_worker.stop(); self.capture_worker.quit(); self.capture_worker.wait()
        if self.progress_dialog:
            self.progress_dialog.close()

    def auto_load_product_model(self, product_id):
        try:
            recipe_path = self.get_current_recipe_path()
            if not recipe_path:
                return False
            yolo_model_folder = os.path.join(recipe_path, "yolo_model")
            if not os.path.exists(yolo_model_folder):
                return False
            model_files = []
            for root, dirs, files in os.walk(yolo_model_folder):
                for file in files:
                    if file.lower().endswith('.pt'):
                        if product_id.lower() in file.lower() or 'best' in file.lower():
                            model_files.append(os.path.join(root, file))
            if not model_files:
                return False
            model_files.sort(key=os.path.getmtime, reverse=True)
            success, message = self.prediction_manager.load_model(model_files[0])
            if success:
                self.model_status_label.setText(f"LOADED: {os.path.basename(model_files[0])}")
                return True
            return False
        except Exception as e:
            print(f"Error auto-loading model: {e}")
            return False

    def run_auto_prediction_on_captured(self, step_number, product_name, product_id, image_path):
        if not self.prediction_manager.is_model_loaded():
            return
        self.prediction_status_label.setText(f"DETECTING {product_name}")
        predict_dialog = QProgressDialog(f"Step {step_number}: Detecting {product_name}", "Cancel", 0, 100, self)
        predict_dialog.setWindowTitle("AI DETECTION")
        predict_dialog.setWindowModality(Qt.WindowModal)
        predict_dialog.setAutoClose(True)
        predict_dialog.show()
        class_id = self.prediction_manager.get_class_id_by_name(product_name)
        if class_id is None and '_' in product_name:
            class_id = self.prediction_manager.get_class_id_by_name(product_name.split('_')[-1])
        thread = threading.Thread(
            target=self._run_prediction_thread,
            args=(step_number, product_name, product_id, image_path, class_id, predict_dialog),
            daemon=True)
        thread.start()

    def _run_prediction_thread(self, step_number, product_name, product_id, image_path, class_filter, progress_dialog):
        try:
            def progress_callback(progress, status):
                QTimer.singleShot(0, lambda: self._update_prediction_progress(progress_dialog, progress, status))
            success, message, predictions, output_path = self.prediction_manager.predict_image(
                image_path, class_filter=class_filter, progress_callback=progress_callback, conf_threshold=0.25)
            if success:
                self.prediction_success.emit(step_number, product_name, predictions, output_path, message, progress_dialog)
            else:
                self.prediction_failed.emit(step_number, product_name, message, progress_dialog)
        except Exception as e:
            self.prediction_failed.emit(step_number, product_name, f"Error: {str(e)}", progress_dialog)

    def _update_prediction_progress(self, progress_dialog, progress, status):
        try:
            if progress_dialog and progress_dialog.isVisible():
                progress_dialog.setValue(progress)
                progress_dialog.setLabelText(f"{status}...")
                if progress >= 100:
                    QTimer.singleShot(500, lambda: self._safe_close_dialog(progress_dialog))
        except Exception as e:
            print(f"Error updating progress: {e}")

    def _safe_close_dialog(self, dialog):
        try:
            if dialog and dialog.isVisible():
                dialog.close(); dialog.deleteLater()
        except:
            pass

    def _on_prediction_success(self, step_number, product_name, predictions, output_path, message, progress_dialog):
        if progress_dialog:
            try:
                progress_dialog.close(); progress_dialog.deleteLater()
            except:
                pass
        if step_number in self.step_widgets:
            step_frame = self.step_widgets[step_number]['frame']
            display_label = step_frame.findChild(QLabel, f"step_{step_number}_display")
            if display_label:
                if predictions:
                    display_label.setText(f"✓  {product_name}\n    {len(predictions)} DETECTED")
                else:
                    display_label.setText(f"⚠  {product_name}\n    NO OBJECTS")
        if predictions:
            if self.calibration.is_calibrated:
                print(f"📐 Using WORLD coordinates")
            QTimer.singleShot(100, lambda: self.send_coordinates_to_server(predictions))
        try:
            if step_number in self.step_selections:
                product_data = self.step_selections[step_number]['product_data']
                product = {'name': product_data['name'], 'image_path': product_data['image_path'], 'filename': product_data['filename']}
                self.show_prediction_results_view(step_number, product, predictions, output_path, None)
        except Exception as e:
            print(f"Error showing results: {e}")

    def send_coordinates_to_server(self, predictions):
        if not AssemblyDialog._heartbeat_manager or not AssemblyDialog._heartbeat_manager.is_connected():
            self._ensure_heartbeat_connected()
            if not AssemblyDialog._heartbeat_manager or not AssemblyDialog._heartbeat_manager.is_connected():
                return False
        try:
            coordinate_lines = []
            for pred in predictions:
                bbox = pred.get('bbox', [0, 0, 0, 0])
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox[:4]
                    if self.calibration.is_calibrated:
                        world_corners = self._convert_to_world_coordinates([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])
                        coord_line = (f"{world_corners[0][0]:.2f}_{world_corners[0][1]:.2f},"
                                      f"{world_corners[1][0]:.2f}_{world_corners[1][1]:.2f},"
                                      f"{world_corners[2][0]:.2f}_{world_corners[2][1]:.2f},"
                                      f"{world_corners[3][0]:.2f}_{world_corners[3][1]:.2f}")
                    else:
                        coord_line = f"{x1:.2f}_{y1:.2f},{x2:.2f}_{y1:.2f},{x2:.2f}_{y2:.2f},{x1:.2f}_{y2:.2f}"
                    coordinate_lines.append(coord_line)
            if not coordinate_lines:
                return False
            message = "\n".join(coordinate_lines) + "\n"
            success = AssemblyDialog._heartbeat_manager.send_data(message)
            if success:
                print(f"✅ Sent {len(coordinate_lines)} coordinate sets via heartbeat")
                self.update_tcp_messages(f"📤 Sent {len(coordinate_lines)} coordinate sets")
                return True
            return False
        except Exception as e:
            print(f"❌ Error sending coordinates: {e}")
            return False

    def _convert_to_world_coordinates(self, pixel_corners):
        world_corners = []
        for corner in pixel_corners:
            world_point = self.calibration.pixel_to_world(corner)
            world_corners.append(world_point if world_point else corner)
        return world_corners

    def _on_prediction_failed(self, step_number, product_name, message, progress_dialog):
        if progress_dialog:
            try:
                progress_dialog.close(); progress_dialog.deleteLater()
            except:
                pass
        self.prediction_status_label.setText(f"STEP {step_number}: DETECTION FAILED")
        self.prediction_status_label.setStyleSheet(
            "font-size:12px;color:#FF3344;padding:6px 10px;background:#1A0508;"
            "border:1px solid #661020;border-radius:0px;min-width:150px;font-family:Consolas;")
        QMessageBox.warning(self, f"❌ Prediction Failed — Step {step_number}",
                            f"Failed to detect {product_name}:\n\n{message}")

    def show_prediction_results_view(self, step_number, product, predictions, output_path, captured_path):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Step {step_number}: {product['name']} — Detection Results")
        dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dialog.setMinimumSize(1100, 600)
        dialog.setModal(True)
        dialog.setStyleSheet("QDialog { background-color: #060C14; border: 1px solid #00AAFF44; } QLabel { color: #CCDDEE; background-color: transparent; }")

        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 12)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0A1828,stop:0.6 #060C14,stop:1 #050D18); border-bottom:2px solid #00AAFF;")
        hdr_row = QHBoxLayout(hdr); hdr_row.setContentsMargins(14, 0, 14, 0); hdr_row.setSpacing(12)
        hdr_badge = QLabel(f"STEP {step_number}")
        hdr_badge.setStyleSheet("font-size:11px;font-weight:900;color:#00AAFF;background:#030810;border:1px solid #00AAFF44;padding:3px 12px;letter-spacing:3px;font-family:Consolas;")
        if predictions:
            hdr_title = QLabel(f"✓  {len(predictions)} OBJECT(S) DETECTED — {product['name']}")
            hdr_title.setStyleSheet("font-size:18px;font-weight:900;color:#FFFFFF;letter-spacing:2px;font-family:Consolas;background:transparent;")
        else:
            hdr_title = QLabel(f"⚠  NO {product['name']} DETECTED")
            hdr_title.setStyleSheet("font-size:18px;font-weight:900;color:#FFFFFF;letter-spacing:2px;font-family:Consolas;background:transparent;")
        hdr_row.addWidget(hdr_badge); hdr_row.addWidget(hdr_title); hdr_row.addStretch()
        layout.addWidget(hdr)
        sep = QWidget(); sep.setFixedHeight(2); sep.setStyleSheet("background:#00AAFF;")
        layout.addWidget(sep)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #1A3A5C; width: 2px; }")

        # Left: reference
        left_widget = QWidget(); left_widget.setStyleSheet("background:#060C14;")
        left_layout = QVBoxLayout(left_widget); left_layout.setContentsMargins(8, 8, 8, 8)

        left_title = QLabel("REFERENCE PRODUCT")
        left_title.setStyleSheet(_panel_hdr("#00AAFF"))
        left_title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(left_title)

        ref_label = QLabel()
        ref_label.setAlignment(Qt.AlignCenter)
        ref_label.setMinimumSize(400, 350)
        ref_label.setStyleSheet("border:1px solid #1A3A5C;border-left:3px solid #00AAFF;border-radius:0px;background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #070F1C,stop:1 #030810);padding:6px;")
        try:
            pixmap = QPixmap(product['image_path'])
            if not pixmap.isNull():
                ref_label.setPixmap(pixmap.scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            ref_label.setText(f"❌ Cannot load reference\n{str(e)}")
        left_layout.addWidget(ref_label)

        product_info = QLabel(f"{product['filename']}")
        product_info.setStyleSheet("font-size:11px;color:#7AAAD4;padding:6px 10px;background:#050D18;border-radius:0px;font-family:Consolas;")
        product_info.setAlignment(Qt.AlignCenter); product_info.setWordWrap(True)
        left_layout.addWidget(product_info)
        left_layout.addStretch()

        # Right: detection
        right_widget = QWidget(); right_widget.setStyleSheet("background:#060C14;")
        right_layout = QVBoxLayout(right_widget); right_layout.setContentsMargins(8, 8, 8, 8)

        right_title = QLabel("AI DETECTION RESULT")
        right_title.setStyleSheet(_panel_hdr("#00AAFF"))
        right_title.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(right_title)

        cap_label = QLabel()
        cap_label.setAlignment(Qt.AlignCenter)
        cap_label.setMinimumSize(400, 350)
        cap_label.setStyleSheet("border:1px solid #1A3A5C;border-left:3px solid #00FF88;border-radius:0px;background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #041A10,stop:1 #030810);padding:6px;")

        display_path = output_path if (output_path and os.path.exists(output_path)) else captured_path
        if display_path and os.path.exists(display_path):
            try:
                pixmap = QPixmap(display_path)
                if not pixmap.isNull():
                    cap_label.setPixmap(pixmap.scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except:
                cap_label.setText("❌ Cannot load image")
        else:
            cap_label.setText("❌ No image available")
        right_layout.addWidget(cap_label)

        if predictions:
            class_counts = {}
            confidences = []
            for p in predictions:
                cn = p.get('class_name', 'unknown')
                class_counts[cn] = class_counts.get(cn, 0) + 1
                confidences.append(p.get('confidence', 0))
            avg_conf = sum(confidences) / len(confidences) * 100 if confidences else 0
            info_text = f"OBJECTS: {len(predictions)}  ·  AVG CONF: {avg_conf:.1f}%\n"
            for cn, count in class_counts.items():
                info_text += f"  {cn}: {count}\n"
        else:
            info_text = "NO OBJECTS DETECTED\nCheck lighting and camera angle."

        info_label = QLabel(info_text)
        info_label.setStyleSheet(
            "font-size:13px;padding:10px 14px;background:#050D18;"
            "border:1px solid #1A3A5C;border-left:3px solid #00AAFF44;"
            "border-radius:0px;margin-top:6px;font-family:Consolas;color:#AACCEE;")
        info_label.setAlignment(Qt.AlignLeft); info_label.setWordWrap(True)
        right_layout.addWidget(info_label)
        right_layout.addStretch()

        splitter.addWidget(left_widget); splitter.addWidget(right_widget)
        splitter.setSizes([500, 600])
        layout.addWidget(splitter, 1)

        button_layout = QHBoxLayout(); button_layout.setContentsMargins(12, 8, 12, 0)
        done_btn = QPushButton("▶  DONE")
        done_btn.setStyleSheet(_btn(_T["green"], _T["green_bg"], _T["green_bd"], "#052A18", 150))
        done_btn.clicked.connect(dialog.accept)
        button_layout.addStretch(); button_layout.addWidget(done_btn)
        layout.addLayout(button_layout)
        dialog.exec()

    def check_completion(self):
        all_selected = all(step in self.step_selections for step in range(1, self.total_steps + 1))
        self.ok_btn.setEnabled(all_selected)

    def get_current_recipe_info(self):
        try:
            if hasattr(config_manager, 'current_recipe'):
                recipe_id = config_manager.current_recipe
                recipe_name = getattr(config_manager, 'current_recipe_name', f'Recipe {recipe_id}')
                return f"{recipe_name} (ID: {recipe_id})"
        except:
            pass
        return "No recipe selected"

    def get_annotation_folder_path(self):
        recipe_path = self.get_current_recipe_path()
        if not recipe_path or not os.path.exists(recipe_path):
            return None
        annotation_path = os.path.join(recipe_path, "Annotation")
        if os.path.exists(annotation_path) and os.path.isdir(annotation_path):
            return annotation_path
        for item in os.listdir(recipe_path):
            item_path = os.path.join(recipe_path, item)
            if os.path.isdir(item_path) and "annotation" in item.lower():
                return item_path
        return None

    def load_bmp_from_annotation(self):
        try:
            self.available_products = []
            self.thumbnail_widgets = {}
            self.annotation_folder = self.get_annotation_folder_path()
            if not self.annotation_folder:
                QMessageBox.warning(self, "⚠️ Annotation Folder Not Found",
                                    "The 'Annotation' folder was not found in the current recipe.")
                self.update_gallery();
                return

            # Define supported image extensions
            image_extensions = ['*.bmp', '*.jpg', '*.jpeg', '*.png', '*.tiff', '*.tif', '*.webp']
            image_files = []

            for pattern in image_extensions:
                try:
                    # Search in root folder
                    image_files.extend(glob.glob(os.path.join(self.annotation_folder, pattern)))
                    # Search recursively in subfolders
                    image_files.extend(glob.glob(os.path.join(self.annotation_folder, "**", pattern), recursive=True))
                except:
                    pass

            # Remove duplicates and sort
            image_files = list(set(image_files))
            image_files.sort()

            if not image_files:
                self.update_gallery()
                return

            product_counter = {}
            for img_path in image_files:
                filename = os.path.basename(img_path)
                base_name = os.path.splitext(filename)[0]
                product_name = self.clean_product_name(base_name)
                product_counter[product_name] = product_counter.get(product_name, 0) + 1
                product_id = f"{product_name}_{product_counter[product_name]}" if product_counter[
                                                                                      product_name] > 1 else product_name
                try:
                    rel_path = os.path.relpath(img_path, self.annotation_folder)
                except:
                    rel_path = filename
                self.available_products.append({
                    'id': product_id, 'name': base_name, 'image_path': img_path,
                    'filename': filename, 'relative_path': rel_path, 'original_name': base_name})
            self.update_gallery()
        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Failed to load annotation images: {str(e)}")

    def clean_product_name(self, filename):
        suffixes = ['_annotated', '_annotation', '_labeled', '_label', '_mask', '_bbox',
                    '_cropped', '_resized', '_processed', '_train', '_val', '_test']
        name = filename
        for suffix in suffixes:
            if name.lower().endswith(suffix.lower()):
                name = name[:-len(suffix)]; break
        name = re.sub(r'^\d+_', '', name)
        return name

    def get_current_recipe_path(self):
        try:
            if hasattr(config_manager, 'get_current_recipe_folder'):
                return config_manager.get_current_recipe_folder()
        except:
            pass
        try:
            if hasattr(config_manager, 'current_recipe'):
                recipe_id = config_manager.current_recipe
                return os.path.join("recipes", str(recipe_id))
        except:
            pass
        return None

    def get_model_path(self, product_id):
        try:
            if hasattr(config_manager, 'get_current_yolo_models_folder'):
                models_folder = config_manager.get_current_yolo_models_folder()
                return os.path.join(models_folder, f"{product_id}.pt")
        except:
            return ""

    def is_model_trained(self, product_id):
        model_path = self.get_model_path(product_id)
        return os.path.exists(model_path) if model_path else False

    def get_all_selections(self):
        try:
            result = {
                'block_id': str(self.block_id), 'block_name': str(self.block_name),
                'total_steps': int(self.total_steps),
                'uploaded_video_path': str(self.uploaded_video_path) if self.uploaded_video_path else '',
                'selections': {}
            }
            for step, selection in self.step_selections.items():
                step_key = str(step)
                capture_info = {}
                if step in self.step_widgets:
                    capture_info = {
                        'capture_count': int(self.step_widgets[step].get('capture_counter', 0)),
                        'capture_folder': str(self.step_widgets[step].get('capture_folder', '')),
                        'assembly_folder': str(self.assembly_folder) if self.assembly_folder else '',
                        'block_id': str(self.block_id), 'block_name': str(self.block_name),
                        'current_image': str(self.step_widgets[step].get('current_image', '')) if self.step_widgets[step].get('current_image') else ''
                    }
                product_data = selection.get('product_data', {})
                result['selections'][step_key] = {
                    'product_id': str(selection.get('product_id', '')),
                    'product_data': {
                        'name': str(product_data.get('name', '')),
                        'original_name': str(product_data.get('original_name', '')),
                        'image_path': str(product_data.get('image_path', '')),
                        'filename': str(product_data.get('filename', '')),
                        'annotation_path': str(product_data.get('annotation_path', '')),
                        'model_path': str(product_data.get('model_path', '')),
                        'trained': bool(product_data.get('trained', False))
                    },
                    'capture_info': capture_info
                }
            return result
        except Exception as e:
            print(f"❌ ERROR in get_all_selections: {e}")
            return {'block_id': str(self.block_id), 'block_name': str(self.block_name),
                    'total_steps': int(self.total_steps), 'selections': {}, 'error': str(e)}

    def validate_and_accept(self):
        for step in range(1, self.total_steps + 1):
            if step not in self.step_selections:
                QMessageBox.warning(self, "⚠️ Missing Selection", f"Please select a product for Step {step}")
                self.set_active_step(step)
                return
        if not self.step_selections:
            QMessageBox.warning(self, "⚠️ No Selections", "No steps have been configured.")
            return
        final_config = self.get_all_selections()
        if not isinstance(final_config, dict):
            QMessageBox.warning(self, "⚠️ Save Failed", "Assembly configuration is invalid.")
            return
        self.config_data = final_config
        self.assembly_data = final_config
        super().accept()

    def get_config(self):
        if hasattr(self, "assembly_data") and isinstance(self.assembly_data, dict):
            return self.assembly_data
        return self.get_all_selections()

    def closeEvent(self, event):
        if self.capture_worker and self.capture_worker.isRunning():
            self.capture_worker.stop(); self.capture_worker.quit(); self.capture_worker.wait()
        if self.is_predicting:
            self.cancel_prediction()
        if self.assembly_tool_window and self.assembly_tool_window.isVisible():
            self.assembly_tool_window.close()
        self.disconnect_tcp()
        event.accept()

    def disconnect_tcp(self):
        if hasattr(AssemblyDialog, '_global_tcp_socket') and AssemblyDialog._global_tcp_socket:
            try:
                AssemblyDialog._global_tcp_socket.close()
            except:
                pass
            AssemblyDialog._global_tcp_socket = None
        self.tcp_socket = None
        self.tcp_connected = False
        self.update_tcp_messages("🔌 TCP disconnected by user")

    def cancel_prediction(self):
        if hasattr(self, 'prediction_manager'):
            self.prediction_manager.cancel_prediction()
        self.is_predicting = False

    @property
    def selected_step(self):
        return self.current_active_step

    @property
    def selected_product(self):
        if 1 in self.step_selections:
            return self.step_selections[1]['product_id']
        return None

    @property
    def product_data(self):
        if 1 in self.step_selections:
            return self.step_selections[1]['product_data']
        return {}


class ScrewDialog(QDialog):
    def __init__(self, parent=None, block_id=None, block_name=None, initial_config=None):
        super().__init__(parent)
        self.parent_dialog = parent
        self.block_id = block_id or "1"
        self.block_name = block_name or f"Block_{self.block_id}"
        self.assembly_tool_window = None
        self.config_data = None
        self.uploaded_video_path = None

        self.setWindowTitle("Screw Configuration")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.showFullScreen()
        self.setStyleSheet("""
            QDialog { background-color: #060C14; }
            QLabel { color: #CCDDEE; background-color: transparent; }
            QSpinBox, QComboBox, QLineEdit {
                font-size:20px; padding:12px 16px;
                background:#050D18; color:#FFFFFF;
                border:1px solid #1A3A5C; border-bottom:3px solid #0E2A40;
                border-radius:3px; font-family:Consolas;
                selection-background-color:#003A6A;
            }
            QSpinBox:focus, QComboBox:focus, QLineEdit:focus {
                border:1px solid #00AAFF55;
                border-bottom:3px solid #00AAFF;
            }
            QComboBox::drop-down { border:none; width:32px; }
            QComboBox::down-arrow { width:12px; height:12px; }
            QComboBox QAbstractItemView {
                background:#050D18; color:#FFFFFF;
                border:1px solid #1A3A5C; selection-background-color:#003A6A;
                font-family:Consolas; font-size:18px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ══ HEADER ════════════════════════════════════════════════════════
        hdr = QWidget()
        hdr.setFixedHeight(72)
        hdr.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #071220,stop:0.5 #060C14,stop:1 #050A12);"
            "border-bottom:2px solid #00AAFF;")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(24, 0, 24, 0); hdr_row.setSpacing(16)
        sys_badge = QLabel("HMI")
        sys_badge.setStyleSheet(
            "font-size:11px;font-weight:900;color:#00AAFF55;"
            "background:#030810;border:1px solid #00AAFF22;"
            "padding:4px 10px;letter-spacing:4px;font-family:Consolas;")
        hdr_title = QLabel(f"SCREW CONFIGURATION  ·  BLOCK {self.block_id}")
        hdr_title.setStyleSheet(
            "font-size:20px;font-weight:900;color:#FFFFFF;"
            "letter-spacing:3px;font-family:Consolas;background:transparent;")
        hdr_row.addWidget(sys_badge); hdr_row.addWidget(hdr_title); hdr_row.addStretch()
        layout.addWidget(hdr)

        # ══ BODY: 2-column data grid + tools ══════════════════════════════
        body = QWidget()
        body.setStyleSheet("background:#060C14;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(40, 40, 40, 20)
        body_layout.setSpacing(24)

        # ── Data grid label ───────────────────────────────────────────────
        cfg_lbl = QLabel("SCREW PARAMETERS")
        cfg_lbl.setStyleSheet(
            "font-size:12px;font-weight:900;color:#2A5A8A;"
            "letter-spacing:5px;font-family:Consolas;"
            "border-bottom:1px solid #0E2A40;padding-bottom:8px;background:transparent;")
        body_layout.addWidget(cfg_lbl)

        # ── 2×2 parameter grid ────────────────────────────────────────────
        param_grid = QGridLayout()
        param_grid.setSpacing(16)
        param_grid.setContentsMargins(0, 0, 0, 0)

        def _field(label_text, widget):
            wrap = QWidget()
            wrap.setStyleSheet("background:transparent;")
            wl = QVBoxLayout(wrap); wl.setContentsMargins(0,0,0,0); wl.setSpacing(6)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                "font-size:13px;font-weight:900;color:#2A5A8A;"
                "letter-spacing:3px;font-family:Consolas;background:transparent;")
            wl.addWidget(lbl); wl.addWidget(widget)
            return wrap

        self.screw_spinbox = QSpinBox()
        self.screw_spinbox.setRange(1, 50); self.screw_spinbox.setValue(4)
        self.screw_spinbox.setFixedHeight(64)

        self.screw_type_combo = QComboBox()
        self.screw_type_combo.addItems(["M3", "M4", "M5", "M6", "M8", "M10", "Custom"])
        self.screw_type_combo.setCurrentText("M4")
        self.screw_type_combo.setFixedHeight(64)

        self.screw_length_input = QLineEdit()
        self.screw_length_input.setPlaceholderText("e.g. 20.5")
        self.screw_length_input.setText("20")
        self.screw_length_input.setFixedHeight(64)

        self.torque_spinbox = QSpinBox()
        self.torque_spinbox.setRange(1, 100); self.torque_spinbox.setValue(10)
        self.torque_spinbox.setSuffix(" N·m"); self.torque_spinbox.setFixedHeight(64)

        param_grid.addWidget(_field("SCREW COUNT (pcs)", self.screw_spinbox),    0, 0)
        param_grid.addWidget(_field("SCREW TYPE",         self.screw_type_combo), 0, 1)
        param_grid.addWidget(_field("SCREW LENGTH (mm)",  self.screw_length_input),1, 0)
        param_grid.addWidget(_field("TORQUE",             self.torque_spinbox),   1, 1)

        body_layout.addLayout(param_grid)

        # ── Tool button section ───────────────────────────────────────────
        tools_lbl = QLabel("ACTIONS")
        tools_lbl.setStyleSheet(
            "font-size:12px;font-weight:900;color:#2A5A8A;"
            "letter-spacing:5px;font-family:Consolas;"
            "border-bottom:1px solid #0E2A40;padding-bottom:8px;background:transparent;")
        body_layout.addWidget(tools_lbl)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(12)
        tools_row.setContentsMargins(0, 0, 0, 0)

        def _tool_btn_3d(label, min_w=220):
            b = QPushButton(label)
            b.setFixedHeight(66)
            b.setStyleSheet(
                f"QPushButton{{font-size:18px;font-weight:900;"
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 #0A3020,stop:0.45 #052818,stop:1 #020C08);"
                f"color:#00FF88;"
                f"border:1px solid #00FF8833;border-top:1px solid #00FF8866;"
                f"border-bottom:4px solid #010804;border-radius:3px;"
                f"min-width:{min_w}px;font-family:Consolas;letter-spacing:2px;padding:12px 24px;}}"
                f"QPushButton:hover{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 #0F4030,stop:0.45 #073020,stop:1 #020C08);"
                f"border-top:1px solid #00FF88;border-bottom:4px solid #010804;color:#FFFFFF;}}"
                f"QPushButton:pressed{{background:#021008;border-bottom:1px solid #010804;padding-top:15px;}}")
            return b

        self.screw_location_btn = _tool_btn_3d("⬡  SCREW LOCATION", 220)
        self.screw_location_btn.clicked.connect(self.open_assembly_tool)
        tools_row.addWidget(self.screw_location_btn)

        # vertical divider
        vdiv = QFrame(); vdiv.setFrameShape(QFrame.VLine)
        vdiv.setStyleSheet("color:#1A3A5C;background:#1A3A5C;max-width:1px;")
        tools_row.addWidget(vdiv)

        self.screw_location_2_btn = _tool_btn_3d("⬡  ASSEMBLY SCREW LOCATION", 280)
        self.screw_location_2_btn.clicked.connect(self.open_assembly_tool_2)
        tools_row.addWidget(self.screw_location_2_btn)

        vdiv2 = QFrame(); vdiv2.setFrameShape(QFrame.VLine)
        vdiv2.setStyleSheet("color:#1A3A5C;background:#1A3A5C;max-width:1px;")
        tools_row.addWidget(vdiv2)

        self.upload_video_btn = _tool_btn_3d("▶  UPLOAD VIDEO", 200)
        self.upload_video_btn.clicked.connect(self.upload_video)
        tools_row.addWidget(self.upload_video_btn)

        tools_row.addStretch()
        body_layout.addLayout(tools_row)
        body_layout.addStretch()
        layout.addWidget(body, 1)

        # ══ FOOTER ════════════════════════════════════════════════════════
        footer = QWidget()
        footer.setFixedHeight(96)
        footer.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #0A1828,stop:1 #060C14);"
            "border-top:2px solid #00AAFF33;")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(24, 16, 24, 16); footer_row.setSpacing(12)

        ok_btn = QPushButton("✓  SAVE CONFIGURATION")
        ok_btn.setFixedHeight(62)
        ok_btn.setStyleSheet(
            "QPushButton{font-size:20px;font-weight:900;"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #0A3020,stop:0.45 #052818,stop:1 #020C08);"
            "color:#00FF88;border:1px solid #00FF8833;"
            "border-top:1px solid #00FF8866;border-bottom:4px solid #010804;"
            "border-radius:3px;min-width:280px;"
            "font-family:Consolas;letter-spacing:3px;padding:10px 24px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #0F4030,stop:0.45 #073020,stop:1 #020C08);"
            "border-top:1px solid #00FF88;border-bottom:4px solid #010804;color:#FFFFFF;}"
            "QPushButton:pressed{background:#021008;border-bottom:1px solid #010804;padding-top:13px;}")

        cancel_btn = QPushButton("✕  CANCEL")
        cancel_btn.setFixedHeight(62)
        cancel_btn.setStyleSheet(
            "QPushButton{font-size:20px;font-weight:900;"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #3A0A10,stop:0.45 #220810,stop:1 #0C0204);"
            "color:#FF3344;border:1px solid #FF334433;"
            "border-top:1px solid #FF334488;border-bottom:4px solid #050104;"
            "border-radius:3px;min-width:160px;"
            "font-family:Consolas;letter-spacing:2px;padding:10px 24px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #4A1020,stop:0.45 #2A1018,stop:1 #0C0204);"
            "border-top:1px solid #FF3344;border-bottom:4px solid #050104;color:#FFFFFF;}"
            "QPushButton:pressed{background:#150408;border-bottom:1px solid #050104;padding-top:13px;}")

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        footer_row.addStretch()
        footer_row.addWidget(ok_btn)
        footer_row.addWidget(cancel_btn)
        layout.addWidget(footer)

        if initial_config and isinstance(initial_config, dict):
            self.load_initial_config(initial_config)

    def load_initial_config(self, config):
        self.screw_spinbox.setValue(int(config.get("count", 4)))
        self.screw_type_combo.setCurrentText(str(config.get("type", "M4")))
        self.screw_length_input.setText(str(config.get("length", "20")))  # Add this line
        self.torque_spinbox.setValue(int(config.get("torque", 10)))
        self.uploaded_video_path = config.get("uploaded_video_path", "")

    def get_config(self):
        # Validate and convert length input
        try:
            length_value = float(self.screw_length_input.text()) if self.screw_length_input.text() else 0
        except ValueError:
            length_value = 0
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid number for screw length.")

        return {
            "block_type": "screw",
            "block_id": str(self.block_id),
            "block_name": str(self.block_name),
            "count": int(self.screw_spinbox.value()),
            "type": str(self.screw_type_combo.currentText()),
            "length": length_value,  # Add this line
            "torque": int(self.torque_spinbox.value()),
            "position": f"ScrewBoxesData/Block_{self.block_id}",
            "position2": f"ScrewBoxesData2/Block_{self.block_id}",
            "uploaded_video_path": str(self.uploaded_video_path) if self.uploaded_video_path else ""
        }

    def accept(self):
        self.config_data = self.get_config()
        super().accept()

    def ensure_video_folder(self):
        recipe_path = None
        try:
            if hasattr(config_manager, 'get_current_recipe_folder'):
                recipe_path = config_manager.get_current_recipe_folder()
        except:
            pass
        if not recipe_path:
            try:
                if hasattr(config_manager, 'current_recipe'):
                    recipe_path = os.path.join("recipes", str(config_manager.current_recipe))
            except:
                pass
        if not recipe_path:
            return None
        video_folder = os.path.join(recipe_path, "Screw", f"Block_{self.block_id}", "uploaded_videos")
        os.makedirs(video_folder, exist_ok=True)
        return video_folder

    def upload_video(self):
        try:
            video_folder = self.ensure_video_folder()
            if not video_folder:
                QMessageBox.warning(self, "⚠️ No Recipe", "Current recipe not found.")
                return
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", "",
                "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.mpeg *.mpg);;All Files (*.*)")
            if not file_path or not os.path.exists(file_path):
                return
            ext = os.path.splitext(file_path)[1]
            recipe_name = "unknown_recipe"
            try:
                if hasattr(config_manager, 'current_recipe_name') and config_manager.current_recipe_name:
                    recipe_name = str(config_manager.current_recipe_name)
                elif hasattr(config_manager, 'current_recipe') and config_manager.current_recipe:
                    recipe_name = str(config_manager.current_recipe)
            except:
                pass
            safe_recipe_name = re.sub(r'[^\w\-\.]', '_', str(recipe_name))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = os.path.join(video_folder, f"{safe_recipe_name}_Screw_Block_{self.block_id}_{timestamp}{ext}")
            shutil.copy2(file_path, target_path)
            self.uploaded_video_path = target_path
            QMessageBox.information(self, "✅ Video Uploaded", f"Video uploaded successfully.\n\nSaved to:\n{target_path}")
        except Exception as e:
            QMessageBox.critical(self, "❌ Upload Failed", f"Failed to upload video:\n\n{str(e)}")

    def open_assembly_tool(self):
        self._open_tool(mode="screw")

    def open_assembly_tool_2(self):
        self._open_tool(mode="screw2")

    def _open_tool(self, mode):
        try:
            from ui.components.assembly_laser import MainWindow as AssemblyLaserMainWindow
            if self.assembly_tool_window:
                try:
                    self.assembly_tool_window.close()
                except:
                    pass
                self.assembly_tool_window = None
            self.assembly_tool_window = AssemblyLaserMainWindow(
                block_id=str(self.block_id), block_name=str(self.block_name), mode=mode)
            self.assembly_tool_window.setParent(None)
            self.assembly_tool_window.setWindowFlags(
                Qt.Window | Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint |
                Qt.WindowTitleHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
            self.assembly_tool_window.setWindowModality(Qt.NonModal)
            self.assembly_tool_window.setAttribute(Qt.WA_DeleteOnClose)
            self.assembly_tool_window.destroyed.connect(self._on_assembly_tool_closed)
            self.assembly_tool_window.show()
            self.assembly_tool_window.raise_()
            self.assembly_tool_window.activateWindow()
            self.hide()
        except Exception as e:
            import traceback; traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to open tool:\n\n{str(e)}")

    def _on_assembly_tool_closed(self):
        self.assembly_tool_window = None
        self.show(); self.raise_(); self.activateWindow()


class ConfigurationOptionsDialog(QDialog):
    VIEW = 1
    EDIT = 2
    CANCEL = 3

    def __init__(self, block_name, current_config, assembly_data=None, parent=None):
        super().__init__(parent)
        self.block_name = block_name
        self.current_config = current_config
        self.assembly_data = assembly_data
        self.result = self.CANCEL

        self.setWindowTitle(f"{block_name} Configuration")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet("QDialog { background-color: #060C14; border: 1px solid #00AAFF55; } QLabel { color: #CCDDEE; background-color: transparent; }")
        self.setFixedSize(520, 440)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0A1828,stop:0.6 #060C14,stop:1 #050D18); border-bottom:2px solid #00AAFF;")
        hdr_row = QHBoxLayout(hdr); hdr_row.setContentsMargins(14, 0, 14, 0); hdr_row.setSpacing(12)
        hdr_badge = QLabel("CONFIG")
        hdr_badge.setStyleSheet("font-size:11px;font-weight:900;color:#00AAFF;background:#030810;border:1px solid #00AAFF44;padding:3px 12px;letter-spacing:3px;font-family:Consolas;")
        hdr_title = QLabel(f"{self.block_name} Configuration Options")
        hdr_title.setStyleSheet("font-size:16px;font-weight:900;color:#FFFFFF;letter-spacing:2px;font-family:Consolas;background:transparent;")
        hdr_row.addWidget(hdr_badge); hdr_row.addWidget(hdr_title); hdr_row.addStretch()
        layout.addWidget(hdr)
        sep = QWidget(); sep.setFixedHeight(2); sep.setStyleSheet("background:#00AAFF;")
        layout.addWidget(sep)

        # ── Body ──────────────────────────────────────────────────────────
        body = QWidget(); body.setStyleSheet("background:#060C14;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(10)

        # Preview label
        preview_lbl = QLabel("CURRENT CONFIGURATION")
        preview_lbl.setStyleSheet("font-size:11px;font-weight:900;color:#2A5A7A;letter-spacing:3px;font-family:Consolas;padding-bottom:4px;border-bottom:1px solid #0E2A40;")
        body_layout.addWidget(preview_lbl)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(140)
        self.preview_text.setStyleSheet(
            "background:#050D18;border:1px solid #1A3A5C;border-left:3px solid #00AAFF44;"
            "border-radius:0px;padding:8px;color:#AACCEE;font-family:Consolas;font-size:12px;")

        if self.block_name == "Assembly" and self.assembly_data:
            preview_text = self.format_assembly_preview()
        else:
            preview_text = self.current_config
        self.preview_text.setPlainText(preview_text)
        body_layout.addWidget(self.preview_text)

        # Warning
        info_label = QLabel("⚠  Changing configuration may affect your workflow.")
        info_label.setStyleSheet(
            "color:#FFAA00;font-size:12px;padding:8px 12px;background:#1A1000;"
            "border:1px solid #553300;border-left:3px solid #FFAA00;border-radius:2px;margin:4px 0;font-family:Consolas;")
        info_label.setWordWrap(True)
        body_layout.addWidget(info_label)

        # Buttons
        view_btn = QPushButton("◉  VIEW CONFIGURATION")
        view_btn.setToolTip("View current configuration details")
        view_btn.setStyleSheet(_btn(_T["cyan"], "#050D18", "#1A5080", "#071828", 220))
        view_btn.clicked.connect(lambda: self.accept_with_result(self.VIEW))

        edit_btn = QPushButton("✎  EDIT CONFIGURATION")
        edit_btn.setToolTip("Modify current configuration")
        edit_btn.setStyleSheet(_btn(_T["green"], _T["green_bg"], _T["green_bd"], "#052A18", 220))
        edit_btn.clicked.connect(lambda: self.accept_with_result(self.EDIT))

        cancel_btn = QPushButton("✕  CANCEL")
        cancel_btn.setStyleSheet("QPushButton{font-size:22px;font-weight:900;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3A0A10,stop:0.45 #220810,stop:1 #0C0204);color:#FF3344;border:1px solid #FF334433;border-top:1px solid #FF334488;border-bottom:4px solid #050104;border-radius:3px;font-family:Consolas;letter-spacing:2px;padding:10px 20px;}QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4A1020,stop:0.45 #2A1018,stop:1 #0C0204);border-top:1px solid #FF3344;border-bottom:4px solid #050104;color:#FFFFFF;}QPushButton:pressed{background:#150408;border-bottom:1px solid #050104;padding-top:13px;}min-width:220px;")
        cancel_btn.clicked.connect(self.reject)

        body_layout.addWidget(view_btn)
        body_layout.addWidget(edit_btn)
        body_layout.addWidget(cancel_btn)
        layout.addWidget(body, 1)

    def format_assembly_preview(self):
        if not self.assembly_data:
            return self.current_config
        lines = [f"TOTAL STEPS: {self.assembly_data['total_steps']}", ""]
        for step, selection in self.assembly_data['selections'].items():
            product_data = selection.get('product_data', {})
            trained = "✓" if product_data.get('trained') else "✗"
            lines.append(f"STEP {step}: {product_data.get('name', selection.get('product_id', '?'))} [{trained}]")
        return "\n".join(lines)

    def find_edit_flow_page(self):
        obj = self.parent()
        while obj:
            if hasattr(obj, "pipeline_blocks") and hasattr(obj, "save_flow"):
                return obj
            obj = obj.parent()
        return None

    def configure_assembly_block(self, assembly_block):
        dialog = AssemblyDialog(
            parent=self,
            initial_config=assembly_block.assembly_data if hasattr(assembly_block, "assembly_data") else None,
            block_id=str(assembly_block.block_id),
            block_name=f"Block_{assembly_block.block_id}")
        if dialog.exec() == QDialog.Accepted:
            new_config = None
            if hasattr(dialog, "config_data") and isinstance(dialog.config_data, dict):
                new_config = dialog.config_data
            elif hasattr(dialog, "assembly_data") and isinstance(dialog.assembly_data, dict):
                new_config = dialog.assembly_data
            else:
                new_config = dialog.get_all_selections()
            if isinstance(new_config, dict):
                assembly_block.assembly_data = new_config
                assembly_block.config = new_config
                total_steps = new_config.get("total_steps", 0)
                assembly_block.text.setPlainText(
                    f"Assembly (Block {assembly_block.block_id}, {total_steps} steps)"
                    if total_steps > 0 else f"Assembly (Block {assembly_block.block_id})")
                self.save_flow()
                self.update_assembly_block_displays()

    def edit_configuration(self, block_id, current_config):
        try:
            if self.block_name == "Screw":
                screw_dialog = ScrewDialog(parent=self, block_id=block_id,
                    block_name=f"Block_{block_id}",
                    initial_config=current_config if isinstance(current_config, dict) else None)
                if screw_dialog.exec() == QDialog.Accepted:
                    new_config = screw_dialog.get_config()
                    self.save_configuration(block_id, new_config)
                return True

            assembly_data = current_config if isinstance(current_config, dict) and 'selections' in current_config else {'total_steps': 1, 'selections': {}}
            self.assembly_dialog = AssemblyDialog(parent=self, initial_config=assembly_data,
                block_id=block_id, block_name=f"Block_{block_id}")
            self.assembly_dialog.setParent(None)
            self.assembly_dialog.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint |
                                                 Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
            self.assembly_dialog.setWindowModality(Qt.NonModal)
            self.assembly_dialog.setModal(False)
            self.assembly_dialog.finished.connect(lambda result: self.on_assembly_dialog_finished(result, block_id))
            self.assembly_dialog.show(); self.assembly_dialog.raise_(); self.assembly_dialog.activateWindow()
            return True
        except Exception as e:
            print(f"❌ ERROR in edit_configuration: {e}")
            import traceback; traceback.print_exc()
            return False

    def save_configuration(self, block_id, new_config):
        print(f"DEBUG: save_configuration called for block_id={block_id}")
        page = self.find_edit_flow_page()
        if not page:
            QMessageBox.warning(self, "Save Failed", "Could not find Edit Flow page.")
            return False
        target_block = None
        for block in page.pipeline_blocks:
            if hasattr(block, "block_id") and str(block.block_id) == str(block_id):
                if self.block_name == "Assembly" and block.name == "Assembly":
                    target_block = block; break
                elif self.block_name == "Screw" and block.name == "Screw":
                    target_block = block; break
        if not target_block:
            QMessageBox.warning(self, "Save Failed", f"Block {block_id} not found.")
            return False
        if target_block.name == "Assembly":
            target_block.assembly_data = new_config
            target_block.config = new_config
            total_steps = new_config.get("total_steps", 0)
            if hasattr(target_block, "text"):
                target_block.text.setPlainText(
                    f"Assembly (Block {target_block.block_id}, {total_steps} steps)"
                    if total_steps > 0 else f"Assembly (Block {target_block.block_id})")
        elif target_block.name == "Screw":
            target_block.config = new_config
            screw_count = new_config.get("count", "")
            screw_type = new_config.get("type", "")
            if hasattr(target_block, "text"):
                target_block.text.setPlainText(
                    f"Screw (Block {target_block.block_id}, {screw_count}x {screw_type})"
                    if screw_count and screw_type else f"Screw (Block {target_block.block_id})")
        if hasattr(page, "update_assembly_block_displays"):
            page.update_assembly_block_displays()
        page.scene.update(); page.view.viewport().update()
        try:
            page.save_flow()
            return True
        except Exception as e:
            QMessageBox.warning(self, "Save Failed", f"Failed to save pipeline flow:\n{str(e)}")
            return False

    def on_assembly_dialog_finished(self, result, block_id):
        if result == QDialog.Accepted:
            new_config = None
            if hasattr(self.assembly_dialog, "config_data") and isinstance(self.assembly_dialog.config_data, dict):
                new_config = self.assembly_dialog.config_data
            elif hasattr(self.assembly_dialog, "assembly_data") and isinstance(self.assembly_dialog.assembly_data, dict):
                new_config = self.assembly_dialog.assembly_data
            else:
                new_config = self.assembly_dialog.get_all_selections()
            if isinstance(new_config, dict):
                self.save_configuration(block_id, new_config)
        self.assembly_dialog = None

    def accept_with_result(self, result):
        self.result = result
        super().accept()

    @staticmethod
    def get_action(block_name, current_config, assembly_data=None, parent=None):
        dialog = ConfigurationOptionsDialog(block_name=block_name, current_config=current_config,
                                             assembly_data=assembly_data, parent=parent)
        dialog.exec()
        return dialog.result