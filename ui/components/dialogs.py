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
import socket  # ADDED for TCP
import re

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QFormLayout, QSpinBox,
    QGroupBox, QGridLayout, QScrollArea, QWidget, QDialogButtonBox, QMessageBox, QFrame, QTextEdit,
    QFileDialog, QProgressDialog, QSplitter
)
from PySide6.QtCore import Signal, Qt, QTimer, QThread
from config_manager import config_manager
from ui.components.prediction_manager import PredictionManager
from ui.components.heartbeat_manager import HeartbeatManager

CAMERA_AVAILABLE = False
camera_module = None

try:
    # Import the module once and store reference
    from camera.camera import AutoCaptureFlow

    CAMERA_AVAILABLE = True
    camera_module = AutoCaptureFlow
except ImportError as e:
    # Only show warning once
    import traceback

    print(f"Camera module import failed: {e}")
    print("Camera functionality will be disabled.")
except Exception as e:
    print(f"Error loading camera module: {e}")
    print("Camera functionality will be disabled.")


class Calibration:
    """Handles camera calibration data and transformations"""

    def __init__(self):
        self.pixel_points = []  # List of (x, y) pixel coordinates
        self.world_points = []  # List of (x, y) world coordinates
        self.calibration_matrix = None
        self.is_calibrated = False
        self.calibration_file = None

    def load_calibration(self, filepath):
        """Load calibration data from JSON file"""
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
        """Convert pixel coordinates to world coordinates"""
        if not self.is_calibrated or self.calibration_matrix is None:
            return None

        try:
            # Convert single point
            pixel_array = np.array([[pixel_point[0], pixel_point[1]]], dtype=np.float32)
            world_array = cv2.perspectiveTransform(pixel_array.reshape(-1, 1, 2),
                                                   self.calibration_matrix)
            world_point = world_array[0][0]
            return (float(world_point[0]), float(world_point[1]))
        except Exception as e:
            print(f"Conversion error: {e}")
            return None


class CaptureWorker(QThread):
    """Worker thread for camera capture"""
    finished = Signal(bool, str, str)  # success, message, image_path

    def __init__(self, block_folder, step_number, product_name, filename, save_image=True):
        super().__init__()
        self.block_folder = block_folder
        self.step_number = step_number
        self.product_name = product_name
        self.filename = filename
        self.save_image = save_image  # NEW: flag to control saving
        self.is_running = True

    def run(self):
        """Run camera capture"""
        try:
            def capture_callback(success, message, image_path):
                if success and image_path:
                    if self.save_image:
                        # SAVE permanently (for manual capture button)
                        save_path = os.path.join(self.block_folder, self.filename)
                        try:
                            shutil.copy2(image_path, save_path)
                            if os.path.exists(image_path):
                                os.remove(image_path)
                            self.finished.emit(True, f"Image captured successfully", save_path)
                        except Exception as e:
                            self.finished.emit(False, f"Failed to save image: {str(e)}", None)
                    else:
                        # DON'T save - use temp file (for auto-capture)
                        # Just pass the original temp path - it will be cleaned up later
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

    # Add class-level heartbeat manager (shared across instances)
    _heartbeat_manager = None
    _heartbeat_reference_count = 0

    def __init__(self, parent=None, initial_config=None, block_id=None, block_name=None):
        super().__init__(parent)
        print(f"🟪 AssemblyDialog __init__ - parent: {parent}")
        print(f"🟪 Initial modal state: {self.isModal()}")
        print(f"🟪 Initial window flags: {self.windowFlags()}")
        self.block_id = block_id or "1"  # Default to "1"
        self.block_name = block_name or f"Block_{self.block_id}"  # ADD THIS LINE
        self.prediction_success.connect(self._on_prediction_success)
        self.prediction_failed.connect(self._on_prediction_failed)

        # ===== HEARTBEAT MANAGER (shared) =====
        self._init_heartbeat_manager()

        if initial_config and 'block_id' in initial_config:
            self.block_id = initial_config['block_id']
            # Also get block_name from config if available
            if 'block_name' in initial_config:
                self.block_name = initial_config['block_name']
            else:
                self.block_name = f"Block_{self.block_id}"

        # Initialize attributes
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
        self.initial_config = initial_config or {}  # Store initial config
        self.assembly_tool_window = None  # Add this for Assembly Tool window

        # Prediction related
        self.prediction_manager = PredictionManager()  # Add this
        self.is_predicting = False  # Add this

        # ===== TCP CONNECTION ATTRIBUTES =====
        self.tcp_socket = None
        self.tcp_connected = False
        self.tcp_connection_attempted = False  # Track if we've tried to connect

        # ===== CALIBRATION ATTRIBUTES =====
        self.calibration = Calibration()
        self.calibration_path = "C:\\Users\\PC_AI_DS\\Pictures\\LaserCalibration\\calibration.json"

        # Auto-load calibration if file exists
        if os.path.exists(self.calibration_path):
            success, message = self.calibration.load_calibration(self.calibration_path)
            if success:
                print(f"✅ Calibration loaded from: {self.calibration_path}")
            else:
                print(f"⚠️ Failed to load calibration: {message}")
        else:
            print(f"⚠️ Calibration file not found at: {self.calibration_path}")

        # Set window properties
        self.setWindowTitle("Assembly Configuration")
        self.setMinimumSize(1400, 800)  # Increase size for prediction UI

        # Initialize UI
        self.init_ui()

        # Load initial configuration if provided
        if self.initial_config:
            QTimer.singleShot(100, self.load_initial_configuration)

        if self.block_name:
            self.setWindowTitle(f"Assembly Configuration - {self.block_name}")
        else:
            self.setWindowTitle("Assembly Configuration")


    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header with current recipe info
        recipe_info = self.get_current_recipe_info()
        header = QLabel(f"📁 Assembly Configuration - {recipe_info}")
        header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # ========== PREDICTION TOOLBAR ==========
        prediction_toolbar = QGroupBox("Assembly Result")
        prediction_toolbar.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #9b59b6;
                border-radius: 8px;
                padding-top: 15px;
                margin-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #8e44ad;
            }
        """)

        toolbar_layout = QHBoxLayout(prediction_toolbar)
        toolbar_layout.setSpacing(10)

        # ===== ASSEMBLY LOCATION BUTTON =====
        self.assembly_tool_btn = QPushButton("🛠️ Assembly Location")
        self.assembly_tool_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px 12px;
                background-color: #FF9800;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.assembly_tool_btn.clicked.connect(self.open_assembly_tool)
        self.assembly_tool_btn.setToolTip("Open Assembly Annotation Tool for bounding box labeling")
        toolbar_layout.addWidget(self.assembly_tool_btn)

        # # Load Model button
        # self.load_model_btn = QPushButton("🤖 Load Model")
        # self.load_model_btn.setStyleSheet("""
        #     QPushButton {
        #         font-size: 12px;
        #         padding: 8px 12px;
        #         background-color: #3498db;
        #         color: white;
        #         border-radius: 4px;
        #         min-width: 120px;
        #     }
        #     QPushButton:hover {
        #         background-color: #2980b9;
        #     }
        #     QPushButton:disabled {
        #         background-color: #bdc3c7;
        #         color: #7f8c8d;
        #     }
        # """)
        # self.load_model_btn.clicked.connect(self.load_model_for_prediction)
        # self.load_model_btn.setToolTip("Load trained YOLO model for prediction")
        # toolbar_layout.addWidget(self.load_model_btn)

        # Model status label
        self.model_status_label = QLabel("No model loaded")
        self.model_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #7f8c8d;
                padding: 6px;
                background-color: #ecf0f1;
                border-radius: 3px;
                min-width: 200px;
            }
        """)
        toolbar_layout.addWidget(self.model_status_label)

        # # Test Prediction button
        # self.test_prediction_btn = QPushButton("🔍 Test Prediction")
        # self.test_prediction_btn.setStyleSheet("""
        #     QPushButton {
        #         font-size: 12px;
        #         padding: 8px 12px;
        #         background-color: #e74c3c;
        #         color: white;
        #         border-radius: 4px;
        #         min-width: 120px;
        #     }
        #     QPushButton:hover {
        #         background-color: #c0392b;
        #     }
        #     QPushButton:disabled {
        #         background-color: #bdc3c7;
        #         color: #7f8c8d;
        #     }
        # """)
        # self.test_prediction_btn.clicked.connect(self.test_prediction_on_selected)
        # self.test_prediction_btn.setEnabled(False)
        # self.test_prediction_btn.setToolTip("Test prediction on selected product image")
        # toolbar_layout.addWidget(self.test_prediction_btn)

        # # Predict All button
        # self.predict_all_btn = QPushButton("🔮 Predict All Steps")
        # self.predict_all_btn.setStyleSheet("""
        #     QPushButton {
        #         font-size: 12px;
        #         padding: 8px 12px;
        #         background-color: #9b59b6;
        #         color: white;
        #         border-radius: 4px;
        #         min-width: 120px;
        #     }
        #     QPushButton:hover {
        #         background-color: #8e44ad;
        #     }
        #     QPushButton:disabled {
        #         background-color: #bdc3c7;
        #         color: #7f8c8d;
        #     }
        # """)
        # self.predict_all_btn.clicked.connect(self.predict_all_steps)
        # self.predict_all_btn.setEnabled(False)
        # self.predict_all_btn.setToolTip("Run prediction on all configured steps")
        # toolbar_layout.addWidget(self.predict_all_btn)

        # Prediction status
        self.prediction_status_label = QLabel("Prediction: Ready")
        self.prediction_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #27ae60;
                padding: 6px;
                background-color: #e8f8ef;
                border-radius: 3px;
                min-width: 150px;
            }
        """)
        toolbar_layout.addWidget(self.prediction_status_label)

        # # ===== CALIBRATION STATUS =====
        # cal_status = "✅" if self.calibration.is_calibrated else "❌"
        # self.calibration_status_label = QLabel(f"📐 Cal: {cal_status}")
        # if self.calibration.is_calibrated:
        #     self.calibration_status_label.setStyleSheet("""
        #         QLabel {
        #             font-size: 11px;
        #             color: #27ae60;
        #             padding: 6px;
        #             background-color: #e8f8ef;
        #             border-radius: 3px;
        #             font-weight: bold;
        #         }
        #     """)
        # else:
        #     self.calibration_status_label.setStyleSheet("""
        #         QLabel {
        #             font-size: 11px;
        #             color: #e74c3c;
        #             padding: 6px;
        #             background-color: #ffebee;
        #             border-radius: 3px;
        #         }
        #     """)
        # toolbar_layout.addWidget(self.calibration_status_label)
        #
        # # ===== TCP STATUS INDICATOR =====
        # self.tcp_status_label = QLabel("🔴 TCP: Disconnected")
        # self.tcp_status_label.setStyleSheet("""
        #     QLabel {
        #         font-size: 11px;
        #         color: #e74c3c;
        #         padding: 6px;
        #         background-color: #ffebee;
        #         border-radius: 3px;
        #         min-width: 120px;
        #     }
        # """)
        # toolbar_layout.addWidget(self.tcp_status_label)
        #
        # # Test TCP button (optional - for debugging)
        # self.test_tcp_btn = QPushButton("📡 Test TCP")
        # self.test_tcp_btn.setStyleSheet("""
        #     QPushButton {
        #         font-size: 12px;
        #         padding: 8px 12px;
        #         background-color: #f39c12;
        #         color: white;
        #         border-radius: 4px;
        #         min-width: 80px;
        #     }
        #     QPushButton:hover {
        #         background-color: #e67e22;
        #     }
        # """)
        # self.test_tcp_btn.clicked.connect(self.test_tcp_connection)
        # self.test_tcp_btn.setToolTip("Test TCP server connection")
        # toolbar_layout.addWidget(self.test_tcp_btn)

        toolbar_layout.addStretch()
        layout.addWidget(prediction_toolbar)

        # Main content area with two columns
        main_content = QHBoxLayout()
        main_content.setSpacing(15)

        # Left column: Step configuration
        left_column = QVBoxLayout()

        # Step 1: Select total number of steps
        # step_group = QGroupBox("Step 1: Set Number of Assembly Steps")
        # step_group.setStyleSheet("""
        #     QGroupBox {
        #         font-weight: bold;
        #         font-size: 13px;
        #         border: 2px solid #3498db;
        #         border-radius: 8px;
        #         padding-top: 15px;
        #         margin-top: 5px;
        #     }
        #     QGroupBox::title {
        #         subcontrol-origin: margin;
        #         left: 10px;
        #         padding: 0 10px 0 10px;
        #         color: #2980b9;
        #     }
        # """)
        # step_layout = QFormLayout(step_group)
        #
        # self.step_spinbox = QSpinBox()
        # self.step_spinbox.setRange(1, 10)
        # self.step_spinbox.setValue(1)
        # self.step_spinbox.valueChanged.connect(self.on_step_count_changed)
        # self.step_spinbox.setStyleSheet("""
        #     QSpinBox {
        #         font-size: 14px;
        #         padding: 8px;
        #         border: 2px solid #bdc3c7;
        #         border-radius: 4px;
        #         min-width: 80px;
        #     }
        #     QSpinBox:focus {
        #         border-color: #3498db;
        #     }
        # """)
        # step_layout.addRow("Total Assembly Steps:", self.step_spinbox)
        # left_column.addWidget(step_group)

        step_group = QGroupBox("Assembly Step")
        step_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #3498db;
                border-radius: 8px;
                padding-top: 15px;
                margin-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #2980b9;
            }
        """)
        step_layout = QFormLayout(step_group)

        fixed_step_label = QLabel("1")
        fixed_step_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                padding: 8px;
                border: 2px solid #bdc3c7;
                border-radius: 4px;
                background-color: #f8f9fa;
                min-width: 80px;
            }
        """)
        step_layout.addRow("Total Assembly Steps:", fixed_step_label)
        left_column.addWidget(step_group)

        # Steps container
        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setSpacing(15)
        self.steps_layout.setContentsMargins(0, 10, 0, 10)

        # Create scroll area for steps
        self.steps_scroll = QScrollArea()
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setWidget(self.steps_container)
        self.steps_scroll.setMinimumHeight(350)
        self.steps_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ecf0f1;
                border-radius: 5px;
                background-color: #f8f9fa;
            }
        """)

        left_column.addWidget(self.steps_scroll)

        # Right column: Image gallery and prediction preview
        right_column = QVBoxLayout()

        gallery_header = QLabel("📸 Product Images - Click to Select")
        gallery_header.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #ecf0f1;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        gallery_header.setAlignment(Qt.AlignCenter)
        right_column.addWidget(gallery_header)

        # Current step indicator
        self.step_indicator = QLabel(f"👉 Currently selecting for: Step {self.current_active_step}")
        self.step_indicator.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #e74c3c;
                padding: 8px;
                background-color: #ffebee;
                border-radius: 4px;
                margin-bottom: 10px;
            }
        """)
        self.step_indicator.setAlignment(Qt.AlignCenter)
        right_column.addWidget(self.step_indicator)

        # Gallery scroll area
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_scroll.setStyleSheet("""
            QScrollArea {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                background-color: white;
            }
        """)

        self.gallery_container = QWidget()
        self.gallery_layout = QGridLayout(self.gallery_container)
        self.gallery_layout.setAlignment(Qt.AlignTop)
        self.gallery_layout.setSpacing(10)
        self.gallery_layout.setContentsMargins(15, 15, 15, 15)

        self.gallery_scroll.setWidget(self.gallery_container)
        self.gallery_scroll.setMinimumHeight(400)

        right_column.addWidget(self.gallery_scroll)

        # # ========== PREDICTION PREVIEW ==========
        # prediction_preview = QGroupBox("🔍 Prediction Preview")
        # prediction_preview.setStyleSheet("""
        #     QGroupBox {
        #         font-weight: bold;
        #         font-size: 13px;
        #         border: 2px solid #FF9800;
        #         border-radius: 8px;
        #         padding-top: 15px;
        #         margin-top: 10px;
        #     }
        #     QGroupBox::title {
        #         subcontrol-origin: margin;
        #         left: 10px;
        #         padding: 0 10px 0 10px;
        #         color: #F57C00;
        #     }
        # """)
        #
        # prediction_layout = QVBoxLayout(prediction_preview)
        #
        # # Prediction preview widget
        # self.prediction_preview_widget = QFrame()
        # self.prediction_preview_widget.setStyleSheet("""
        #     QFrame {
        #         border: 1px solid #ddd;
        #         border-radius: 6px;
        #         background-color: white;
        #         padding: 10px;
        #         min-height: 150px;
        #     }
        # """)
        #
        # self.prediction_preview_layout = QVBoxLayout(self.prediction_preview_widget)
        #
        # # Default prediction message
        # self.prediction_message = QLabel("Load a model and select an image to see predictions")
        # self.prediction_message.setAlignment(Qt.AlignCenter)
        # self.prediction_message.setStyleSheet("""
        #     QLabel {
        #         font-size: 14px;
        #         color: #7f8c8d;
        #         padding: 50px;
        #         font-style: italic;
        #     }
        # """)
        # self.prediction_preview_layout.addWidget(self.prediction_message)
        #
        # # Prediction results label
        # self.prediction_results_label = QLabel("")
        # self.prediction_results_label.setAlignment(Qt.AlignCenter)
        # self.prediction_results_label.setStyleSheet("""
        #     QLabel {
        #         font-size: 12px;
        #         color: #2c3e50;
        #         padding: 5px;
        #         margin-top: 5px;
        #     }
        # """)
        # self.prediction_preview_layout.addWidget(self.prediction_results_label)
        #
        # prediction_layout.addWidget(self.prediction_preview_widget)
        # right_column.addWidget(prediction_preview)
        #
        # # ========== TCP MESSAGES DISPLAY ==========
        # tcp_group = QGroupBox("📡 TCP Messages")
        # tcp_group.setStyleSheet("""
        #     QGroupBox {
        #         font-weight: bold;
        #         font-size: 12px;
        #         border: 2px solid #9b59b6;
        #         border-radius: 8px;
        #         padding-top: 15px;
        #         margin-top: 5px;
        #     }
        #     QGroupBox::title {
        #         subcontrol-origin: margin;
        #         left: 10px;
        #         padding: 0 10px 0 10px;
        #         color: #8e44ad;
        #     }
        # """)
        #
        # tcp_layout = QVBoxLayout(tcp_group)
        #
        # self.tcp_messages_display = QTextEdit()
        # self.tcp_messages_display.setReadOnly(True)
        # self.tcp_messages_display.setMaximumHeight(120)
        # self.tcp_messages_display.setStyleSheet("""
        #     QTextEdit {
        #         font-family: monospace;
        #         font-size: 11px;
        #         background-color: #f8f9fa;
        #         border: 1px solid #ddd;
        #         border-radius: 4px;
        #         padding: 5px;
        #     }
        # """)
        # tcp_layout.addWidget(self.tcp_messages_display)
        #
        # clear_btn = QPushButton("🗑️ Clear")
        # clear_btn.setMaximumWidth(80)
        # clear_btn.clicked.connect(lambda: self.tcp_messages_display.clear())
        # tcp_layout.addWidget(clear_btn, alignment=Qt.AlignRight)
        #
        # right_column.addWidget(tcp_group)
        right_column.addStretch()

        # Add columns to main content
        main_content.addLayout(left_column, 45)
        main_content.addLayout(right_column, 55)

        layout.addLayout(main_content)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)

        # Refresh button
        refresh_btn = QPushButton("🔄 Load Annotation Images")
        refresh_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 10px;
                background-color: #e74c3c;
                color: white;
                border-radius: 4px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        refresh_btn.clicked.connect(self.load_bmp_from_annotation)

        self.ok_btn = QPushButton("✅ Complete Selection")
        self.ok_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                padding: 12px 24px;
                background-color: #2ecc71;
                color: white;
                border-radius: 4px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
        """)
        self.ok_btn.clicked.connect(self.validate_and_accept)
        self.ok_btn.setEnabled(False)

        cancel_btn = QPushButton("❌ Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                padding: 12px 24px;
                background-color: #95a5a6;
                color: white;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Initialize with one step
        self.create_step_widget(1)

        # Load images from annotation folder automatically
        QTimer.singleShot(100, self.load_bmp_from_annotation)

    # ===== ASSEMBLY TOOL METHODS =====
    def open_assembly_tool(self):
        """Open the Assembly Laser Annotation Tool and temporarily hide this dialog"""
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
                block_id=str(self.block_id),
                block_name=str(self.block_name),
                mode="assembly"
            )

            self.assembly_tool_window.setParent(None)
            self.assembly_tool_window.setWindowFlags(
                Qt.Window |
                Qt.WindowStaysOnTopHint |
                Qt.CustomizeWindowHint |
                Qt.WindowTitleHint |
                Qt.WindowMinMaxButtonsHint |
                Qt.WindowCloseButtonHint
            )
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

    def close_dialog_safely(self):
        """Safely close the dialog with a small delay to ensure Assembly Tool is shown"""
        try:
            print("🟡 Executing close_dialog_safely")

            # Option 1: Just reject/close the dialog
            # self.reject()

            if self.assembly_tool_window and self.assembly_tool_window.isVisible():
                print("🟡 Assembly Tool window already exists, raising it")
                self.assembly_tool_window.raise_()
                self.assembly_tool_window.activateWindow()
                self.update_tcp_messages("🛠️ Assembly Tool already open")
                return

            print("✅ Dialog closed successfully")
        except Exception as e:
            print(f"❌ Error closing dialog: {e}")

    def _on_assembly_tool_closed(self):
        """Handle assembly tool window closing"""
        self.update_tcp_messages("✅ Assembly Tool closed")
        self.assembly_tool_window = None

        # 工具关掉后，把配置窗口显示回来
        self.show()
        self.raise_()
        self.activateWindow()

    def _init_heartbeat_manager(self):
        """Initialize or reference the shared heartbeat manager"""
        if AssemblyDialog._heartbeat_manager is None:
            AssemblyDialog._heartbeat_manager = HeartbeatManager()
            # Connect signals
            AssemblyDialog._heartbeat_manager.connection_status_changed.connect(
                self._on_heartbeat_connection_changed
            )
            AssemblyDialog._heartbeat_manager.heartbeat_sent.connect(
                self._on_heartbeat_sent
            )

        AssemblyDialog._heartbeat_reference_count += 1
        print(f"🔌 Heartbeat manager reference count: {AssemblyDialog._heartbeat_reference_count}")

        # Try to connect if not already connected
        self._ensure_heartbeat_connected()

    def _on_heartbeat_connection_changed(self, connected, message):
        """Handle heartbeat connection status changes"""
        if hasattr(self, 'tcp_status_label'):
            if connected:
                self.tcp_status_label.setText("🟢 TCP: Connected (Heartbeat)")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 6px;
                        background-color: #e8f8ef;
                        border-radius: 3px;
                        font-weight: bold;
                    }
                """)
            else:
                self.tcp_status_label.setText("🔴 TCP: Disconnected")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e74c3c;
                        padding: 6px;
                        background-color: #ffebee;
                        border-radius: 3px;
                    }
                """)

        self.update_tcp_messages(
            f"{'✅ Heartbeat connected' if connected else '🔴 Heartbeat disconnected'}: {message}"
        )

    def _on_heartbeat_sent(self, message):
        """Handle heartbeat sent events"""
        self.update_tcp_messages(f"💓 {message}")

    def _ensure_heartbeat_connected(self):
        """Ensure heartbeat manager is connected"""
        if AssemblyDialog._heartbeat_manager and not AssemblyDialog._heartbeat_manager.is_connected():
            server_ip = self.get_server_address()
            server_port = self.get_server_port()

            success, message = AssemblyDialog._heartbeat_manager.connect(server_ip, server_port)
            if success:
                self.update_tcp_messages(f"✅ Heartbeat started (interval: 5s)")
            else:
                self.update_tcp_messages(f"❌ Heartbeat failed: {message}")

    # ===== TCP CONNECTION METHODS =====
    def ensure_tcp_connected(self):
        """Connect to TCP server - keeps connection open across dialogs"""
        # Check if we already have a global connection
        if hasattr(AssemblyDialog, '_global_tcp_socket') and AssemblyDialog._global_tcp_socket:
            self.tcp_socket = AssemblyDialog._global_tcp_socket
            self.tcp_connected = True
            print(f"✅ Reusing existing TCP connection")
            return True

        try:
            server_ip = self.get_server_address()
            server_port = self.get_server_port()

            if not server_ip:
                print("⚠️ No server IP configured")
                return False

            print(f"📡 Connecting to TCP server {server_ip}:{server_port}...")

            # Create socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(5)

            # Connect
            self.tcp_socket.connect((server_ip, server_port))

            self.tcp_connected = True
            print(f"✅ TCP Connected to {server_ip}:{server_port}")

            # Save to global for other dialogs to reuse
            AssemblyDialog._global_tcp_socket = self.tcp_socket

            # Update UI
            if hasattr(self, 'tcp_status_label'):
                self.tcp_status_label.setText("🟢 TCP: Connected")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 6px;
                        background-color: #e8f8ef;
                        border-radius: 3px;
                        font-weight: bold;
                    }
                """)

            return True

        except Exception as e:
            print(f"⚠️ TCP connection failed: {e}")
            self.tcp_connected = False
            self.tcp_socket = None
            AssemblyDialog._global_tcp_socket = None

            # Update UI
            if hasattr(self, 'tcp_status_label'):
                self.tcp_status_label.setText("🔴 TCP: Disconnected")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e74c3c;
                        padding: 6px;
                        background-color: #ffebee;
                        border-radius: 3px;
                    }
                """)
            return False

    def start_tcp_keepalive(self):
        """Enable TCP keep-alive to prevent timeout disconnects"""
        if self.tcp_socket:
            try:
                # Enable keep-alive
                self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                # For Windows, set keep-alive parameters
                if hasattr(socket, 'TCP_KEEPIDLE'):
                    self.tcp_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                    self.tcp_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
                    self.tcp_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                print("✅ TCP keep-alive enabled")
            except Exception as e:
                print(f"⚠️ Could not enable keep-alive: {e}")

    def start_tcp_listening(self):
        """Start thread to listen for TCP responses"""

        def listen_thread():
            while self.tcp_connected and self.tcp_socket:
                try:
                    data = self.tcp_socket.recv(1024)
                    if data:
                        response = data.decode('utf-8').strip()
                        self.update_tcp_messages(f"📨 Server: {response}")

                        # Handle specific responses if needed
                        if "OK" in response or "ACK" in response:
                            self.handle_server_acknowledgment(response)
                    else:
                        # Connection closed by server
                        break
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.tcp_connected:
                        print(f"TCP listening error: {e}")
                    break

            self.tcp_connected = False
            self.update_tcp_messages("🔌 Disconnected from server")

            # Update status indicator
            if hasattr(self, 'tcp_status_label'):
                self.tcp_status_label.setText("🔴 TCP: Disconnected")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e74c3c;
                        padding: 6px;
                        background-color: #ffebee;
                        border-radius: 3px;
                    }
                """)

        thread = threading.Thread(target=listen_thread, daemon=True)
        thread.start()

    def handle_server_acknowledgment(self, response):
        """Handle server acknowledgment messages"""
        self.update_tcp_messages(f"✅ Server acknowledged: {response}")

        # You can add specific handling here
        # For example, if server sends "SAVE_OK", you might want to save something
        if "SAVE" in response:
            self.update_tcp_messages("💾 Server confirmed data saved")

    def test_tcp_connection_direct(self):
        """Direct test of TCP connection"""
        import socket
        import time

        server_ip = "127.0.0.1"
        server_port = 8888

        try:
            print(f"\n🔌 Testing direct TCP connection to {server_ip}:{server_port}")

            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)

            # Connect
            sock.connect((server_ip, server_port))
            print("✅ Connected successfully")

            # Send test message
            test_msg = "123.45_67.89,234.56_78.90,345.67_89.01,456.78_90.12\n"
            bytes_sent = sock.send(test_msg.encode('utf-8'))
            print(f"✅ Sent {bytes_sent} bytes: {test_msg.rstrip()}")

            # Wait for data to transmit
            time.sleep(0.5)

            # Try to receive response
            try:
                response = sock.recv(1024)
                print(f"📨 Response: {response.decode('utf-8').rstrip()}")
            except socket.timeout:
                print("⏱️ No response (timeout)")
            except Exception as e:
                print(f"⚠️ Receive error: {e}")

            # Close
            sock.close()
            print("🔌 Connection closed")

        except Exception as e:
            print(f"❌ Test failed: {e}")

    def get_server_address(self):
        """Get server IP address from config or return default"""
        try:
            # Try to get from config manager
            if hasattr(config_manager, 'get_tcp_server'):
                return config_manager.get_tcp_server()
        except:
            pass

        # Return default or try to get from parent
        try:
            if self.parent() and hasattr(self.parent(), 'host_edit'):
                return self.parent().host_edit.text().strip()
        except:
            pass

        # Default fallback
        return "127.0.0.1"

    def get_server_port(self):
        """Get server port from config or return default"""
        try:
            # Try to get from config manager
            if hasattr(config_manager, 'get_tcp_port'):
                return config_manager.get_tcp_port()
        except:
            pass

        # Return default or try to get from parent
        try:
            if self.parent() and hasattr(self.parent(), 'port_spin'):
                return self.parent().port_spin.value()
        except:
            pass

        # Default fallback
        return 8888

    def update_tcp_messages(self, message):
        """Update TCP messages display"""
        try:
            if hasattr(self, 'tcp_messages_display'):
                current_text = self.tcp_messages_display.toPlainText()
                timestamp = time.strftime("%H:%M:%S")
                new_text = f"[{timestamp}] {message}\n{current_text}"
                self.tcp_messages_display.setPlainText(new_text)
        except:
            # Just print to console if no display
            print(f"[TCP] {message}")

    def test_tcp_connection(self):
        """Test TCP server connection"""
        server_ip = self.get_server_address()
        server_port = self.get_server_port()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)

            self.update_tcp_messages(f"🔌 Testing connection to {server_ip}:{server_port}...")

            sock.connect((server_ip, server_port))

            # Send test message
            test_msg = f"TEST|AssemblyDialog|{self.block_name}|Step_{self.current_active_step}"
            sock.sendall(test_msg.encode('utf-8'))

            self.update_tcp_messages(f"✅ Connected to {server_ip}:{server_port}")

            # Try to receive response
            try:
                response = sock.recv(1024)
                self.update_tcp_messages(f"📨 Response: {response.decode('utf-8').strip()}")
            except:
                self.update_tcp_messages(f"⚠️ No response (server may not send replies)")

            sock.close()

            QMessageBox.information(self, "✅ TCP Test",
                                    f"Successfully connected to {server_ip}:{server_port}")

        except Exception as e:
            error_msg = f"❌ Connection failed: {e}"
            self.update_tcp_messages(error_msg)
            QMessageBox.warning(self, "❌ TCP Test Failed", error_msg)

    # ===== EXISTING METHODS WITH TCP INTEGRATION =====
    # def load_initial_configuration(self):
    #     """Load initial configuration if editing existing assembly"""
    #     try:
    #         if 'total_steps' in self.initial_config:
    #             # Set total steps
    #             self.step_spinbox.setValue(self.initial_config['total_steps'])
    #             self.total_steps = self.initial_config['total_steps']
    #
    #             # Load step selections - ACCESS THE 'selections' KEY
    #             if 'selections' in self.initial_config:
    #                 # Wait a bit for UI to update
    #                 QTimer.singleShot(200, lambda: self.restore_step_selections(self.initial_config['selections']))
    #
    #     except Exception as e:
    #         print(f"Error loading initial configuration: {e}")

    def load_initial_configuration(self):
        """Load initial configuration if editing existing assembly"""
        try:
            self.total_steps = 1

            if 'selections' in self.initial_config:
                QTimer.singleShot(200, lambda: self.restore_step_selections(self.initial_config['selections']))

        except Exception as e:
            print(f"Error loading initial configuration: {e}")

    def restore_step_selections(self, selections):
        """Restore previous step selections with block-aware paths"""
        try:
            # First, ensure we have all products loaded
            if not self.available_products:
                self.load_bmp_from_annotation()
                # Wait a bit for products to load
                QTimer.singleShot(300, lambda: self._restore_selections_after_load(selections))
            else:
                self._restore_selections_after_load(selections)

        except Exception as e:
            print(f"Error restoring selections: {e}")

    def _restore_selections_after_load(self, selections):
        """Restore selections after products are loaded"""
        try:
            for step_str, selection in selections.items():
                try:
                    step_num = int(step_str)  # This will work now because step_str is a number string
                except ValueError:
                    print(f"Skipping non-step key: {step_str}")
                    continue

                product_id = selection['product_id']

                # Find the product in available products
                product = None
                for p in self.available_products:
                    if p['id'] == product_id:
                        product = p
                        break

                if product:
                    # Create new unique folder for this block
                    assembly_folder = self.ensure_assembly_folder()
                    capture_info = {}

                    if assembly_folder:
                        # Find existing images for this step in the block folder
                        pattern = f"Step_{step_num}_*.bmp"
                        existing_images = glob.glob(os.path.join(assembly_folder, pattern))

                        if existing_images:
                            # Use the most recent image for this step
                            existing_images.sort(key=os.path.getmtime, reverse=True)
                            latest_image = existing_images[0]

                            capture_info = {
                                'capture_folder': assembly_folder,
                                'current_image': latest_image,
                                'assembly_folder': assembly_folder,
                                'block_name': self.block_name
                            }
                        else:
                            capture_info = {
                                'capture_folder': assembly_folder,
                                'current_image': None,
                                'assembly_folder': assembly_folder,
                                'block_name': self.block_name
                            }
                    else:
                        capture_info = selection.get('capture_info', {})

                    # Store selection with updated paths
                    self.step_selections[step_num] = {
                        'product_id': product_id,
                        'product_data': selection.get('product_data', {
                            'name': product['name'],
                            'original_name': product['original_name'],
                            'image_path': product['image_path'],
                            'filename': product['filename'],
                            'annotation_path': product['relative_path'],
                            'model_path': self.get_model_path(product_id),
                            'trained': self.is_model_trained(product_id)
                        }),
                        'capture_info': capture_info
                    }

                    # Update visual feedback
                    self.update_step_display(step_num, product)
                    self.update_thumbnail_selection(product_id, step_num)

                    # Enable capture button for this step
                    if step_num in self.step_widgets:
                        step_frame = self.step_widgets[step_num]['frame']
                        capture_btn = step_frame.findChild(QPushButton, f"step_{step_num}_capture_btn")
                        if capture_btn:
                            capture_btn.setEnabled(True)

                        # Check for captured images
                        if capture_info.get('current_image'):
                            self.step_widgets[step_num]['capture_folder'] = capture_info['capture_folder']
                            self.step_widgets[step_num]['capture_counter'] = 1
                            self.step_widgets[step_num]['current_image'] = capture_info['current_image']

                            self.update_capture_status(step_num, "1 image captured")

                            preview_btn = step_frame.findChild(QPushButton, f"step_{step_num}_preview_btn")
                            if preview_btn:
                                preview_btn.setEnabled(True)

            # Update current active step
            if selections:
                step_keys = [int(k) for k in selections.keys() if k.isdigit()]
                if step_keys:
                    last_step = max(step_keys)
                    if last_step < self.total_steps:
                        self.current_active_step = last_step + 1
                    else:
                        self.current_active_step = 1

            self.update_step_indicator()
            self.check_completion()

        except Exception as e:
            print(f"Error in _restore_selections_after_load: {e}")
            import traceback
            traceback.print_exc()

    def create_step_widget(self, step_number):
        """Create a widget for a specific step with direct capture functionality"""
        step_frame = QFrame()
        step_frame.setFrameStyle(QFrame.Box)

        # Store reference
        self.step_widgets[step_number] = {
            'frame': step_frame,
            'capture_counter': 0,
            'capture_folder': None
        }

        if step_number == self.current_active_step:
            step_frame.setStyleSheet("""
                QFrame {
                    border: 3px solid #3498db;
                    border-radius: 8px;
                    background-color: #e3f2fd;
                    padding: 12px;
                }
            """)
        else:
            step_frame.setStyleSheet("""
                QFrame {
                    border: 2px solid #bdc3c7;
                    border-radius: 8px;
                    background-color: #f8f9fa;
                    padding: 12px;
                }
            """)

        layout = QVBoxLayout(step_frame)
        layout.setSpacing(10)

        # Step header
        header = QLabel(f"Step {step_number}")
        header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding-bottom: 5px;
                border-bottom: 1px solid #dfe6e9;
            }
        """)
        layout.addWidget(header)

        # Selection display
        selection_display = QLabel("⏳ Not selected yet")
        selection_display.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #7f8c8d;
                padding: 8px;
                background-color: #ecf0f1;
                border-radius: 4px;
                min-height: 40px;
            }
        """)
        selection_display.setWordWrap(True)
        selection_display.setObjectName(f"step_{step_number}_display")
        layout.addWidget(selection_display)

        # # Capture controls frame
        # capture_frame = QFrame()
        # capture_frame.setStyleSheet("""
        #     QFrame {
        #         border: 1px solid #ddd;
        #         border-radius: 6px;
        #         background-color: #f9f9f9;
        #         padding: 8px;
        #     }
        # """)

        # capture_layout = QVBoxLayout(capture_frame)
        # capture_layout.setSpacing(8)

        # # DIRECT CAPTURE button - Capture immediately
        # capture_btn = QPushButton("📷 Capture Assembly Image")
        # capture_btn.setStyleSheet("""
        #     QPushButton {
        #         font-size: 12px;
        #         padding: 8px;
        #         background-color: #9b59b6;
        #         color: white;
        #         border-radius: 4px;
        #     }
        #     QPushButton:hover {
        #         background-color: #8e44ad;
        #     }
        #     QPushButton:disabled {
        #         background-color: #bdc3c7;
        #         color: #7f8c8d;
        #     }
        # """)
        # capture_btn.clicked.connect(lambda checked, step=step_number: self.direct_capture_for_step(step))
        # capture_btn.setEnabled(False)
        # capture_btn.setObjectName(f"step_{step_number}_capture_btn")

        # # Capture status
        # capture_status = QLabel("No images captured")
        # capture_status.setStyleSheet("""
        #     QLabel {
        #         font-size: 11px;
        #         color: #7f8c8d;
        #         padding: 4px;
        #         background-color: #f0f0f0;
        #         border-radius: 3px;
        #     }
        # """)
        # capture_status.setObjectName(f"step_{step_number}_capture_status")

        # # Preview button
        # preview_btn = QPushButton("👁️ Preview Captured")
        # preview_btn.setStyleSheet("""
        #     QPushButton {
        #         font-size: 11px;
        #         padding: 5px;
        #         background-color: #3498db;
        #         color: white;
        #         border-radius: 3px;
        #     }
        #     QPushButton:hover {
        #         background-color: #2980b9;
        #     }
        #     QPushButton:disabled {
        #         background-color: #bdc3c7;
        #         color: #7f8c8d;
        #     }
        # """)
        # preview_btn.clicked.connect(lambda checked, step=step_number: self.preview_captured_for_step(step))
        # preview_btn.setEnabled(False)
        # preview_btn.setObjectName(f"step_{step_number}_preview_btn")
        #
        # capture_layout.addWidget(capture_btn)
        # capture_layout.addWidget(capture_status)
        # capture_layout.addWidget(preview_btn)

        # layout.addWidget(capture_frame)

        # Step selection button
        # step_btn = QPushButton(f"Select Product for Step {step_number}")

        # step_btn.clicked.connect(lambda checked, step=step_number: self.set_active_step(step))
        # step_btn.setObjectName(f"step_{step_number}_btn")
        # layout.addWidget(step_btn)

        # Store in layout
        step_frame.setProperty("step_number", step_number)
        self.steps_layout.addWidget(step_frame)

    def ensure_assembly_folder(self):
        """Ensure the Assembly folder exists for specific block"""
        recipe_path = self.get_current_recipe_path()
        if not recipe_path:
            return None

        # Create Assembly/Block_{block_id} folder
        self.assembly_folder = os.path.join(recipe_path, "Assembly", f"Block_{self.block_id}")
        os.makedirs(self.assembly_folder, exist_ok=True)

        return self.assembly_folder

    def direct_capture_for_step(self, step_number):
        """Direct camera capture for a specific step - captures, saves, and predicts"""
        if step_number not in self.step_selections:
            QMessageBox.warning(self, "⚠️ No Product Selected",
                                f"Please select a product for Step {step_number} first.")
            return

        # Get product info
        product_id = self.step_selections[step_number]['product_id']
        product_data = self.step_selections[step_number]['product_data']
        product_name = product_data['name']

        # Check if model is loaded for prediction
        if not self.prediction_manager.is_model_loaded():
            # Try to auto-load the latest model for this product
            model_loaded = self.auto_load_product_model(product_id)
            if not model_loaded:
                QMessageBox.warning(
                    self,
                    "⚠️ No Model Found",
                    f"No trained model found for {product_name}.\n\n"
                    f"Please train a model first in the Deep Learning page."
                )
                return

        # Ensure Assembly folder exists (unique for this block)
        assembly_folder = self.ensure_assembly_folder()
        if not assembly_folder:
            QMessageBox.warning(self, "⚠️ No Recipe", "Current recipe not found.")
            return

        print(f"DEBUG: Block folder: {assembly_folder}")
        print(f"DEBUG: Block name: {self.block_name}")
        print(f"DEBUG: Product selected: {product_name} (ID: {product_id})")

        # Generate unique filename for this step
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Step_{step_number}_{timestamp}.bmp"

        # Check if there's already an image for this step in the block folder
        existing_images = []
        if os.path.exists(assembly_folder):
            # Look for files starting with "Step_{step_number}_"
            pattern = f"Step_{step_number}_*.bmp"
            existing_images = glob.glob(os.path.join(assembly_folder, pattern))

        if existing_images:
            print(f"DEBUG: Found existing images for step {step_number}: {existing_images}")
            # Ask user if they want to replace the existing image
            reply = QMessageBox.question(
                self, "⚠️ Image Already Exists",
                f"Step {step_number} already has a captured image.\n\n"
                f"Existing image: {os.path.basename(existing_images[0])}\n\n"
                "Do you want to replace it with a new capture?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

            # Delete the existing image(s) for this step
            try:
                for img in existing_images:
                    os.remove(img)
                    print(f"DEBUG: Deleted existing image: {img}")
            except Exception as e:
                QMessageBox.warning(self, "⚠️ Error", f"Failed to delete existing image: {str(e)}")
                return

        # Store the full path for this step's image
        image_path = os.path.join(assembly_folder, filename)
        self.step_widgets[step_number]['capture_folder'] = assembly_folder
        self.step_widgets[step_number]['capture_counter'] = 1
        self.step_widgets[step_number]['current_image'] = image_path

        # Get class ID for prediction filtering
        class_id = self.prediction_manager.get_class_id_by_name(product_name)
        if class_id is not None:
            class_name = self.prediction_manager.current_model.names.get(class_id, product_name)
            predict_message = f"\n🔍 AI will automatically detect '{class_name}' in the captured image."
        else:
            predict_message = f"\n🔍 AI will detect all objects in the captured image."

        # Get relative path for display
        recipe_path = self.get_current_recipe_path()
        rel_path = ""
        if recipe_path:
            try:
                rel_path = os.path.relpath(assembly_folder, recipe_path)
            except:
                rel_path = assembly_folder

        # Show preparation message
        QMessageBox.information(self, "📸 Camera Capture with AI Detection",
                                f"Step {step_number}: {product_name}\n\n"
                                f"Camera will open shortly...{predict_message}\n\n"
                                f"Image will be SAVED to:\n{rel_path}/{filename}")

        # Disable capture button during capture
        step_frame = self.step_widgets[step_number]['frame']
        # capture_btn = step_frame.findChild(QPushButton, f"step_{step_number}_capture_btn")
        # if capture_btn:
        #     capture_btn.setEnabled(False)
        #     capture_btn.setText("📷 Capturing...")

        # Update status
        self.update_capture_status(step_number, "Opening camera (with AI prediction)...")

        # Create capture worker with save_image = TRUE
        self.capture_worker = CaptureWorker(assembly_folder, step_number, product_name, filename, save_image=True)

        # Connect to enhanced finished handler that includes prediction
        self.capture_worker.finished.connect(
            lambda success, msg, path: self.on_capture_with_prediction_finished(
                step_number, product_name, product_id, success, msg, path
            )
        )

        self.capture_worker.start()

        # Show progress dialog
        self.show_capture_with_prediction_progress(step_number, product_name)

    def show_camera_capture_with_prediction(self, step_number, product_name, product_id, block_folder, filename):
        """Show dialog and start camera capture with automatic prediction"""
        # Get relative path for display
        recipe_path = self.get_current_recipe_path()
        rel_path = ""
        if recipe_path:
            try:
                rel_path = os.path.relpath(block_folder, recipe_path)
            except:
                rel_path = block_folder

        # Get class ID for prediction filtering
        class_id = self.prediction_manager.get_class_id_by_name(product_name)
        if class_id is not None:
            class_name = self.prediction_manager.current_model.names.get(class_id, product_name)
            predict_message = f"\n🔍 AI will automatically detect '{class_name}' in the captured image."
        else:
            predict_message = f"\n🔍 AI will detect all objects in the captured image."

        # Show preparation message
        QMessageBox.information(self, "📸 Camera Capture with AI Detection",
                                f"Step {step_number}: {product_name}\n\n"
                                f"Camera will open shortly...{predict_message}\n\n"
                                f"Image will be saved to:\n{rel_path}/{filename}")

        # Disable capture button during capture
        step_frame = self.step_widgets[step_number]['frame']
        # capture_btn = step_frame.findChild(QPushButton, f"step_{step_number}_capture_btn")
        # if capture_btn:
        #     capture_btn.setEnabled(False)
        #     capture_btn.setText("📷 Capturing...")

        # Update status
        self.update_capture_status(step_number, "Opening camera (with AI prediction)...")

        # Create capture worker
        self.capture_worker = CaptureWorker(block_folder, step_number, product_name, filename)

        # Connect to enhanced finished handler that includes prediction
        self.capture_worker.finished.connect(
            lambda success, msg, path: self.on_capture_with_prediction_finished(
                step_number, product_name, product_id, success, msg, path
            )
        )

        self.capture_worker.start()

        # Show progress dialog
        self.show_capture_with_prediction_progress(step_number, product_name)

    def show_capture_with_prediction_progress(self, step_number, product_name):
        """Show capture progress dialog with prediction info"""
        self.progress_dialog = QProgressDialog(
            f"📸 Step {step_number}: Capturing {product_name}\n\n"
            f"Camera will open automatically...\n"
            f"After capture, AI will detect objects in the image",
            "Cancel", 0, 0, self
        )
        self.progress_dialog.setWindowTitle("📸 Camera Capture & AI Detection")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.cancel_capture)
        self.progress_dialog.show()

    def on_capture_with_prediction_finished(self, step_number, product_name, product_id, success, message, image_path):
        """Handle capture completion and run prediction"""
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()

        # Re-enable capture button
        step_frame = self.step_widgets[step_number]['frame']
        # capture_btn = step_frame.findChild(QPushButton, f"step_{step_number}_capture_btn")
        # if capture_btn:
        #     capture_btn.setEnabled(True)
        #     capture_btn.setText("📷 Capture Image for this Step")

        if success and image_path:
            # Update step data with captured image
            self.step_widgets[step_number]['capture_folder'] = os.path.dirname(image_path)
            self.step_widgets[step_number]['capture_counter'] = 1
            self.step_widgets[step_number]['current_image'] = image_path

            # Update capture status
            self.update_capture_status(step_number, "1 image captured")

            # Enable preview button
            # preview_btn = step_frame.findChild(QPushButton, f"step_{step_number}_preview_btn")
            # if preview_btn:
            #     preview_btn.setEnabled(True)

            # Show success message for capture
            filename = os.path.basename(image_path)

            # Now run prediction on the captured image
            self.prediction_status_label.setText(f"🔍 Running AI detection on captured image...")

            # Run prediction - this will use the same logic as auto_capture_and_predict
            self.run_auto_prediction_on_captured(step_number, product_name, product_id, image_path)

        else:
            QMessageBox.warning(self, "❌ Capture Failed", message)
            self.update_capture_status(step_number, "Capture failed")

    def show_camera_capture_dialog(self, step_number, product_name, block_folder, filename, save_image=True):
        """Show dialog and start camera capture with save option"""
        # Get relative path for display
        recipe_path = self.get_current_recipe_path()
        rel_path = ""
        if recipe_path:
            try:
                rel_path = os.path.relpath(block_folder, recipe_path)
            except:
                rel_path = block_folder

        save_text = "Image will be SAVED permanently" if save_image else "Image will be TEMPORARY"

        # Show preparation message
        QMessageBox.information(self, "📸 Camera Capture",
                                f"Step {step_number}: {product_name}\n\n"
                                f"Camera will open shortly...\n\n"
                                f"{save_text} to:\n{rel_path}/{filename}")

        # Disable capture button during capture
        step_frame = self.step_widgets[step_number]['frame']
        # capture_btn = step_frame.findChild(QPushButton, f"step_{step_number}_capture_btn")
        # if capture_btn:
        #     capture_btn.setEnabled(False)
        #     capture_btn.setText("📷 Capturing...")

        # Update status
        self.update_capture_status(step_number, "Opening camera...")

        # Start camera capture in background thread with save_image flag
        self.start_camera_capture(step_number, product_name, block_folder, filename, save_image)

    def start_camera_capture(self, step_number, product_name, block_folder, filename, save_image=True):
        """Start camera capture using your existing camera system"""
        print(f"DEBUG: start_camera_capture called for {filename} with save_image={save_image}")

        # Check if camera is available
        print(f"DEBUG: CAMERA_AVAILABLE = {CAMERA_AVAILABLE}")

        # Create and start capture worker - pass the filename and save_image flag
        self.capture_worker = CaptureWorker(block_folder, step_number, product_name, filename, save_image)
        self.capture_worker.finished.connect(lambda success, msg, path:
                                             self.on_capture_finished(step_number, success, msg, path))
        self.capture_worker.start()

        print(f"DEBUG: Capture worker started")

        # Show progress dialog
        self.show_capture_progress(step_number, product_name)

    def show_capture_progress(self, step_number, product_name):
        """Show capture progress dialog"""
        self.progress_dialog = QProgressDialog(
            f"Capturing image for Step {step_number}: {product_name}",
            "Cancel", 0, 0, self
        )
        self.progress_dialog.setWindowTitle("📸 Camera Capture")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.cancel_capture)
        self.progress_dialog.show()

    def cancel_capture(self):
        """Cancel ongoing capture"""
        if self.capture_worker and self.capture_worker.isRunning():
            self.capture_worker.stop()
            self.capture_worker.quit()
            self.capture_worker.wait()

        if self.progress_dialog:
            self.progress_dialog.close()

        # Re-enable capture button
        current_step = self.current_active_step
        if current_step in self.step_widgets:
            step_frame = self.step_widgets[current_step]['frame']
            # capture_btn = step_frame.findChild(QPushButton, f"step_{current_step}_capture_btn")
            # if capture_btn:
            #     capture_btn.setEnabled(True)
            #     capture_btn.setText("📷 Capture Images for this Step")

        self.update_capture_status(current_step, "Capture cancelled")

    def on_capture_finished(self, step_number, success, message, image_path):
        """Handle capture completion"""
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()

        # Re-enable capture button
        step_frame = self.step_widgets[step_number]['frame']
        # capture_btn = step_frame.findChild(QPushButton, f"step_{step_number}_capture_btn")
        # if capture_btn:
        #     capture_btn.setEnabled(True)
        #     capture_btn.setText("📷 Capture Image for this Step")

        if success and image_path:
            # Update status - always show 1 image since we replace
            self.update_capture_status(step_number, "1 image captured")

            # Enable preview button
            # preview_btn = step_frame.findChild(QPushButton, f"step_{step_number}_preview_btn")
            # if preview_btn:
            #     preview_btn.setEnabled(True)

            # Show success message with replace info
            filename = os.path.basename(image_path)
            self.show_capture_success(step_number, filename)

            # Don't ask for another capture - each step only has one image
            # Instead, show completion message
            QMessageBox.information(
                self, "✅ Capture Complete",
                f"Image captured for Step {step_number}.\n\n"
                f"Each step can only have one image.\n"
                f"To capture a different image, use 'Capture Image for this Step' again."
            )
        else:
            QMessageBox.warning(self, "❌ Capture Failed", message)
            self.update_capture_status(step_number, "Capture failed")

    def show_capture_success(self, step_number, filename):
        """Show success message after capture"""
        # Get relative path for display
        recipe_path = self.get_current_recipe_path()
        rel_path = ""
        if step_number in self.step_widgets:
            step_folder = self.step_widgets[step_number].get('capture_folder')
            if step_folder and recipe_path:
                try:
                    rel_path = os.path.relpath(step_folder, recipe_path)
                except:
                    rel_path = step_folder

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(f"✅ Step {step_number} - Image Captured")
        msg.setText("Image captured successfully!")
        msg.setInformativeText(f"Saved to: {rel_path}\nFile: {filename}\n\n"
                               f"⚠️ Only one image per step is allowed.\n"
                               f"To capture a different image, use 'Capture Image' again.")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QMessageBox QLabel {
                font-size: 12px;
            }
        """)

        # Auto-close after 3 seconds
        QTimer.singleShot(3000, msg.accept)
        msg.exec()

    def update_capture_status(self, step_number, status_text):
        """Update capture status display for a step"""
        if step_number not in self.step_widgets:
            return

        step_frame = self.step_widgets[step_number]['frame']
        status_label = step_frame.findChild(QLabel, f"step_{step_number}_capture_status")

        if not status_label:
            print(f"DEBUG: step_{step_number}_capture_status not found, skip UI update: {status_text}")
            return

        step_folder = self.step_widgets[step_number].get('capture_folder')
        if step_folder and os.path.exists(step_folder):
            pattern = os.path.join(step_folder, f"Step_{step_number}_*.bmp")
            existing_images = glob.glob(pattern)
            if existing_images:
                status_text = "1 image captured"

        status_label.setText(status_text)

        if "1 image" in status_text:
            status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #27ae60;
                    padding: 4px;
                    background-color: #e8f8ef;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        elif "Capture failed" in status_text:
            status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #e74c3c;
                    padding: 4px;
                    background-color: #ffebee;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        else:
            status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #7f8c8d;
                    padding: 4px;
                    background-color: #f0f0f0;
                    border-radius: 3px;
                }
            """)

    def preview_captured_for_step(self, step_number):
        """Preview captured image for a specific step"""
        if step_number not in self.step_widgets:
            return

        step_data = self.step_widgets[step_number]

        # Check for current image
        current_image = step_data.get('current_image')
        if not current_image or not os.path.exists(current_image):
            # Try to find any image for this step in the block folder
            block_folder = step_data.get('capture_folder')
            if block_folder and os.path.exists(block_folder):
                pattern = f"Step_{step_number}_*.bmp"
                existing_images = glob.glob(os.path.join(block_folder, pattern))
                if existing_images:
                    # Use the most recent image
                    existing_images.sort(key=os.path.getmtime, reverse=True)
                    current_image = existing_images[0]
                else:
                    QMessageBox.warning(self, "⚠️ No Captured Image",
                                        f"No captured image found for Step {step_number}.")
                    return
            else:
                QMessageBox.warning(self, "⚠️ No Captured Image",
                                    f"No captured image found for Step {step_number}.")
                return

        # Get product info
        product_name = "Unknown"
        if step_number in self.step_selections:
            product_name = self.step_selections[step_number]['product_data']['name']

        # Show block-specific path
        if self.block_name:
            # Get relative path from recipe folder
            recipe_path = self.get_current_recipe_path()
            if recipe_path:
                try:
                    block_folder = os.path.dirname(current_image)
                    rel_path = os.path.relpath(block_folder, recipe_path)
                except:
                    rel_path = f"Assembly/{self.block_name}/"
            else:
                rel_path = f"Assembly/{self.block_name}/"
        else:
            rel_path = "Assembly/"

        # Show preview dialog
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle(f"📸 Step {step_number} - Captured Image")
        preview_dialog.setFixedSize(600, 400)

        layout = QVBoxLayout(preview_dialog)

        # Header
        header = QLabel(f"Step {step_number}: {product_name}")
        header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #ecf0f1;
                border-radius: 5px;
                margin-bottom: 10px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Image info
        img_file = os.path.basename(current_image)
        info_label = QLabel(f"File: {img_file}\nLocation: {rel_path}")
        info_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #7f8c8d;
                padding: 8px;
                background-color: #f8f9fa;
                border-radius: 4px;
                margin-bottom: 10px;
            }
        """)
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)

        # Image preview
        try:
            pixmap = QPixmap(current_image)
            if not pixmap.isNull():
                # Scale image to fit
                scaled_pixmap = pixmap.scaled(
                    400, 300,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                image_label = QLabel()
                image_label.setPixmap(scaled_pixmap)
                image_label.setAlignment(Qt.AlignCenter)
                image_label.setStyleSheet("""
                    QLabel {
                        border: 2px solid #bdc3c7;
                        border-radius: 6px;
                        background-color: #f8f9fa;
                        padding: 5px;
                    }
                """)
                layout.addWidget(image_label, alignment=Qt.AlignCenter)
        except:
            error_label = QLabel("❌ Unable to display image")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet("""
                QLabel {
                    color: #e74c3c;
                    font-size: 13px;
                    padding: 20px;
                    background-color: #ffebee;
                    border-radius: 6px;
                }
            """)
            layout.addWidget(error_label)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px;
                background-color: #95a5a6;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        close_btn.clicked.connect(preview_dialog.accept)
        layout.addWidget(close_btn)

        preview_dialog.exec()

    def get_assembly_structure(self):
        """Get the assembly folder structure for this block"""
        if not self.assembly_folder:
            return None

        structure = {
            'block_name': self.block_name,
            'assembly_folder': self.assembly_folder,
            'step_images': {}
        }

        for step in range(1, self.total_steps + 1):
            pattern = os.path.join(self.assembly_folder, f"Step_{step}_*.bmp")
            images = glob.glob(pattern)
            images.sort(key=os.path.getmtime, reverse=True)

            structure['step_images'][step] = {
                'images': images,
                'latest_image': images[0] if images else None
            }

        return structure

    def show_available_classes(self):
        """Show all available classes in the loaded model"""
        if not self.prediction_manager.is_model_loaded():
            QMessageBox.warning(self, "No Model Loaded", "Please load a model first.")
            return

        classes = self.prediction_manager.debug_print_classes()

        if not classes:
            QMessageBox.information(self, "No Classes", "No class information available in the model.")
            return

        # Create dialog to show classes
        dialog = QDialog(self)
        dialog.setWindowTitle("📋 Available Classes in Model")
        dialog.setMinimumSize(400, 500)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel(f"Model: {os.path.basename(self.prediction_manager.model_path)}")
        header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 12px;
                border-radius: 4px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Class list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        for class_id, class_name in classes.items():
            class_frame = QFrame()
            class_frame.setStyleSheet("""
                QFrame {
                    border: 1px solid #bdc3c7;
                    border-radius: 4px;
                    padding: 8px;
                    margin: 2px;
                    background-color: #f8f9fa;
                }
                QFrame:hover {
                    background-color: #e8f8ef;
                    border-color: #27ae60;
                }
            """)

            frame_layout = QHBoxLayout(class_frame)

            id_label = QLabel(f"ID: {class_id}")
            id_label.setStyleSheet("font-weight: bold; color: #2980b9; min-width: 60px;")

            name_label = QLabel(class_name)
            name_label.setStyleSheet("font-size: 12px;")

            frame_layout.addWidget(id_label)
            frame_layout.addWidget(name_label)
            frame_layout.addStretch()

            scroll_layout.addWidget(class_frame)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def open_assembly_folder(self):
        """Open the Assembly folder in file explorer"""
        if not self.assembly_folder or not os.path.exists(self.assembly_folder):
            # Try to get the Assembly folder path
            recipe_path = self.get_current_recipe_path()
            if recipe_path:
                self.assembly_folder = os.path.join(recipe_path, "Assembly")

        if not self.assembly_folder or not os.path.exists(self.assembly_folder):
            QMessageBox.warning(self, "⚠️ Assembly Folder Not Found",
                                "Assembly folder does not exist.\nIt will be created when you start capturing.")
            return

        try:
            import subprocess
            import platform

            system = platform.system()

            if system == "Windows":
                os.startfile(self.assembly_folder)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", self.assembly_folder])
            else:  # Linux
                subprocess.Popen(["xdg-open", self.assembly_folder])

        except Exception as e:
            QMessageBox.warning(self, "⚠️ Cannot Open Folder",
                                f"Failed to open folder: {str(e)}\n\n"
                                f"Path: {self.assembly_folder}")

    def open_capture_folder(self, folder_path):
        """Open a folder in file explorer"""
        if not folder_path or not os.path.exists(folder_path):
            QMessageBox.warning(self, "⚠️ Folder Not Found", "Folder does not exist.")
            return

        try:
            import subprocess
            import platform

            system = platform.system()

            if system == "Windows":
                os.startfile(folder_path)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", folder_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", folder_path])

        except Exception as e:
            QMessageBox.warning(self, "⚠️ Cannot Open Folder",
                                f"Failed to open folder: {str(e)}\n\n"
                                f"Path: {folder_path}")

    # def on_image_selected(self, product_id):
    #     """Handle image selection from gallery - just open camera viewer"""
    #     # Find the product
    #     product = None
    #     for p in self.available_products:
    #         if p['id'] == product_id:
    #             product = p
    #             break
    #
    #     if not product:
    #         return
    #
    #     # Show simple message and open camera
    #     reply = QMessageBox.question(
    #         self,
    #         f"View Camera?",
    #         f"Product: {product['name']}\n\nOpen camera to view this product?",
    #         QMessageBox.Yes | QMessageBox.No,
    #         QMessageBox.Yes
    #     )
    #
    #     if reply == QMessageBox.Yes:
    #         # Open simple camera viewer - pass just product, NOT step_number
    #         self.open_simple_camera_viewer(product)  # Fixed: removed step_number parameter

    def select_image_for_step(self, product_id):
        """Select image for the current step with auto capture and predict"""

        # ===== TRY TCP CONNECTION (NON-THREADED) =====
        # Just try to connect directly - it's fast enough
        try:
            self.ensure_tcp_connected()
        except Exception as e:
            print(f"⚠️ TCP connection attempt failed (non-critical): {e}")

        # Check if this product is already selected for a different step
        if product_id in self.selected_thumbnails.values():
            current_step = None
            for step, pid in self.selected_thumbnails.items():
                if pid == product_id:
                    current_step = step
                    break

            if current_step:
                reply = QMessageBox.question(
                    self, "⚠️ Product Already Selected",
                    f"This image is already selected for Step {current_step}.\n\n"
                    f"Do you want to reassign it to Step {self.current_active_step}?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.No:
                    return

                # Remove from previous step
                del self.step_selections[current_step]
                del self.selected_thumbnails[current_step]

                # Update the previous step display
                self.update_step_display(current_step, None)

                # Reset capture for previous step
                if current_step in self.step_widgets:
                    self.step_widgets[current_step]['capture_counter'] = 0
                    self.step_widgets[current_step]['capture_folder'] = None
                    self.update_capture_status(current_step, "No images captured")

                    # Disable capture and preview buttons
                    step_frame = self.step_widgets[current_step]['frame']
                    # capture_btn = step_frame.findChild(QPushButton, f"step_{current_step}_capture_btn")
                    # preview_btn = step_frame.findChild(QPushButton, f"step_{current_step}_preview_btn")
                    # if capture_btn:
                    #     capture_btn.setEnabled(False)
                    # if preview_btn:
                    #     preview_btn.setEnabled(False)

        # Find the product
        product = None
        for p in self.available_products:
            if p['id'] == product_id:
                product = p
                break

        if not product:
            return

        # Store selection for current step
        self.step_selections[self.current_active_step] = {
            'product_id': product_id,
            'product_data': {
                'name': product['name'],
                'original_name': product['original_name'],
                'image_path': product['image_path'],
                'filename': product['filename'],
                'annotation_path': product['relative_path'],
                'model_path': self.get_model_path(product_id),
                'trained': self.is_model_trained(product_id)
            }
        }

        # Update visual feedback
        self.update_step_display(self.current_active_step, product)
        self.update_thumbnail_selection(product_id, self.current_active_step)

        # Enable capture button for this step
        if self.current_active_step in self.step_widgets:
            step_frame = self.step_widgets[self.current_active_step]['frame']
            capture_btn = step_frame.findChild(QPushButton, f"step_{self.current_active_step}_capture_btn")
            if capture_btn:
                capture_btn.setEnabled(True)

        # ========== AUTO CAPTURE AND PREDICT ==========
        # Automatically start camera capture and prediction when product is selected
        QTimer.singleShot(500, lambda: self.auto_capture_and_predict_for_step(
            self.current_active_step,
            product['name'],
            product['id']
        ))

        # Move to next step if available
        if self.current_active_step < self.total_steps:
            self.current_active_step += 1
            self.update_step_indicator()
        else:
            # All steps have selections
            self.check_completion()

    def is_tcp_enabled(self):
        """Check if TCP functionality is enabled"""
        try:
            # You can add a setting in config_manager
            if hasattr(config_manager, 'is_tcp_enabled'):
                return config_manager.is_tcp_enabled()
        except:
            pass
        return True  # Enabled by default

    def auto_capture_and_predict_for_step(self, step_number, product_name, product_id):
        """Auto capture after product selection - DON'T save the image"""

        # Check if model is loaded
        if not self.prediction_manager.is_model_loaded():
            model_loaded = self.auto_load_product_model(product_id)
            if not model_loaded:
                QMessageBox.warning(
                    self,
                    "⚠️ No Model Found",
                    f"No trained model found for {product_name}.\n\n"
                    f"Please train a model first in the Deep Learning page."
                )
                return

        # Get the assembly folder
        assembly_folder = self.ensure_assembly_folder()
        if not assembly_folder:
            return

        # Create predictions subfolder
        predictions_folder = os.path.join(assembly_folder, "predictions")
        os.makedirs(predictions_folder, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Step_{step_number}_{timestamp}.bmp"

        self.prediction_status_label.setText(f"📸 Auto-capturing {product_name}...")

        # Create capture worker with save_image = FALSE
        self.capture_worker = CaptureWorker(
            assembly_folder,
            step_number,
            product_name,
            filename,
            save_image=False  # ← THIS WILL NOT SAVE
        )

        self.capture_worker.finished.connect(
            lambda success, msg, path: self.on_auto_capture_prediction_finished(
                step_number, product_name, product_id, success, msg, path
            )
        )

        self.capture_worker.start()

        # Show progress dialog
        self.progress_dialog = QProgressDialog(
            f"📸 Step {step_number}: Auto-capturing {product_name}\n\n"
            f"Camera will open automatically...\n"
            f"After capture, AI will detect objects in the image",
            "Cancel", 0, 0, self
        )
        self.progress_dialog.setWindowTitle("🤖 Auto Capture & Predict")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.cancel_capture)
        self.progress_dialog.show()

    def delete_captured_image_for_step(self, step_number):
        """Delete the captured BMP image for a specific step after successful prediction"""
        try:
            if step_number in self.step_widgets:
                current_image = self.step_widgets[step_number].get('current_image')
                if current_image and os.path.exists(current_image):
                    os.remove(current_image)
                    print(f"DEBUG: Deleted captured image for Step {step_number}: {current_image}")

                    # Update status to show no image
                    self.update_capture_status(step_number, "No images captured (auto-deleted)")

                    # Disable preview button since image is gone
                    step_frame = self.step_widgets[step_number]['frame']
                    # preview_btn = step_frame.findChild(QPushButton, f"step_{step_number}_preview_btn")
                    # if preview_btn:
                    #     preview_btn.setEnabled(False)

                    return True
        except Exception as e:
            print(f"DEBUG: Error deleting captured image for Step {step_number}: {e}")
        return False

    def delete_file_if_exists(self, file_path):
        """Delete file if it exists"""
        import os
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Deleted temporary file: {file_path}")
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")

    def cleanup_temp_dir(self, temp_dir):
        """Clean up temporary directory"""
        import shutil
        import os
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            print(f"Error cleaning up temp dir {temp_dir}: {e}")

    def auto_load_product_model(self, product_id):
        """Auto-load the latest trained model for a specific product"""
        try:
            # Get the recipe's yolo_model folder
            recipe_path = self.get_current_recipe_path()
            if not recipe_path:
                return False

            yolo_model_folder = os.path.join(recipe_path, "yolo_model")
            if not os.path.exists(yolo_model_folder):
                return False

            # Find all .pt files that might be related to this product
            model_files = []
            for root, dirs, files in os.walk(yolo_model_folder):
                for file in files:
                    if file.lower().endswith('.pt') and product_id.lower() in file.lower():
                        full_path = os.path.join(root, file)
                        model_files.append(full_path)

            # If no specific product model, get the latest best.pt
            if not model_files:
                for root, dirs, files in os.walk(yolo_model_folder):
                    for file in files:
                        if file.lower() == 'best.pt' or 'best' in file.lower():
                            full_path = os.path.join(root, file)
                            model_files.append(full_path)

            if not model_files:
                return False

            # Sort by modification time (newest first)
            model_files.sort(key=os.path.getmtime, reverse=True)
            latest_model = model_files[0]

            # Load the model
            success, message = self.prediction_manager.load_model(latest_model)

            if success:
                model_name = os.path.basename(latest_model)
                self.model_status_label.setText(f"✅ Auto-loaded: {model_name}")
                return True
            else:
                return False

        except Exception as e:
            print(f"Error auto-loading model: {e}")
            return False

    def start_auto_capture_prediction(self, step_number, product_name, product_id, block_folder, filename):
        """Start camera capture and automatically run prediction on captured image"""

        # Create capture worker with the filename
        self.capture_worker = CaptureWorker(block_folder, step_number, product_name, filename)

        # Connect to handle capture completion and then run prediction
        self.capture_worker.finished.connect(
            lambda success, msg, path: self.on_auto_capture_prediction_finished(
                step_number, product_name, product_id, success, msg, path
            )
        )

        # Start capture
        self.capture_worker.start()

        # Show progress dialog with prediction info
        self.progress_dialog = QProgressDialog(
            f"📸 Step {step_number}: Auto-capturing {product_name}\n\n"
            f"Camera will open automatically...\n"
            f"After capture, AI will detect objects in the image",
            "Cancel", 0, 0, self
        )
        self.progress_dialog.setWindowTitle("🤖 Auto Capture & Predict")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.cancel_capture)
        self.progress_dialog.show()

    def on_auto_capture_prediction_finished(self, step_number, product_name, product_id, success, message, image_path):
        """Handle auto-capture completion - image is temporary, will be cleaned up"""

        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()

        if success and image_path:
            # DON'T save the image path in step_widgets since it's temporary
            # Just store a reference for prediction
            self.step_widgets[step_number]['temp_image'] = image_path

            # Update capture status (but note it's temporary)
            self.update_capture_status(step_number, "Image captured (temporary)")

            # Enable preview button? Maybe not for temp files
            step_frame = self.step_widgets[step_number]['frame']
            # preview_btn = step_frame.findChild(QPushButton, f"step_{step_number}_preview_btn")
            # if preview_btn:
            #     preview_btn.setEnabled(False)  # Disable preview for temp files

            # Update status
            self.prediction_status_label.setText(f"🔍 Detecting objects...")

            # Run prediction on the temporary image
            self.run_auto_prediction_on_captured(step_number, product_name, product_id, image_path)

            # Optional: Schedule temp file cleanup after prediction
            QTimer.singleShot(10000, lambda: self.cleanup_temp_file(image_path))  # Delete after 10 seconds

        else:
            QMessageBox.warning(
                self,
                "❌ Capture Failed",
                f"Failed to capture image for Step {step_number}: {message}"
            )
            self.update_capture_status(step_number, "Capture failed")

    def cleanup_temp_file(self, file_path):
        """Clean up temporary file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"DEBUG: Cleaned up temp file: {file_path}")
        except Exception as e:
            print(f"DEBUG: Error cleaning up temp file: {e}")

    def get_class_id_from_product_name(self, product_name):
        """Get the class ID from the model based on product name"""
        try:
            if self.prediction_manager.is_model_loaded():
                model = self.prediction_manager.model
                if hasattr(model, 'names'):
                    # Search for product name in model classes
                    for class_id, class_name in model.names.items():
                        if product_name.lower() in class_name.lower():
                            return class_id
            return None
        except Exception as e:
            print(f"Error getting class ID: {e}")
            return None

    def run_auto_prediction_on_captured(self, step_number, product_name, product_id, image_path):
        """Run prediction on captured image with class filter"""

        if not self.prediction_manager.is_model_loaded():
            self.prediction_status_label.setText("⚠️ No model loaded for prediction")
            return

        # Show prediction status
        self.prediction_status_label.setText(f"🔍 Detecting {product_name}")

        # Create progress dialog
        predict_dialog = QProgressDialog(
            f"🔍 Step {step_number}: Detecting {product_name}",
            "Cancel", 0, 100, self
        )
        predict_dialog.setWindowTitle("🤖 AI Detection")
        predict_dialog.setWindowModality(Qt.WindowModal)
        predict_dialog.setAutoClose(True)
        predict_dialog.show()

        # ===== IMPROVED CLASS FILTERING =====
        class_id = None

        # Try to get class ID from product name
        class_id = self.prediction_manager.get_class_id_by_name(product_name)

        # If still no match, try to extract just the letter part
        if class_id is None and '_' in product_name:
            letter_part = product_name.split('_')[-1]
            print(f"DEBUG: Trying to match just the letter: '{letter_part}'")
            class_id = self.prediction_manager.get_class_id_by_name(letter_part)

        # Log what we're detecting
        if class_id is not None:
            class_name = "unknown"
            if self.prediction_manager.current_model and hasattr(self.prediction_manager.current_model, 'names'):
                class_name = self.prediction_manager.current_model.names.get(class_id, f"class_{class_id}")

            print(f"DEBUG: 🔍 Detecting ONLY class {class_id} ({class_name}) for product '{product_name}'")
            self.prediction_status_label.setText(f"🔍 Detecting {class_name}")
        else:
            print(f"DEBUG: 🔍 Detecting ALL objects (no class filter) for product '{product_name}'")
            self.prediction_status_label.setText(f"🔍 Detecting all objects")

        # Run prediction in background thread
        thread = threading.Thread(
            target=self._run_prediction_thread,
            args=(step_number, product_name, product_id, image_path, class_id, predict_dialog),
            daemon=True
        )
        thread.start()

    def _run_prediction_thread(self, step_number, product_name, product_id, image_path, class_filter, progress_dialog):
        """Run prediction in background thread"""
        try:
            print(f"DEBUG: _run_prediction_thread started for step {step_number}")

            def progress_callback(progress, status):
                # Use QTimer for UI updates from background thread
                QTimer.singleShot(0, lambda: self._update_prediction_progress(
                    progress_dialog, progress, status
                ))

            print(f"DEBUG: Running prediction with class filter: {class_filter}")

            # Run prediction with class filter
            success, message, predictions, output_path = self.prediction_manager.predict_image(
                image_path,
                class_filter=class_filter,
                progress_callback=progress_callback,
                conf_threshold=0.25
            )

            print(
                f"DEBUG: Prediction completed - Success: {success}, Predictions: {len(predictions) if predictions else 0}")
            print(f"DEBUG: Output path: {output_path}")

            # EMIT SIGNALS instead of using QTimer - this is guaranteed to work cross-thread
            if success:
                print(f"DEBUG: 🟢 SUCCESS - Emitting prediction_success signal")
                self.prediction_success.emit(
                    step_number, product_name, predictions, output_path, message, progress_dialog
                )
            else:
                print(f"DEBUG: 🔴 FAILED - Emitting prediction_failed signal")
                self.prediction_failed.emit(
                    step_number, product_name, message, progress_dialog
                )

        except Exception as e:
            print(f"DEBUG: Prediction thread error: {e}")
            import traceback
            traceback.print_exc()
            self.prediction_failed.emit(
                step_number, product_name, f"Error: {str(e)}", progress_dialog
            )

    def _call_prediction_success_safe(self, step_number, product_name, predictions, output_path, message,
                                      progress_dialog):
        """Safely call _on_prediction_success with error handling"""
        try:
            print(
                f"🔵🔵🔵 _call_prediction_success_safe: ABOUT TO CALL _on_prediction_success for step {step_number} 🔵🔵🔵")
            self._on_prediction_success(step_number, product_name, predictions, output_path, message, progress_dialog)
            print(
                f"🟢🟢🟢 _call_prediction_success_safe: SUCCESSFULLY CALLED _on_prediction_success for step {step_number} 🟢🟢🟢")
        except Exception as e:
            print(f"🔴🔴🔴 ERROR in _call_prediction_success_safe: {e} 🔴🔴🔴")
            import traceback
            traceback.print_exc()

            # Try to show error message
            try:
                QMessageBox.critical(
                    self,
                    "Error Showing Results",
                    f"Failed to show prediction results:\n\n{str(e)}"
                )
            except:
                pass

    def _update_prediction_progress(self, progress_dialog, progress, status):
        """Update prediction progress dialog"""
        try:
            if progress_dialog and progress_dialog.isVisible():
                progress_dialog.setValue(progress)
                progress_dialog.setLabelText(f"{status}...")

                # Auto-close at 100%
                if progress >= 100:
                    QTimer.singleShot(500, lambda: self._safe_close_dialog(progress_dialog))
        except Exception as e:
            print(f"DEBUG: Error updating progress: {e}")

    def _safe_close_dialog(self, dialog):
        """Safely close a dialog"""
        try:
            if dialog and dialog.isVisible():
                dialog.close()
                dialog.deleteLater()
        except:
            pass

    def _on_prediction_success(self, step_number, product_name, predictions, output_path, message, progress_dialog):
        """Handle successful prediction"""

        # Close progress dialog
        if progress_dialog:
            try:
                progress_dialog.close()
                progress_dialog.deleteLater()
            except:
                pass

        # Update UI
        if step_number in self.step_widgets:
            step_frame = self.step_widgets[step_number]['frame']
            display_label = step_frame.findChild(QLabel, f"step_{step_number}_display")
            if display_label:
                if predictions:
                    display_label.setText(f"✅ {product_name}\n✓ {len(predictions)} detected")
                else:
                    display_label.setText(f"⚠️ {product_name}\n❌ No objects")

        # SEND COORDINATES (with calibration applied)
        if predictions:
            # Show calibration status
            if self.calibration.is_calibrated:
                print(f"📐 Using WORLD coordinates from calibration")
            else:
                print(f"📷 Using PIXEL coordinates (no calibration)")

            # Send coordinates
            QTimer.singleShot(100, lambda: self.send_coordinates_to_server(predictions))

        # Show results dialog
        try:
            if step_number in self.step_selections:
                product_data = self.step_selections[step_number]['product_data']
                product = {
                    'name': product_data['name'],
                    'image_path': product_data['image_path'],
                    'filename': product_data['filename']
                }
                self.show_prediction_results_view(step_number, product, predictions, output_path, None)
        except Exception as e:
            print(f"Error showing results: {e}")

    def send_coordinates_to_server(self, predictions):
        """Send coordinates to server using heartbeat manager"""
        if not AssemblyDialog._heartbeat_manager or not AssemblyDialog._heartbeat_manager.is_connected():
            print("⚠️ Heartbeat manager not connected - attempting to reconnect...")
            self._ensure_heartbeat_connected()

            if not AssemblyDialog._heartbeat_manager or not AssemblyDialog._heartbeat_manager.is_connected():
                return False

        try:
            # Build coordinate string (same as before)
            coordinate_lines = []
            for i, pred in enumerate(predictions):
                bbox = pred.get('bbox', [0, 0, 0, 0])
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox[:4]

                    # ... coordinate conversion logic (unchanged) ...

                    # Build coordinate line
                    if self.calibration.is_calibrated:
                        # Convert to world coordinates (your existing logic)
                        world_corners = self._convert_to_world_coordinates([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])
                        coord_line = (f"{world_corners[0][0]:.2f}_{world_corners[0][1]:.2f},"
                                      f"{world_corners[1][0]:.2f}_{world_corners[1][1]:.2f},"
                                      f"{world_corners[2][0]:.2f}_{world_corners[2][1]:.2f},"
                                      f"{world_corners[3][0]:.2f}_{world_corners[3][1]:.2f}")
                    else:
                        coord_line = (f"{x1:.2f}_{y1:.2f},"
                                      f"{x2:.2f}_{y1:.2f},"
                                      f"{x2:.2f}_{y2:.2f},"
                                      f"{x1:.2f}_{y2:.2f}")

                    coordinate_lines.append(coord_line)

            if not coordinate_lines:
                return False

            # Send using heartbeat manager
            message = "\n".join(coordinate_lines) + "\n"
            success = AssemblyDialog._heartbeat_manager.send_data(message)

            if success:
                print(f"✅ Sent {len(coordinate_lines)} coordinate sets via heartbeat")
                self.update_tcp_messages(f"📤 Sent {len(coordinate_lines)} coordinate sets")
                return True
            else:
                print("❌ Failed to send coordinates")
                return False

        except Exception as e:
            print(f"❌ Error sending coordinates: {e}")
            return False

    def _convert_to_world_coordinates(self, pixel_corners):
        """Helper method to convert pixel corners to world coordinates"""
        world_corners = []
        for corner in pixel_corners:
            world_point = self.calibration.pixel_to_world(corner)
            if world_point:
                world_corners.append(world_point)
            else:
                world_corners.append(corner)  # Fallback to pixel
        return world_corners

    def _fallback_show_results(self, step_number, product, predictions, output_path, captured_path, product_name):
        """Fallback method to show results if direct call fails"""
        try:
            print(f"🟡 _fallback_show_results called for step {step_number}")

            if product:
                self.show_prediction_results_view(
                    step_number,
                    product,
                    predictions,
                    output_path,
                    captured_path
                )
            else:
                self.show_prediction_image_only(
                    output_path,
                    captured_path,
                    step_number,
                    product_name,
                    predictions
                )
            print(f"✅ _fallback_show_results completed")
        except Exception as e:
            print(f"🔴 _fallback_show_results failed: {e}")
            QMessageBox.information(
                self,
                "Detection Complete",
                f"Step {step_number}: {product_name}\n"
                f"Detected {len(predictions)} objects.\n"
                f"Image saved to: {output_path}"
            )

    def _show_results_dialog(self, step_number, product, predictions, output_path, captured_path):
        """Helper method to show results dialog - ensures it runs in main thread"""
        print(f"DEBUG: _show_results_dialog called for step {step_number}")

        if product:
            self.show_prediction_results_view(
                step_number,
                product,
                predictions,
                output_path,
                captured_path
            )
        else:
            self.show_prediction_image_only(
                output_path,
                captured_path,
                step_number,
                product['name'] if product else "Unknown",
                predictions
            )

    def show_prediction_image_only(self, output_path, captured_path, step_number, product_name, predictions):
        """Show just the prediction image if product reference is not available"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"🔍 Step {step_number}: {product_name} - Detection Result")
        dialog.setMinimumSize(1000, 1000)

        layout = QVBoxLayout(dialog)

        # Header
        if predictions:
            header = QLabel(f"✅ Detection Complete - Found {len(predictions)} Object(s)")
            header.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: white;
                    background-color: #27ae60;
                    padding: 12px;
                    border-radius: 4px;
                }
            """)
        else:
            header = QLabel(f"⚠️ No Objects Detected")
            header.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: white;
                    background-color: #e67e22;
                    padding: 12px;
                    border-radius: 4px;
                }
            """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Image display
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setMinimumHeight(400)
        image_label.setStyleSheet("""
            QLabel {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 10px;
            }
        """)

        # Show the predicted image
        if output_path and os.path.exists(output_path):
            pixmap = QPixmap(output_path)
        elif captured_path and os.path.exists(captured_path):
            pixmap = QPixmap(captured_path)
        else:
            pixmap = None

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(700, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(scaled)
        else:
            image_label.setText("❌ Cannot load prediction image")

        layout.addWidget(image_label)

        # Results info
        if predictions:
            info_text = f"📊 Detection Results:\n\n"
            info_text += f"• Total objects: {len(predictions)}\n"

            # Group by class
            class_counts = {}
            confidences = []
            for p in predictions:
                class_name = p.get('class_name', 'unknown')
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
                confidences.append(p.get('confidence', 0))

            for class_name, count in class_counts.items():
                info_text += f"• {class_name}: {count}\n"

            if confidences:
                avg_conf = sum(confidences) / len(confidences)
        else:
            info_text = "❌ No objects were detected in the image.\n\n"
            info_text += "Try adjusting lighting or camera angle."

        info_label = QLabel(info_text)
        info_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 4px;
                margin: 10px 0;
                font-family: monospace;
            }
        """)
        info_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(info_label)

        # Buttons
        button_layout = QHBoxLayout()

        # # Open folder button
        # if output_path:
        #     folder_btn = QPushButton("📂 Open Predictions Folder")
        #     folder_btn.clicked.connect(lambda: self.open_prediction_folder(output_path))
        #     button_layout.addWidget(folder_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px 16px;
                background-color: #95a5a6;
                color: white;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    def show_prediction_results_view(self, step_number, product, predictions, output_path, captured_path):
        """Show side-by-side comparison of reference and detected image"""

        dialog = QDialog(self)
        dialog.setWindowTitle(f"✅ Step {step_number}: {product['name']} - Detection Results")
        dialog.setMinimumSize(1100, 600)
        dialog.setModal(True)  # Make it modal

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)

        # Header with status
        if predictions:
            header = QLabel(f"✅ SUCCESS: Detected {len(predictions)} {product['name']}(s)")
            header.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: white;
                    background-color: #27ae60;
                    padding: 15px;
                    border-radius: 6px;
                }
            """)
        else:
            header = QLabel(f"⚠️ No {product['name']} detected")
            header.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: white;
                    background-color: #e67e22;
                    padding: 15px;
                    border-radius: 6px;
                }
            """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Splitter for side-by-side view
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #bdc3c7;
                width: 2px;
            }
        """)

        # ===== LEFT: Reference product =====
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(10)

        left_title = QLabel("📋 Reference Product")
        left_title.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #ecf0f1;
                border-radius: 4px;
            }
        """)
        left_title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(left_title)

        # Reference image
        ref_label = QLabel()
        ref_label.setAlignment(Qt.AlignCenter)
        ref_label.setMinimumSize(400, 350)
        ref_label.setStyleSheet("""
            QLabel {
                border: 2px solid #3498db;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 10px;
            }
        """)

        try:
            pixmap = QPixmap(product['image_path'])
            if not pixmap.isNull():
                scaled = pixmap.scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                ref_label.setPixmap(scaled)
        except Exception as e:
            ref_label.setText(f"❌ Cannot load reference\n{str(e)}")

        left_layout.addWidget(ref_label)

        # Product info
        product_info = QLabel(f"📄 {product['filename']}")
        product_info.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #7f8c8d;
                padding: 8px;
                background-color: #f8f9fa;
                border-radius: 4px;
                font-family: monospace;
            }
        """)
        product_info.setAlignment(Qt.AlignCenter)
        product_info.setWordWrap(True)
        left_layout.addWidget(product_info)
        left_layout.addStretch()

        # ===== RIGHT: Captured + Detection =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(10)

        right_title = QLabel("🤖 AI Detection Result")
        right_title.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #ecf0f1;
                border-radius: 4px;
            }
        """)
        right_title.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(right_title)

        # Detection image
        cap_label = QLabel()
        cap_label.setAlignment(Qt.AlignCenter)
        cap_label.setMinimumSize(400, 350)
        cap_label.setStyleSheet("""
            QLabel {
                border: 2px solid #27ae60;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 10px;
            }
        """)

        # Use prediction output if available, otherwise use captured image
        display_path = None
        if output_path and os.path.exists(output_path):
            display_path = output_path
        elif captured_path and os.path.exists(captured_path):
            display_path = captured_path

        if display_path:
            try:
                pixmap = QPixmap(display_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(450, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    cap_label.setPixmap(scaled)
            except:
                cap_label.setText("❌ Cannot load image")
        else:
            cap_label.setText("❌ No image available")

        right_layout.addWidget(cap_label)

        # Detection info
        if predictions:
            # Calculate statistics
            confidences = [p['confidence'] for p in predictions]
            avg_conf = sum(confidences) / len(confidences)
            best_conf = max(confidences)

            # Group by class
            class_counts = {}
            for p in predictions:
                class_name = p.get('class_name', 'unknown')
                class_counts[class_name] = class_counts.get(class_name, 0) + 1

            info_text = "📊 DETECTION SUMMARY\n"
            info_text += "═" * 40 + "\n\n"
            info_text += f"✅ Total objects: {len(predictions)}\n"

            for class_name, count in class_counts.items():
                info_text += f"   • {class_name}: {count}\n"

        else:
            info_text = "❌ NO OBJECTS DETECTED\n"
            info_text += "═" * 40 + "\n\n"
            info_text += "• Image was captured successfully\n"
            info_text += "• No matching objects were found\n\n"
            info_text += "💡 Tips:\n"
            info_text += "• Adjust lighting conditions\n"
            info_text += "• Try different camera angle\n"
            info_text += "• Check if model is trained for this object"

        info_label = QLabel(info_text)
        info_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 6px;
                margin-top: 10px;
                font-family: 'Courier New', monospace;
                line-height: 1.5;
            }
        """)
        info_label.setAlignment(Qt.AlignLeft)
        info_label.setWordWrap(True)
        right_layout.addWidget(info_label)
        right_layout.addStretch()

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([500, 600])

        layout.addWidget(splitter, 1)  # Give the splitter stretch

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)

        # # Open folder button
        # if output_path:
        #     open_btn = QPushButton("📂 Open Predictions Folder")
        #     open_btn.setStyleSheet("""
        #         QPushButton {
        #             font-size: 13px;
        #             font-weight: bold;
        #             padding: 12px 24px;
        #             background-color: #3498db;
        #             color: white;
        #             border-radius: 6px;
        #             min-width: 200px;
        #         }
        #         QPushButton:hover {
        #             background-color: #2980b9;
        #         }
        #     """)
        #     open_btn.clicked.connect(lambda: self.open_prediction_folder(output_path))
        #     button_layout.addWidget(open_btn)

        # Done button
        done_btn = QPushButton("✓ Done")
        done_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                padding: 12px 24px;
                background-color: #27ae60;
                color: white;
                border-radius: 6px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        done_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(done_btn)

        layout.addLayout(button_layout)

        # Show the dialog
        dialog.exec()

    def _on_prediction_failed(self, step_number, product_name, message, progress_dialog):
        """Handle failed prediction"""
        if progress_dialog:
            try:
                progress_dialog.close()
                progress_dialog.deleteLater()
            except:
                pass

        self.prediction_status_label.setText(f"❌ Step {step_number}: Prediction failed")
        self.prediction_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #e74c3c;
                padding: 6px;
                background-color: #ffebee;
                border-radius: 3px;
            }
        """)

        QMessageBox.warning(
            self,
            f"❌ Prediction Failed - Step {step_number}",
            f"Failed to detect {product_name}:\n\n{message}"
        )

    def show_prediction_capture_notification(self, step_number, product_name, num_detections, output_path):
        """Show success notification with auto-close"""
        notification = QMessageBox(self)
        notification.setWindowTitle(f"✅ Step {step_number} - Auto Capture & Predict Complete")
        notification.setIcon(QMessageBox.Information)

        if num_detections > 0:
            notification.setText(f"Successfully captured and detected {product_name}!")
            notification.setInformativeText(
                f"📸 Image captured\n"
                f"🔍 Detected {num_detections} object(s)\n"
                f"🎯 Confidence: {self.get_detection_confidence(output_path):.1%}\n\n"
                f"Results saved to predictions/ folder"
            )
        else:
            notification.setText(f"Image captured, but no {product_name} detected")
            notification.setInformativeText(
                f"📸 Image saved to Assembly folder\n"
                f"⚠️ No objects of type '{product_name}' were found\n\n"
                f"You can check the image using the Preview button"
            )

        notification.setStandardButtons(QMessageBox.Ok)

        # Auto-close after 3 seconds
        QTimer.singleShot(3000, notification.accept)
        notification.exec()

    def get_detection_confidence(self, output_path):
        """Get the highest confidence from prediction results"""
        try:
            # This is a placeholder - you might want to extract this from the prediction results
            return 0.85
        except:
            return 0.0

    def update_prediction_preview(self, predictions, output_path):
        """Update the prediction preview in the UI"""
        if not hasattr(self, 'prediction_preview_layout'):
            print("DEBUG: prediction_preview_layout not found, skip preview update")
            return

        try:
            while self.prediction_preview_layout.count():
                child = self.prediction_preview_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            if output_path and os.path.exists(output_path):
                pixmap = QPixmap(output_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(
                        300, 200,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    image_label = QLabel()
                    image_label.setPixmap(scaled_pixmap)
                    image_label.setAlignment(Qt.AlignCenter)
                    image_label.setStyleSheet("""
                        QLabel {
                            border: 2px solid #bdc3c7;
                            border-radius: 6px;
                            background-color: #f8f9fa;
                            padding: 5px;
                            margin-bottom: 5px;
                        }
                    """)
                    self.prediction_preview_layout.addWidget(image_label, alignment=Qt.AlignCenter)
                else:
                    raise Exception("Cannot load image")
            else:
                placeholder = QLabel("No prediction image available")
                placeholder.setAlignment(Qt.AlignCenter)
                placeholder.setStyleSheet("""
                    QLabel {
                        font-size: 12px;
                        color: #7f8c8d;
                        padding: 50px;
                        font-style: italic;
                    }
                """)
                self.prediction_preview_layout.addWidget(placeholder)

            if predictions:
                count_label = QLabel(f"Detected: {len(predictions)} objects")
                count_label.setAlignment(Qt.AlignCenter)
                count_label.setStyleSheet("""
                    QLabel {
                        font-size: 12px;
                        color: #27ae60;
                        padding: 5px;
                        font-weight: bold;
                        background-color: #e8f8ef;
                        border-radius: 3px;
                        margin-top: 5px;
                    }
                """)
                self.prediction_preview_layout.addWidget(count_label)

        except Exception as e:
            print(f"Error updating prediction preview: {e}")

    def closeEvent(self, event):
        """Clean up on dialog close"""
        if self.capture_worker and self.capture_worker.isRunning():
            self.capture_worker.stop()
            self.capture_worker.quit()
            self.capture_worker.wait()

        if self.is_predicting:
            self.cancel_prediction()

        # Close assembly tool window if open
        if self.assembly_tool_window and self.assembly_tool_window.isVisible():
            self.assembly_tool_window.close()

        # Disconnect TCP when user closes dialog
        self.disconnect_tcp()  # ← ADD THIS LINE

        event.accept()

    def disconnect_tcp(self):
        """Manually disconnect TCP connection"""
        if hasattr(AssemblyDialog, '_global_tcp_socket') and AssemblyDialog._global_tcp_socket:
            try:
                AssemblyDialog._global_tcp_socket.close()
                print("🔌 TCP connection closed by user")
            except:
                pass
            AssemblyDialog._global_tcp_socket = None

        self.tcp_socket = None
        self.tcp_connected = False

        # Update UI
        if hasattr(self, 'tcp_status_label'):
            self.tcp_status_label.setText("🔴 TCP: Disconnected")
            self.tcp_status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #e74c3c;
                    padding: 6px;
                    background-color: #ffebee;
                    border-radius: 3px;
                }
            """)

        self.update_tcp_messages("🔌 TCP disconnected by user")

    def update_step_display(self, step_number, product):
        """Update the display for a specific step"""
        if step_number not in self.step_widgets:
            return

        step_frame = self.step_widgets[step_number]['frame']

        # Find the display label
        display_label = step_frame.findChild(QLabel, f"step_{step_number}_display")
        if display_label:
            if product:
                display_text = f"✅ {product['name']}\n"
                display_text += f"📄 {product['filename']}"

                display_label.setText(display_text)
                display_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 8px;
                        background-color: #e8f8ef;
                        border-radius: 4px;
                        min-height: 40px;
                        font-weight: bold;
                    }
                """)

                # Update step frame appearance
                step_frame.setStyleSheet("""
                    QFrame {
                        border: 2px solid #2ecc71;
                        border-radius: 8px;
                        background-color: #e8f8ef;
                        padding: 12px;
                    }
                """)
            else:
                display_label.setText("⏳ Not selected yet")
                display_label.setStyleSheet("""
                    QLabel {
                        font-size: 12px;
                        color: #7f8c8d;
                        padding: 8px;
                        background-color: #ecf0f1;
                        border-radius: 4px;
                        min-height: 40px;
                    }
                """)

                if step_number == self.current_active_step:
                    step_frame.setStyleSheet("""
                        QFrame {
                            border: 3px solid #3498db;
                            border-radius: 8px;
                            background-color: #e3f2fd;
                            padding: 12px;
                        }
                    """)
                else:
                    step_frame.setStyleSheet("""
                        QFrame {
                            border: 2px solid #bdc3c7;
                            border-radius: 8px;
                            background-color: #f8f9fa;
                            padding: 12px;
                        }
                    """)

    def update_step_indicator(self):
        """Update the current step indicator"""
        self.step_indicator.setText(f"👉 Currently selecting for: Step {self.current_active_step}")

    def set_active_step(self, step_number):
        """Set which step is currently active for selection"""
        if step_number > self.total_steps:
            return

        self.current_active_step = step_number
        self.update_step_indicator()

        # Update all step frames
        for step, data in self.step_widgets.items():
            step_frame = data['frame']
            if step == step_number:
                if step in self.step_selections:
                    step_frame.setStyleSheet("""
                        QFrame {
                            border: 3px solid #3498db;
                            border-radius: 8px;
                            background-color: #e8f8ef;
                            padding: 12px;
                        }
                    """)
                else:
                    step_frame.setStyleSheet("""
                        QFrame {
                            border: 3px solid #3498db;
                            border-radius: 8px;
                            background-color: #e3f2fd;
                            padding: 12px;
                        }
                    """)
            elif step in self.step_selections:
                step_frame.setStyleSheet("""
                    QFrame {
                        border: 2px solid #2ecc71;
                        border-radius: 8px;
                        background-color: #e8f8ef;
                        padding: 12px;
                    }
                """)
            else:
                step_frame.setStyleSheet("""
                    QFrame {
                        border: 2px solid #bdc3c7;
                        border-radius: 8px;
                        background-color: #f8f9fa;
                        padding: 12px;
                    }
                """)

    # def on_step_count_changed(self, value):
    #     """Handle change in total steps"""
    #     old_total = self.total_steps
    #     self.total_steps = value
    #
    #     # Clear existing step widgets
    #     while self.steps_layout.count():
    #         child = self.steps_layout.takeAt(0)
    #         if child.widget():
    #             child.widget().deleteLater()
    #
    #     self.step_widgets = {}
    #
    #     # Clear selections for removed steps
    #     steps_to_remove = []
    #     for step in self.step_selections:
    #         if step > value:
    #             steps_to_remove.append(step)
    #
    #     for step in steps_to_remove:
    #         if step in self.selected_thumbnails:
    #             del self.selected_thumbnails[step]
    #         del self.step_selections[step]
    #
    #     # Create new step widgets
    #     for step in range(1, value + 1):
    #         self.create_step_widget(step)
    #
    #         # Restore existing selections if any
    #         if step in self.step_selections:
    #             product_id = self.step_selections[step]['product_id']
    #             # Find the product
    #             for product in self.available_products:
    #                 if product['id'] == product_id:
    #                     self.update_step_display(step, product)
    #                     self.update_thumbnail_selection(product_id, step)
    #
    #                     # Enable capture button
    #                     step_frame = self.step_widgets[step]['frame']
    #                     capture_btn = step_frame.findChild(QPushButton, f"step_{step}_capture_btn")
    #                     if capture_btn:
    #                         capture_btn.setEnabled(True)
    #                     break
    #
    #     # Adjust current active step if needed
    #     if self.current_active_step > value:
    #         self.current_active_step = value
    #
    #     self.update_step_indicator()
    #     self.check_completion()

    def check_completion(self):
        """Check if all steps have selections"""
        all_selected = all(step in self.step_selections for step in range(1, self.total_steps + 1))
        self.ok_btn.setEnabled(all_selected)

    def get_current_recipe_info(self):
        """Get information about current recipe"""
        try:
            if hasattr(config_manager, 'current_recipe'):
                recipe_id = config_manager.current_recipe
                recipe_name = getattr(config_manager, 'current_recipe_name', f'Recipe {recipe_id}')
                return f"{recipe_name} (ID: {recipe_id})"
        except:
            pass
        return "No recipe selected"

    def get_annotation_folder_path(self):
        """Get the Annotation folder path within current recipe"""
        recipe_path = self.get_current_recipe_path()

        if not recipe_path or not os.path.exists(recipe_path):
            return None

        # Check for exact "Annotation" folder
        annotation_path = os.path.join(recipe_path, "Annotation")
        if os.path.exists(annotation_path) and os.path.isdir(annotation_path):
            return annotation_path

        # Search for folders containing "annotation" in name (case-insensitive)
        annotation_folders = []
        try:
            for item in os.listdir(recipe_path):
                item_path = os.path.join(recipe_path, item)
                if os.path.isdir(item_path) and "annotation" in item.lower():
                    annotation_folders.append(item_path)
        except:
            pass

        # Return the first found annotation folder
        if annotation_folders:
            return annotation_folders[0]

        return None

    def load_bmp_from_annotation(self):
        """Load BMP images specifically from Annotation folder"""
        try:
            self.available_products = []
            self.thumbnail_widgets = {}

            # Get annotation folder path
            self.annotation_folder = self.get_annotation_folder_path()

            if not self.annotation_folder:
                QMessageBox.warning(self, "⚠️ Annotation Folder Not Found",
                                    "The 'Annotation' folder was not found in the current recipe.\n\n"
                                    f"Current recipe: {self.get_current_recipe_path()}\n\n"
                                    "Please ensure there is an 'Annotation' folder containing BMP images.")
                self.update_gallery()
                return

            # Search for BMP files in annotation folder
            bmp_files = []
            search_patterns = [
                os.path.join(self.annotation_folder, "**", "*.bmp"),
                os.path.join(self.annotation_folder, "**", "*.BMP"),
                os.path.join(self.annotation_folder, "*.bmp"),
                os.path.join(self.annotation_folder, "*.BMP"),
            ]

            for pattern in search_patterns:
                try:
                    files = glob.glob(pattern, recursive=True)
                    bmp_files.extend(files)
                except:
                    pass

            # Remove duplicates and sort
            bmp_files = list(set(bmp_files))
            bmp_files.sort()

            if not bmp_files:
                QMessageBox.information(self, "📭 No BMP Files",
                                        f"No BMP images found in Annotation folder:\n{self.annotation_folder}")
                self.update_gallery()
                return

            # Process found BMP files
            product_counter = {}
            for bmp_path in bmp_files:
                filename = os.path.basename(bmp_path)

                # Extract product name from filename
                base_name = os.path.splitext(filename)[0]

                # Try to get clean product name
                product_name = self.clean_product_name(base_name)

                # Count occurrences
                if product_name not in product_counter:
                    product_counter[product_name] = 0
                product_counter[product_name] += 1

                # Create unique product ID
                if product_counter[product_name] > 1:
                    product_id = f"{product_name}_{product_counter[product_name]}"
                else:
                    product_id = product_name

                # Get relative path
                try:
                    rel_path = os.path.relpath(bmp_path, self.annotation_folder)
                except:
                    rel_path = filename

                self.available_products.append({
                    'id': product_id,
                    'name': base_name,
                    'image_path': bmp_path,
                    'filename': filename,
                    'relative_path': rel_path,
                    'original_name': base_name
                })

            # Update UI
            self.update_gallery()

        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Failed to load annotation images: {str(e)}")

    def clean_product_name(self, filename):
        """Clean product name without destroying valid part numbers"""
        suffixes = ['_annotated', '_annotation', '_labeled', '_label', '_mask', '_bbox',
                    '_cropped', '_resized', '_processed', '_train', '_val', '_test']

        name = filename
        for suffix in suffixes:
            if name.lower().endswith(suffix.lower()):
                name = name[:-len(suffix)]
                break

        # Remove leading step index like "2_AN10-01" -> "AN10-01"
        name = re.sub(r'^\d+_', '', name)

        return name

    def update_gallery(self):
        """Update the BMP image gallery"""
        # Clear existing gallery
        while self.gallery_layout.count():
            child = self.gallery_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.thumbnail_widgets = {}

        if not self.available_products:
            # Show empty state
            if self.annotation_folder:
                empty_text = f"📭 No BMP images found in:\n{os.path.basename(self.annotation_folder)}"
            else:
                empty_text = "📭 No Annotation folder found"

            empty_label = QLabel(empty_text)
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    color: #95a5a6;
                    padding: 60px;
                    background-color: #f8f9fa;
                    border-radius: 8px;
                    font-weight: bold;
                }
            """)
            self.gallery_layout.addWidget(empty_label, 0, 0, 1, 4)
            return

        # Display BMP thumbnails in grid
        row = 0
        col = 0
        max_cols = 4

        for product in self.available_products:
            thumbnail_widget = self.create_thumbnail_widget(product)
            self.thumbnail_widgets[product['id']] = thumbnail_widget

            self.gallery_layout.addWidget(thumbnail_widget, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def create_thumbnail_widget(self, product):
        """Create a clickable thumbnail widget for a BMP product"""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Box)

        # Check if this product is already selected
        is_selected = product['id'] in self.selected_thumbnails.values()

        if is_selected:
            # Find which step it's selected for
            step_num = None
            for step, pid in self.selected_thumbnails.items():
                if pid == product['id']:
                    step_num = step
                    break

            widget.setStyleSheet(f"""
                QFrame {{
                    border: 4px solid #2ecc71;
                    border-radius: 8px;
                    background-color: #e8f8ef;
                    padding: 8px;
                }}
            """)
        else:
            widget.setStyleSheet("""
                QFrame {
                    border: 2px solid #dfe6e9;
                    border-radius: 8px;
                    background-color: white;
                    padding: 8px;
                }
                QFrame:hover {
                    border: 2px solid #3498db;
                    background-color: #f0f8ff;
                }
            """)

        widget.setCursor(Qt.PointingHandCursor)
        widget.setFixedSize(180, 200)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # BMP thumbnail
        thumbnail = QLabel()
        thumbnail.setAlignment(Qt.AlignCenter)
        thumbnail.setFixedSize(150, 100)

        # Load and display BMP
        try:
            pixmap = QPixmap(product['image_path'])
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    140, 90,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                thumbnail.setPixmap(scaled_pixmap)
                thumbnail.setStyleSheet("border: 1px solid #bdc3c7; border-radius: 4px;")
            else:
                thumbnail.setText("❌\nInvalid BMP")
                thumbnail.setStyleSheet("""
                    QLabel {
                        background-color: #ffebee;
                        color: #e74c3c;
                        font-size: 10px;
                        border: 1px dashed #ffcdd2;
                        border-radius: 4px;
                    }
                """)
        except:
            thumbnail.setText("⚠️\nLoad Error")
            thumbnail.setStyleSheet("""
                QLabel {
                    background-color: #fff3e0;
                    color: #f39c12;
                    font-size: 10px;
                    border: 1px dashed #ffeaa7;
                    border-radius: 4px;
                }
            """)

        # Product name
        name_label = QLabel(product['name'])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 12px;
                color: #2c3e50;
                padding: 2px;
            }
        """)
        name_label.setWordWrap(True)
        name_label.setToolTip(f"Original: {product['original_name']}")

        # File info
        file_label = QLabel(product['filename'])
        file_label.setAlignment(Qt.AlignCenter)
        file_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #7f8c8d;
                padding: 1px;
                font-family: monospace;
            }
        """)
        file_label.setWordWrap(True)

        # Status indicator
        status_label = QLabel(" ")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setFixedHeight(20)

        # If selected, show step number
        if is_selected:
            for step, pid in self.selected_thumbnails.items():
                if pid == product['id']:
                    status_label.setText(f"✓ Step {step}")
                    status_label.setStyleSheet("""
                        QLabel {
                            color: #27ae60;
                            font-weight: bold;
                            font-size: 11px;
                            background-color: #d5f4e6;
                            border-radius: 3px;
                            padding: 2px;
                        }
                    """)
                    break

        layout.addWidget(thumbnail)
        layout.addWidget(name_label)
        layout.addWidget(file_label)
        layout.addWidget(status_label)

        # NEW: This selects for step AND opens camera
        widget.mousePressEvent = lambda event, pid=product['id']: self.select_image_for_step(pid)

        return widget

    def update_thumbnail_selection(self, product_id, step_number):
        """Update thumbnail appearance when selected"""
        # Update selection tracking
        self.selected_thumbnails[step_number] = product_id

        # Update all thumbnails
        for pid, widget in self.thumbnail_widgets.items():
            layout = widget.layout()
            if layout and layout.count() >= 4:
                status_label = layout.itemAt(3).widget()

                if pid == product_id:
                    # This is the newly selected product
                    widget.setStyleSheet("""
                        QFrame {
                            border: 4px solid #2ecc71;
                            border-radius: 8px;
                            background-color: #e8f8ef;
                            padding: 8px;
                        }
                    """)
                    status_label.setText(f"✓ Step {step_number}")
                    status_label.setStyleSheet("""
                        QLabel {
                            color: #27ae60;
                            font-weight: bold;
                            font-size: 11px;
                            background-color: #d5f4e6;
                            border-radius: 3px;
                            padding: 2px;
                        }
                    """)
                elif pid in self.selected_thumbnails.values():
                    # This product is selected for a different step
                    for step, selected_pid in self.selected_thumbnails.items():
                        if selected_pid == pid:
                            widget.setStyleSheet(f"""
                                QFrame {{
                                    border: 3px solid #f39c12;
                                    border-radius: 8px;
                                    background-color: #fff9e6;
                                    padding: 8px;
                                }}
                            """)
                            status_label.setText(f"✓ Step {step}")
                            status_label.setStyleSheet("""
                                QLabel {
                                    color: #f39c12;
                                    font-weight: bold;
                                    font-size: 11px;
                                    background-color: #fff3cd;
                                    border-radius: 3px;
                                    padding: 2px;
                                }
                            """)
                            break
                else:
                    # Not selected
                    widget.setStyleSheet("""
                        QFrame {
                            border: 2px solid #dfe6e9;
                            border-radius: 8px;
                            background-color: white;
                            padding: 8px;
                        }
                        QFrame:hover {
                            border: 2px solid #3498db;
                            background-color: #f0f8ff;
                        }
                    """)
                    status_label.setText(" ")
                    status_label.setStyleSheet("")

    def get_current_recipe_path(self):
        """Get the path of current recipe folder"""
        try:
            if hasattr(config_manager, 'get_current_recipe_folder'):
                return config_manager.get_current_recipe_folder()
        except:
            pass

        # Try default path
        try:
            if hasattr(config_manager, 'current_recipe'):
                recipe_id = config_manager.current_recipe
                return os.path.join("recipes", str(recipe_id))
        except:
            pass

        return None

    def get_model_path(self, product_id):
        """Get model path for product"""
        try:
            if hasattr(config_manager, 'get_current_yolo_models_folder'):
                models_folder = config_manager.get_current_yolo_models_folder()
                return os.path.join(models_folder, f"{product_id}.pt")
        except:
            return ""

    def is_model_trained(self, product_id):
        """Check if model is trained"""
        model_path = self.get_model_path(product_id)
        return os.path.exists(model_path) if model_path else False

    def get_all_selections(self):
        """Get all step selections including capture info"""
        print(f"🔴🔴🔴 get_all_selections CALLED 🔴🔴🔴")

        try:
            result = {
                'block_id': str(self.block_id),
                'block_name': str(self.block_name),
                'total_steps': int(self.total_steps),
                'selections': {}
            }

            print(f"DEBUG: Building selections for steps: {list(self.step_selections.keys())}")

            for step, selection in self.step_selections.items():
                step_key = str(step)
                print(f"DEBUG: Processing step {step_key}")

                # Get capture info safely
                capture_info = {}
                if step in self.step_widgets:
                    capture_info = {
                        'capture_count': int(self.step_widgets[step].get('capture_counter', 0)),
                        'capture_folder': str(self.step_widgets[step].get('capture_folder', '')),
                        'assembly_folder': str(self.assembly_folder) if self.assembly_folder else '',
                        'block_id': str(self.block_id),
                        'block_name': str(self.block_name),
                        'current_image': str(self.step_widgets[step].get('current_image', '')) if self.step_widgets[
                            step].get('current_image') else ''
                    }

                # Get product data safely
                product_data = selection.get('product_data', {})

                # Build selection dictionary
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

            print(f"DEBUG: get_all_selections returning dict with {len(result['selections'])} selections")
            print(f"DEBUG: Return type: {type(result)}")

            return result

        except Exception as e:
            print(f"❌ ERROR in get_all_selections: {e}")
            import traceback
            traceback.print_exc()
            # Return an empty dict, NEVER return a boolean
            return {
                'block_id': str(self.block_id),
                'block_name': str(self.block_name),
                'total_steps': int(self.total_steps),
                'selections': {},
                'error': str(e)
            }

    def validate_and_accept(self):
        """Validate selections, build final assembly config, then accept"""
        print("🔴🔴🔴 validate_and_accept CALLED 🔴🔴🔴")

        for step in range(1, self.total_steps + 1):
            if step not in self.step_selections:
                QMessageBox.warning(
                    self,
                    "⚠️ Missing Selection",
                    f"Please select a product for Step {step}"
                )
                self.set_active_step(step)
                return

        if not self.step_selections:
            QMessageBox.warning(
                self,
                "⚠️ No Selections",
                "No steps have been configured."
            )
            return

        final_config = self.get_all_selections()

        if not isinstance(final_config, dict):
            QMessageBox.warning(
                self,
                "⚠️ Save Failed",
                "Assembly configuration is invalid."
            )
            return

        # 关键：把最终结果明确存下来
        self.config_data = final_config
        self.assembly_data = final_config

        print(f"DEBUG: Final assembly config prepared: {final_config}")
        print(f"DEBUG: Accepting dialog with {len(final_config.get('selections', {}))} steps")

        super().accept()

    def get_config(self):
        """Return final assembly config"""
        if hasattr(self, "assembly_data") and isinstance(self.assembly_data, dict):
            return self.assembly_data
        return self.get_all_selections()

    # ========== PREDICTION METHODS ==========

    def auto_predict_for_step(self, step_number, image_path, product_name):
        """Automatically run prediction when image is selected"""
        if not self.prediction_manager.is_model_loaded():
            return

        if not image_path or not os.path.exists(image_path):
            return

        # Show auto-prediction notification
        self.prediction_status_label.setText(f"Auto-predicting Step {step_number}...")
        self.prediction_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #FF9800;
                padding: 6px;
                background-color: #FFF3E0;
                border-radius: 3px;
            }
        """)

        # Run prediction in background
        thread = threading.Thread(
            target=self.run_auto_prediction,
            args=(step_number, image_path, product_name),
            daemon=True
        )
        thread.start()

    def predict_all_steps(self):
        """Run prediction on all configured steps"""
        try:
            if not self.prediction_manager.is_model_loaded():
                QMessageBox.warning(self, "No Model Loaded",
                                    "Please load a model first using 'Load Model' button.")
                return

            if not self.step_selections:
                QMessageBox.warning(self, "No Steps Configured",
                                    "Please configure assembly steps first.")
                return

            # Ask for confirmation
            reply = QMessageBox.question(
                self,
                "Predict All Steps",
                f"Run prediction on all {len(self.step_selections)} configured steps?\n\n"
                "This may take some time depending on the number of images.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

            # Create progress dialog
            self.predict_all_progress = QProgressDialog(
                "Running predictions on all steps...",
                "Cancel", 0, len(self.step_selections), self
            )
            self.predict_all_progress.setWindowTitle("🔮 Predicting All Steps")
            self.predict_all_progress.setWindowModality(Qt.WindowModal)
            self.predict_all_progress.show()

            # Run predictions sequentially
            self.current_prediction_step = 1
            self.total_prediction_steps = len(self.step_selections)
            self.predict_all_results = []

            # Start first prediction
            QTimer.singleShot(100, self.run_next_prediction)

        except Exception as e:
            QMessageBox.critical(self, "Prediction Error",
                                 f"Failed to run predictions:\n{str(e)}")

    def run_next_prediction(self):
        """Run prediction for the next step"""
        if self.current_prediction_step > self.total_prediction_steps:
            # All predictions completed
            self.predict_all_progress.close()
            self.show_predict_all_results()
            return

        # Get current step data
        step_number = sorted(self.step_selections.keys())[self.current_prediction_step - 1]
        selection = self.step_selections[step_number]
        product_data = selection['product_data']
        image_path = product_data.get('image_path')
        product_name = product_data.get('name', f"Step {step_number}")

        self.predict_all_progress.setLabelText(f"Predicting Step {step_number}: {product_name}")
        self.predict_all_progress.setValue(self.current_prediction_step - 1)

        if image_path and os.path.exists(image_path):
            # Run prediction
            success, message, predictions, output_path = self.prediction_manager.predict_image(image_path)

            # Store results
            self.predict_all_results.append({
                'step': step_number,
                'product_name': product_name,
                'success': success,
                'message': message,
                'num_predictions': len(predictions) if success else 0,
                'output_path': output_path if success else None
            })

        # Move to next step
        self.current_prediction_step += 1

        # Schedule next prediction (with 500ms delay to avoid overwhelming)
        QTimer.singleShot(500, self.run_next_prediction)

    def show_predict_all_results(self):
        """Show summary of all predictions"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🔮 All Predictions Complete")
        dialog.setFixedSize(600, 500)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel("📊 Prediction Results Summary")
        header.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: white;
                background-color: #9b59b6;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Results scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: white;
            }
        """)

        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setSpacing(8)

        successful = 0
        failed = 0

        for result in self.predict_all_results:
            result_frame = QFrame()
            result_frame.setFrameStyle(QFrame.Box)

            if result['success']:
                result_frame.setStyleSheet("""
                    QFrame {
                        border: 2px solid #27ae60;
                        border-radius: 5px;
                        background-color: #e8f8ef;
                        padding: 10px;
                        margin: 2px;
                    }
                """)
                successful += 1
            else:
                result_frame.setStyleSheet("""
                    QFrame {
                        border: 2px solid #e74c3c;
                        border-radius: 5px;
                        background-color: #ffebee;
                        padding: 10px;
                        margin: 2px;
                    }
                """)
                failed += 1

            frame_layout = QHBoxLayout(result_frame)

            # Step info
            step_label = QLabel(f"Step {result['step']}: {result['product_name']}")
            step_label.setStyleSheet("font-weight: bold; font-size: 13px;")

            # Status
            if result['success']:
                status_label = QLabel(f"✅ {result['num_predictions']} objects")
                status_label.setStyleSheet("color: #27ae60;")
            else:
                status_label = QLabel(f"❌ Failed: {result['message']}")
                status_label.setStyleSheet("color: #e74c3c;")
                status_label.setWordWrap(True)

            frame_layout.addWidget(step_label)
            frame_layout.addStretch()
            frame_layout.addWidget(status_label)

            results_layout.addWidget(result_frame)

        results_layout.addStretch()
        scroll_area.setWidget(results_widget)
        layout.addWidget(scroll_area)

        # Summary
        summary = QLabel(f"✅ Successful: {successful}  |  ❌ Failed: {failed}")
        summary.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #ecf0f1;
                border-radius: 5px;
                margin: 10px 0;
            }
        """)
        summary.setAlignment(Qt.AlignCenter)
        layout.addWidget(summary)

        # Buttons
        button_layout = QHBoxLayout()

        if successful > 0:
            view_btn = QPushButton("📂 Open Results Folder")
            view_btn.setStyleSheet("""
                QPushButton {
                    font-size: 12px;
                    padding: 8px;
                    background-color: #3498db;
                    color: white;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            view_btn.clicked.connect(self.open_predictions_root_folder)
            button_layout.addWidget(view_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px;
                background-color: #95a5a6;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    def run_auto_prediction(self, step_number, image_path, product_name):
        """Run auto-prediction in background thread"""
        try:
            # Run prediction
            success, message, predictions, output_path = self.prediction_manager.predict_image(
                image_path,
                progress_callback=lambda progress, status: self.on_auto_prediction_progress(step_number, progress,
                                                                                            status)
            )

            if success:
                # Update UI in main thread
                QTimer.singleShot(0, lambda: self.on_auto_prediction_success(
                    step_number, predictions, output_path, message, product_name
                ))
            else:
                QTimer.singleShot(0, lambda: self.on_auto_prediction_failed(
                    step_number, message, product_name
                ))

        except Exception as e:
            QTimer.singleShot(0, lambda: self.on_auto_prediction_failed(
                step_number, f"Prediction error: {str(e)}", product_name
            ))

    def on_auto_prediction_progress(self, step_number, progress, status):
        """Update auto-prediction progress"""
        QTimer.singleShot(0, lambda: self._update_auto_prediction_progress(step_number, progress, status))

    def _update_auto_prediction_progress(self, step_number, progress, status):
        """Update auto-prediction progress (called in main thread)"""
        self.prediction_status_label.setText(f"Step {step_number}: {status}")

    def on_auto_prediction_success(self, step_number, predictions, output_path, message, product_name):
        """Handle successful auto-prediction and send coordinates"""
        # Update step display with prediction results
        if step_number in self.step_selections:
            # Get current step display
            step_frame = self.step_widgets[step_number]['frame']
            display_label = step_frame.findChild(QLabel, f"step_{step_number}_display")

            if display_label:
                # Update display with prediction results
                prediction_text = f"✅ {product_name}\n"
                prediction_text += f"📄 {os.path.basename(output_path) if output_path else 'No output'}\n"
                prediction_text += f"🔍 {len(predictions)} objects detected"

                display_label.setText(prediction_text)
                display_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 8px;
                        background-color: #e8f8ef;
                        border-radius: 4px;
                        min-height: 40px;
                        font-weight: bold;
                    }
                """)

        # Update prediction preview
        self.update_prediction_preview(predictions, output_path if output_path else "")

        # Update prediction results label
        if predictions and hasattr(self, 'prediction_results_label'):
            self.prediction_results_label.setText(f"Step {step_number}: {len(predictions)} objects")
            self.prediction_results_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #27ae60;
                    padding: 5px;
                    margin-top: 5px;
                    font-weight: bold;
                }
            """)

        # Update status
        self.prediction_status_label.setText(f"Step {step_number}: Auto-prediction complete")
        self.prediction_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #27ae60;
                padding: 6px;
                background-color: #e8f8ef;
                border-radius: 3px;
            }
        """)

        # ===== SEND COORDINATES TO SERVER =====
        if predictions:
            if self.calibration.is_calibrated:
                print(f"📐 Using WORLD coordinates from calibration")
            else:
                print(f"📷 Using PIXEL coordinates (no calibration)")
            self.send_coordinates_to_server(predictions)

        # Show notification
        QTimer.singleShot(100, lambda: self.show_auto_prediction_notification(
            step_number, product_name, len(predictions), True
        ))

    def on_auto_prediction_failed(self, step_number, message, product_name):
        """Handle failed auto-prediction"""
        # Update step display
        if step_number in self.step_selections:
            step_frame = self.step_widgets[step_number]['frame']
            display_label = step_frame.findChild(QLabel, f"step_{step_number}_display")

            if display_label:
                error_text = f"⚠️ {product_name}\n"
                error_text += f"❌ Prediction failed"

                display_label.setText(error_text)
                display_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e74c3c;
                        padding: 8px;
                        background-color: #ffebee;
                        border-radius: 4px;
                        min-height: 40px;
                        font-weight: bold;
                    }
                """)

        # Update status
        self.prediction_status_label.setText(f"Step {step_number}: Auto-prediction failed")
        self.prediction_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #e74c3c;
                padding: 6px;
                background-color: #ffebee;
                border-radius: 3px;
            }
        """)

        # Show notification
        QTimer.singleShot(100, lambda: self.show_auto_prediction_notification(
            step_number, product_name, 0, False, message
        ))

    def show_auto_prediction_notification(self, step_number, product_name, num_objects, success, error_msg=""):
        """Show auto-prediction notification"""
        if success:
            title = f"✅ Step {step_number}: Auto-Prediction Complete"
            message = f"Auto-prediction completed for {product_name}!\n\n"
            message += f"Detected {num_objects} object(s)\n"
            message += f"Results saved to predictions/ folder"

            # Create custom notification dialog
            notification = QMessageBox(self)
            notification.setWindowTitle(title)
            notification.setText(message)
            notification.setIcon(QMessageBox.Information)
            notification.setStandardButtons(QMessageBox.Ok)

            # Auto-close after 3 seconds
            QTimer.singleShot(3000, notification.accept)
            notification.exec()
        else:
            QMessageBox.warning(
                self,
                f"⚠️ Step {step_number}: Auto-Prediction Failed",
                f"Failed to auto-predict {product_name}:\n\n{error_msg}"
            )

    def show_load_model_prompt(self):
        """Show prompt to load model for auto-prediction"""
        # Only show if no model is loaded and we have selections
        if not self.prediction_manager.is_model_loaded() and len(self.step_selections) > 0:
            reply = QMessageBox.question(
                self,
                "🤖 Load Model for Auto-Prediction?",
                "No model loaded for auto-prediction.\n\n"
                "Would you like to load a trained model now?\n\n"
                "Auto-prediction will run automatically when you select images.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                self.load_model_for_prediction()

    def load_model_for_prediction(self):
        """Load a trained YOLO model using shared manager"""
        try:
            # Ask user to select a model file
            model_path, _ = QFileDialog.getOpenFileName(
                self, "Select Trained Model",
                "",
                "PyTorch Models (*.pt);;All Files (*.*)"
            )

            if not model_path or not os.path.exists(model_path):
                return

            # Show loading dialog
            loading_dialog = QProgressDialog("Loading model...", None, 0, 0, self)
            loading_dialog.setWindowTitle("Loading Model")
            loading_dialog.setWindowModality(Qt.WindowModal)
            loading_dialog.setMinimumDuration(0)
            loading_dialog.show()

            QTimer.singleShot(100, lambda: self._perform_model_load(model_path, loading_dialog))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load model:\n{str(e)}")

    def _perform_model_load(self, model_path, loading_dialog):
        """Perform the actual model loading in a separate call"""
        try:
            success, message = self.prediction_manager.load_model(model_path)

            if success:
                if hasattr(self, 'test_prediction_btn'):
                    self.test_prediction_btn.setEnabled(True)

                if hasattr(self, 'predict_all_btn'):
                    self.predict_all_btn.setEnabled(True)

                self.model_status_label.setText(f"✅ {self.prediction_manager.get_model_info()}")
                self.model_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 6px;
                        background-color: #e8f8ef;
                        border-radius: 3px;
                        font-weight: bold;
                    }
                """)

                self.prediction_status_label.setText(f"Auto-prediction enabled on {self.prediction_manager.device}")
                self.prediction_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 6px;
                        background-color: #e8f8ef;
                        border-radius: 3px;
                    }
                """)

                loading_dialog.close()

                QMessageBox.information(
                    self, "Model Loaded",
                    f"✅ Model loaded successfully!\n\n"
                    f"Auto-prediction is now enabled.\n"
                    f"Images will be automatically predicted when selected."
                )

                QTimer.singleShot(500, self.auto_predict_existing_selections)

            else:
                loading_dialog.close()
                QMessageBox.critical(self, "Load Failed", message)
                self.reset_prediction_ui()

        except Exception as e:
            loading_dialog.close()
            QMessageBox.critical(self, "Load Failed", f"Failed to load model:\n{str(e)}")
            self.reset_prediction_ui()

    def auto_predict_existing_selections(self):
        """Auto-predict already selected steps after model load"""
        if not self.prediction_manager.is_model_loaded():
            return

        if len(self.step_selections) == 0:
            return

        # Show notification
        self.prediction_status_label.setText("Auto-predicting existing selections...")

        # Predict each selected step
        for step_number, selection in self.step_selections.items():
            product_data = selection['product_data']
            image_path = product_data.get('image_path')
            product_name = product_data.get('name', f"Step {step_number}")

            if image_path and os.path.exists(image_path):
                # Delay each prediction slightly to avoid overwhelming
                delay = (step_number - 1) * 1000  # 1 second delay between steps
                QTimer.singleShot(delay, lambda s=step_number, p=image_path, n=product_name:
                self.auto_predict_for_step(s, p, n))

    def reset_prediction_ui(self):
        """Reset the prediction UI to default state"""
        try:
            self.model_status_label.setText("No model loaded")
            self.model_status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #7f8c8d;
                    padding: 6px;
                    background-color: #ecf0f1;
                    border-radius: 3px;
                }
            """)

            self.prediction_status_label.setText("Prediction: Ready")
            self.prediction_status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #27ae60;
                    padding: 6px;
                    background-color: #e8f8ef;
                    border-radius: 3px;
                }
            """)

            if hasattr(self, 'prediction_preview_layout'):
                while self.prediction_preview_layout.count():
                    child = self.prediction_preview_layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

                self.prediction_message = QLabel("Load a model and select an image to see predictions")
                self.prediction_message.setAlignment(Qt.AlignCenter)
                self.prediction_message.setStyleSheet("""
                    QLabel {
                        font-size: 14px;
                        color: #7f8c8d;
                        padding: 50px;
                        font-style: italic;
                    }
                """)
                self.prediction_preview_layout.addWidget(self.prediction_message)

            if hasattr(self, 'prediction_results_label'):
                self.prediction_results_label.setText("")

            if hasattr(self, 'test_prediction_btn'):
                self.test_prediction_btn.setEnabled(False)

            if hasattr(self, 'predict_all_btn'):
                self.predict_all_btn.setEnabled(False)

            if hasattr(self, 'prediction_manager'):
                self.prediction_manager.reset()

            print("DEBUG: Prediction UI reset complete")

        except Exception as e:
            print(f"DEBUG: Error resetting prediction UI: {e}")

    def test_prediction_on_selected(self):
        """Test prediction on currently selected image"""
        try:
            # Check if model is loaded
            if not self.prediction_manager.is_model_loaded():
                QMessageBox.warning(self, "No Model Loaded",
                                    "Please load a model first using 'Load Model' button.")
                return

            # Get the current active step
            if self.current_active_step not in self.step_selections:
                QMessageBox.warning(self, "No Image Selected",
                                    f"Please select an image for Step {self.current_active_step} first.")
                return

            # Get the selected product
            selection = self.step_selections[self.current_active_step]
            product_data = selection['product_data']
            image_path = product_data.get('image_path')
            product_name = product_data.get('name', f"Step {self.current_active_step}")

            if not image_path or not os.path.exists(image_path):
                QMessageBox.warning(self, "Image Not Found",
                                    f"Selected image not found:\n{image_path}")
                return

            # Show progress dialog
            progress_dialog = QProgressDialog(
                f"Running prediction on Step {self.current_active_step}: {product_name}",
                "Cancel", 0, 100, self
            )
            progress_dialog.setWindowTitle("🔍 Running Prediction")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(True)

            # Run prediction in background thread
            thread = threading.Thread(
                target=self.run_test_prediction,
                args=(self.current_active_step, image_path, product_name, progress_dialog),
                daemon=True
            )
            thread.start()

            # Show progress dialog
            progress_dialog.show()

        except Exception as e:
            QMessageBox.critical(self, "Prediction Error",
                                 f"Failed to run prediction:\n{str(e)}")

    def run_test_prediction(self, step_number, image_path, product_name, progress_dialog):
        """Run test prediction in background thread"""
        try:
            def progress_callback(progress, status):
                QTimer.singleShot(0, lambda: self.update_test_prediction_progress(
                    progress_dialog, progress, status
                ))

            # Run prediction
            success, message, predictions, output_path = self.prediction_manager.predict_image(
                image_path,
                progress_callback=progress_callback
            )

            if success:
                QTimer.singleShot(0, lambda: self.on_test_prediction_success(
                    step_number, predictions, output_path, message, product_name, progress_dialog
                ))
            else:
                QTimer.singleShot(0, lambda: self.on_test_prediction_failed(
                    step_number, message, product_name, progress_dialog
                ))

        except Exception as e:
            QTimer.singleShot(0, lambda: self.on_test_prediction_failed(
                step_number, f"Error: {str(e)}", product_name, progress_dialog
            ))

    def update_test_prediction_progress(self, progress_dialog, progress, status):
        """Update test prediction progress"""
        progress_dialog.setValue(progress)
        progress_dialog.setLabelText(f"{status}...")

    def on_test_prediction_success(self, step_number, predictions, output_path, message, product_name, progress_dialog):
        """Handle successful test prediction"""
        progress_dialog.close()

        # Update prediction preview
        self.update_prediction_preview(predictions, output_path)

        # Update prediction results label
        if predictions and hasattr(self, 'prediction_results_label'):
            self.prediction_results_label.setText(f"Step {step_number}: {len(predictions)} objects")
            self.prediction_results_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #27ae60;
                    padding: 5px;
                    margin-top: 5px;
                    font-weight: bold;
                }
            """)

        # Show results dialog
        self.show_test_prediction_results(step_number, product_name, len(predictions), output_path)

    def on_test_prediction_failed(self, step_number, message, product_name, progress_dialog):
        """Handle failed test prediction"""
        progress_dialog.close()

        QMessageBox.warning(
            self,
            f"⚠️ Prediction Failed - Step {step_number}",
            f"Failed to predict {product_name}:\n\n{message}"
        )

    def show_test_prediction_results(self, step_number, product_name, num_objects, output_path):
        """Show detailed test prediction results"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"✅ Prediction Results - Step {step_number}")
        dialog.setFixedSize(500, 400)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel(f"Step {step_number}: {product_name}")
        header.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Results summary
        summary = QLabel(f"✅ Prediction Successful!\n\n"
                         f"📊 Detected Objects: {num_objects}\n"
                         f"📁 Results saved to: {os.path.basename(output_path) if output_path else 'N/A'}")
        summary.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #2c3e50;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 6px;
                margin-bottom: 15px;
            }
        """)
        summary.setAlignment(Qt.AlignCenter)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # Image preview if available
        if output_path and os.path.exists(output_path):
            try:
                pixmap = QPixmap(output_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(
                        300, 200,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    image_label = QLabel()
                    image_label.setPixmap(scaled_pixmap)
                    image_label.setAlignment(Qt.AlignCenter)
                    image_label.setStyleSheet("""
                        QLabel {
                            border: 2px solid #bdc3c7;
                            border-radius: 6px;
                            background-color: #f8f9fa;
                            padding: 5px;
                            margin-bottom: 15px;
                        }
                    """)
                    layout.addWidget(image_label, alignment=Qt.AlignCenter)
            except:
                pass

        # Button to open folder
        open_folder_btn = QPushButton("📂 Open Results Folder")
        open_folder_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px;
                background-color: #9b59b6;
                color: white;
                border-radius: 4px;
                margin-bottom: 10px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        open_folder_btn.clicked.connect(lambda: self.open_prediction_folder(output_path))
        layout.addWidget(open_folder_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px;
                background-color: #95a5a6;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def open_prediction_folder(self, output_path):
        """Open the folder containing prediction results"""
        if not output_path or not os.path.exists(output_path):
            QMessageBox.warning(self, "Folder Not Found", "Prediction output folder not found.")
            return

        folder_path = os.path.dirname(output_path)

        try:
            import subprocess
            import platform

            system = platform.system()

            if system == "Windows":
                os.startfile(folder_path)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", folder_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", folder_path])

        except Exception as e:
            QMessageBox.warning(self, "Cannot Open Folder",
                                f"Failed to open folder:\n{str(e)}\n\nPath: {folder_path}")

    def open_predictions_root_folder(self):
        """Open the predictions folder for current block"""
        recipe_path = self.get_current_recipe_path()
        if not recipe_path:
            QMessageBox.warning(self, "Folder Not Found", "Recipe folder not found.")
            return

        predictions_folder = os.path.join(
            recipe_path,
            "Assembly",
            f"Block_{self.block_id}",
            "predictions"
        )

        if not os.path.exists(predictions_folder):
            QMessageBox.warning(
                self,
                "Folder Not Found",
                f"Predictions folder not found:\n{predictions_folder}"
            )
            return

        try:
            import subprocess
            import platform

            system = platform.system()

            if system == "Windows":
                os.startfile(predictions_folder)
            elif system == "Darwin":
                subprocess.Popen(["open", predictions_folder])
            else:
                subprocess.Popen(["xdg-open", predictions_folder])

        except Exception as e:
            QMessageBox.warning(
                self,
                "Cannot Open Folder",
                f"Failed to open folder:\n{str(e)}\n\nPath: {predictions_folder}"
            )

    def cancel_prediction(self):
        """Cancel any ongoing prediction"""
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
        print(f"DEBUG ScrewDialog __init__ -> self={id(self)}, block_id={block_id}, block_name={block_name}")
        self.parent_dialog = parent
        self.block_id = block_id or "1"
        self.block_name = block_name or f"Block_{self.block_id}"
        self.assembly_tool_window = None
        self.config_data = None

        self.setWindowTitle("Screw Configuration")
        self.setFixedSize(250, 260)

        layout = QFormLayout(self)

        self.screw_spinbox = QSpinBox()
        self.screw_spinbox.setRange(1, 50)
        self.screw_spinbox.setValue(4)
        self.screw_spinbox.setStyleSheet("font-size: 14px; padding: 5px;")
        layout.addRow("🔩 Number of Screws:", self.screw_spinbox)

        self.screw_type_combo = QComboBox()
        self.screw_type_combo.addItems(["M3", "M4", "M5", "M6", "M8", "M10", "Custom"])
        self.screw_type_combo.setCurrentText("M4")
        self.screw_type_combo.setStyleSheet("font-size: 14px; padding: 5px;")
        layout.addRow("⚙️ Screw Type:", self.screw_type_combo)

        self.torque_spinbox = QSpinBox()
        self.torque_spinbox.setRange(1, 100)
        self.torque_spinbox.setValue(10)
        self.torque_spinbox.setSuffix(" N·m")
        self.torque_spinbox.setStyleSheet("font-size: 14px; padding: 5px;")
        layout.addRow("💪 Torque:", self.torque_spinbox)

        self.screw_location_btn = QPushButton("🔩 Screw Location")
        self.screw_location_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px 12px;
                background-color: #FF9800;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.screw_location_btn.clicked.connect(self.open_assembly_tool)
        self.screw_location_btn.setToolTip("Open the same Assembly Annotation Tool page")
        layout.addRow(self.screw_location_btn)

        self.screw_location_2_btn = QPushButton("🔩 Screw Location 2")
        self.screw_location_2_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 8px 12px;
                background-color: #9C27B0;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
            }
        """)
        self.screw_location_2_btn.clicked.connect(self.open_assembly_tool_2)
        self.screw_location_2_btn.setToolTip("Open alternate screw location tool with separate folders")
        layout.addRow(self.screw_location_2_btn)

        # OK / Cancel buttons
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addRow(btn_row)

        if initial_config and isinstance(initial_config, dict):
            self.load_initial_config(initial_config)

    def load_initial_config(self, config):
        self.screw_spinbox.setValue(int(config.get("count", 4)))
        self.screw_type_combo.setCurrentText(str(config.get("type", "M4")))
        self.torque_spinbox.setValue(int(config.get("torque", 10)))

    def get_config(self):
        return {
            "block_type": "screw",
            "block_id": str(self.block_id),
            "block_name": str(self.block_name),
            "count": int(self.screw_spinbox.value()),
            "type": str(self.screw_type_combo.currentText()),
            "torque": int(self.torque_spinbox.value()),
            "position": f"ScrewBoxesData/Block_{self.block_id}",
            "position2": f"ScrewBoxesData2/Block_{self.block_id}"
        }

    def accept(self):
        self.config_data = self.get_config()
        super().accept()

    def open_assembly_tool(self):
        """Open Screw Location Tool"""
        try:
            from ui.components.assembly_laser import MainWindow as AssemblyLaserMainWindow

            print(f"DEBUG open_assembly_tool -> block_id={self.block_id}, block_name={self.block_name}, mode=screw")

            if self.assembly_tool_window:
                try:
                    self.assembly_tool_window.close()
                except:
                    pass
                self.assembly_tool_window = None

            self.assembly_tool_window = AssemblyLaserMainWindow(
                block_id=str(self.block_id),
                block_name=str(self.block_name),
                mode="screw"
            )

            self.assembly_tool_window.setParent(None)
            self.assembly_tool_window.setWindowFlags(
                Qt.Window |
                Qt.WindowStaysOnTopHint |
                Qt.CustomizeWindowHint |
                Qt.WindowTitleHint |
                Qt.WindowMinMaxButtonsHint |
                Qt.WindowCloseButtonHint
            )
            self.assembly_tool_window.setWindowModality(Qt.NonModal)
            self.assembly_tool_window.setAttribute(Qt.WA_DeleteOnClose)

            self.assembly_tool_window.destroyed.connect(self._on_assembly_tool_closed)

            self.assembly_tool_window.show()
            self.assembly_tool_window.raise_()
            self.assembly_tool_window.activateWindow()

            self.hide()

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to open Screw Location Tool:\n\n{str(e)}")

    def open_assembly_tool_2(self):
        """Open Screw Location Tool 2 with separate folders"""
        try:
            from ui.components.assembly_laser import MainWindow as AssemblyLaserMainWindow

            print(f"DEBUG open_assembly_tool_2 -> block_id={self.block_id}, block_name={self.block_name}, mode=screw2")

            if self.assembly_tool_window:
                try:
                    self.assembly_tool_window.close()
                except:
                    pass
                self.assembly_tool_window = None

            self.assembly_tool_window = AssemblyLaserMainWindow(
                block_id=str(self.block_id),
                block_name=str(self.block_name),
                mode="screw2"
            )

            self.assembly_tool_window.setParent(None)
            self.assembly_tool_window.setWindowFlags(
                Qt.Window |
                Qt.WindowStaysOnTopHint |
                Qt.CustomizeWindowHint |
                Qt.WindowTitleHint |
                Qt.WindowMinMaxButtonsHint |
                Qt.WindowCloseButtonHint
            )
            self.assembly_tool_window.setWindowModality(Qt.NonModal)
            self.assembly_tool_window.setAttribute(Qt.WA_DeleteOnClose)

            self.assembly_tool_window.destroyed.connect(self._on_assembly_tool_closed)

            self.assembly_tool_window.show()
            self.assembly_tool_window.raise_()
            self.assembly_tool_window.activateWindow()

            self.hide()

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to open Screw Location Tool 2:\n\n{str(e)}")

    def _on_assembly_tool_closed(self):
        """Show ScrewDialog again after tool window is closed"""
        self.assembly_tool_window = None
        self.show()
        self.raise_()
        self.activateWindow()


class ConfigurationOptionsDialog(QDialog):
    """Dialog to choose between viewing or editing configuration"""

    # Dialog results
    VIEW = 1
    EDIT = 2
    CANCEL = 3

    def __init__(self, block_name, current_config, assembly_data=None, parent=None):
        super().__init__(parent)
        self.block_name = block_name
        self.current_config = current_config
        self.assembly_data = assembly_data
        self.result = self.CANCEL

        self.setWindowTitle(f"⚙️ {block_name} Configuration")
        self.setFixedSize(500, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel(f"{self.block_name} Configuration Options")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #1d4ed8;
            margin: 10px;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Current configuration preview
        preview_label = QLabel("Current Configuration:")
        preview_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(preview_label)

        # Configuration preview area
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)

        if self.block_name == "Assembly" and self.assembly_data:
            # Format assembly configuration nicely
            preview_text = self.format_assembly_preview()
        else:
            # Simple text preview
            preview_text = self.current_config

        self.preview_text.setPlainText(preview_text)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Courier New', monospace;
                font-size: 11px;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.preview_text)

        # Warning/Info message
        info_label = QLabel(
            "⚠️ Changing configuration may affect your workflow. Make sure to update connections if needed.")
        info_label.setStyleSheet("""
            color: #d97706;
            font-size: 12px;
            padding: 8px;
            background-color: #fef3c7;
            border: 1px solid #fbbf24;
            border-radius: 4px;
            margin: 10px 0;
        """)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Button choices
        button_layout = QVBoxLayout()
        button_layout.setSpacing(10)

        # View Configuration button
        view_btn = QPushButton("👁️  View Configuration")
        view_btn.setToolTip("View current configuration details")
        view_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                background-color: #3b82f6;
                color: white;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        view_btn.clicked.connect(lambda: self.accept_with_result(self.VIEW))

        # Edit Configuration button
        edit_btn = QPushButton("✏️  Edit Configuration")
        edit_btn.setToolTip("Modify current configuration")
        edit_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                background-color: #10b981;
                color: white;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        edit_btn.clicked.connect(lambda: self.accept_with_result(self.EDIT))

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px;
                background-color: #6b7280;
                color: white;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(view_btn)
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def find_edit_flow_page(self):
        obj = self.parent()
        while obj:
            if hasattr(obj, "pipeline_blocks") and hasattr(obj, "save_flow"):
                return obj
            obj = obj.parent()
        return None

    def format_assembly_preview(self):
        """Format assembly configuration for preview"""
        if not self.assembly_data:
            return self.current_config

        preview_lines = []
        preview_lines.append(f"Total Steps: {self.assembly_data['total_steps']}")
        preview_lines.append("")

        for step, selection in self.assembly_data['selections'].items():
            product_id = selection['product_id']
            product_data = selection['product_data']
            trained_status = "✅" if product_data.get('trained') else "❌"
            preview_lines.append(f"Step {step}: {product_data.get('name', product_id)} {trained_status}")

        return "\n".join(preview_lines)

    def configure_assembly_block(self, assembly_block):
        dialog = AssemblyDialog(
            parent=self,
            initial_config=assembly_block.assembly_data if hasattr(assembly_block, "assembly_data") else None,
            block_id=str(assembly_block.block_id),
            block_name=f"Block_{assembly_block.block_id}"
        )

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
                    if total_steps > 0 else
                    f"Assembly (Block {assembly_block.block_id})"
                )

                text_rect = assembly_block.text.boundingRect()
                text_x = (assembly_block.block_width - text_rect.width()) / 2
                text_y = (assembly_block.block_height - text_rect.height()) / 2
                assembly_block.text.setPos(text_x, text_y)

                self.save_flow()
                self.update_assembly_block_displays()

    # When user chooses to edit configuration
    def edit_assembly_configuration(self):
        """Edit existing assembly configuration"""
        # Get current configuration from the block
        current_config = self.get_current_assembly_config()  # You need to implement this

        # Create and show dialog with initial configuration
        dialog = AssemblyDialog(parent=self, initial_config=current_config)

        if dialog.exec() == QDialog.Accepted:
            # Get the updated configuration
            updated_config = {
                'total_steps': dialog.total_steps,
                'selections': dialog.get_all_selections()
            }

            # Save the updated configuration
            self.save_assembly_configuration(updated_config)

    # In the place where you handle the ConfigurationOptionsDialog result
    def on_configuration_option_selected(self, block_id, action):
        """Handle configuration option selection"""
        if action == ConfigurationOptionsDialog.VIEW:
            # Show current configuration
            self.view_configuration(block_id)
        elif action == ConfigurationOptionsDialog.EDIT:
            # Edit configuration - pass existing config
            current_config = self.get_block_configuration(block_id)  # Get existing config
            self.edit_configuration(block_id, current_config)

    def edit_configuration(self, block_id, current_config):
        """Edit configuration for a block"""
        try:
            print(f"🔴🔴🔴 edit_configuration CALLED for block {block_id}, block_name={self.block_name} 🔴🔴🔴")

            # ===== SCREW =====
            if self.block_name == "Screw":
                print("DEBUG: Opening ScrewDialog")

                screw_dialog = ScrewDialog(
                    parent=self,
                    block_id=block_id,
                    block_name=f"Block_{block_id}",
                    initial_config=current_config if isinstance(current_config, dict) else None
                )

                if screw_dialog.exec() == QDialog.Accepted:
                    new_config = screw_dialog.get_config()
                    print(f"DEBUG: Screw config accepted: {new_config}")
                    self.save_configuration(block_id, new_config)
                else:
                    print("DEBUG: Screw dialog cancelled")

                return True

            # ===== ASSEMBLY =====
            assembly_data = None
            if isinstance(current_config, dict) and 'selections' in current_config:
                assembly_data = current_config
                print(f"DEBUG: Using existing assembly data with {len(assembly_data.get('selections', {}))} steps")
            else:
                print("DEBUG: No existing assembly data, creating new")
                assembly_data = {'total_steps': 1, 'selections': {}}

            print("DEBUG: Creating AssemblyDialog...")
            self.assembly_dialog = AssemblyDialog(
                parent=self,
                initial_config=assembly_data,
                block_id=block_id,
                block_name=f"Block_{block_id}"
            )

            self.assembly_dialog.setParent(None)
            self.assembly_dialog.setWindowFlags(
                Qt.Window |
                Qt.CustomizeWindowHint |
                Qt.WindowTitleHint |
                Qt.WindowMinMaxButtonsHint |
                Qt.WindowCloseButtonHint
            )
            self.assembly_dialog.setWindowModality(Qt.NonModal)
            self.assembly_dialog.setModal(False)

            self.assembly_dialog.finished.connect(
                lambda result: self.on_assembly_dialog_finished(result, block_id)
            )

            self.assembly_dialog.show()
            self.assembly_dialog.raise_()
            self.assembly_dialog.activateWindow()

            print("DEBUG: Assembly dialog shown successfully")
            return True

        except Exception as e:
            print(f"❌ ERROR in edit_configuration: {e}")
            import traceback
            traceback.print_exc()
            return False

    def save_configuration(self, block_id, new_config):
        print(f"DEBUG: save_configuration called for block_id={block_id}")
        print(f"DEBUG: new_config={new_config}")

        page = self.find_edit_flow_page()
        if not page:
            print("❌ Could not find EditFlowPage")
            QMessageBox.warning(self, "Save Failed", "Could not find Edit Flow page.")
            return False

        target_block = None

        # 在 pipeline_blocks 里找对应 block
        for block in page.pipeline_blocks:
            if hasattr(block, "block_id") and str(block.block_id) == str(block_id):
                if self.block_name == "Assembly" and block.name == "Assembly":
                    target_block = block
                    break
                elif self.block_name == "Screw" and block.name == "Screw":
                    target_block = block
                    break

        if not target_block:
            print(f"❌ Block {block_id} not found in pipeline_blocks")
            QMessageBox.warning(self, "Save Failed", f"Block {block_id} not found.")
            return False

        # ===== 更新 block 数据 =====
        if target_block.name == "Assembly":
            target_block.assembly_data = new_config
            target_block.config = new_config

            total_steps = new_config.get("total_steps", 0)
            if hasattr(target_block, "text"):
                if total_steps > 0:
                    target_block.text.setPlainText(f"Assembly (Block {target_block.block_id}, {total_steps} steps)")
                else:
                    target_block.text.setPlainText(f"Assembly (Block {target_block.block_id})")

        elif target_block.name == "Screw":
            target_block.config = new_config

            screw_count = new_config.get("count", "")
            screw_type = new_config.get("type", "")
            if hasattr(target_block, "text"):
                if screw_count and screw_type:
                    target_block.text.setPlainText(
                        f"Screw (Block {target_block.block_id}, {screw_count}x {screw_type})"
                    )
                else:
                    target_block.text.setPlainText(f"Screw (Block {target_block.block_id})")

        print(f"✅ Updated block object for block_id={block_id}")

        # ===== 刷新 block 显示 =====
        if hasattr(page, "update_assembly_block_displays"):
            page.update_assembly_block_displays()

        page.scene.update()
        page.view.viewport().update()

        # ===== 写回 pipeline_flow.json =====
        try:
            page.save_flow()
            print("✅ pipeline_flow.json saved")
        except Exception as e:
            print(f"❌ Failed to save flow: {e}")
            QMessageBox.warning(self, "Save Failed", f"Failed to save pipeline flow:\n{str(e)}")
            return False

        return True

    def on_assembly_dialog_finished(self, result, block_id):
        """Handle when AssemblyDialog is closed"""
        print(f"DEBUG: Assembly dialog finished with result: {result}")

        if result == QDialog.Accepted:
            new_config = None

            if hasattr(self.assembly_dialog, "config_data") and isinstance(self.assembly_dialog.config_data, dict):
                new_config = self.assembly_dialog.config_data
            elif hasattr(self.assembly_dialog, "assembly_data") and isinstance(self.assembly_dialog.assembly_data,
                                                                               dict):
                new_config = self.assembly_dialog.assembly_data
            else:
                new_config = self.assembly_dialog.get_all_selections()

            print(f"DEBUG: New config type: {type(new_config)}")
            print(f"DEBUG: New config value: {new_config}")

            if isinstance(new_config, dict):
                self.save_configuration(block_id, new_config)
            else:
                print(f"❌ ERROR: new_config is {type(new_config)}, expected dict")
        else:
            print("DEBUG: Dialog cancelled")

        self.assembly_dialog = None

    def get_current_assembly_config(self):
        """Get current assembly configuration from workflow block"""
        if not hasattr(self, 'assembly_data'):
            return None

        # Get the assembly data stored in the block
        if self.assembly_data:
            config = {
                'total_steps': self.assembly_data.get('total_steps', 0),
                'selections': {}
            }

            # Process each step selection
            for step, selection in self.assembly_data.get('selections', {}).items():
                # Get product data
                product_data = selection.get('product_data', {})

                # Get capture info from the selection
                capture_info = selection.get('capture_info', {})

                # Build the selection dictionary
                config['selections'][step] = {
                    'product_id': selection.get('product_id', ''),
                    'product_data': {
                        'name': product_data.get('name', ''),
                        'original_name': product_data.get('original_name', ''),
                        'image_path': product_data.get('image_path', ''),
                        'filename': product_data.get('filename', ''),
                        'annotation_path': product_data.get('annotation_path', ''),
                        'model_path': product_data.get('model_path', ''),
                        'trained': product_data.get('trained', False)
                    },
                    'capture_info': {
                        'capture_count': capture_info.get('capture_counter', 0),
                        'capture_folder': capture_info.get('capture_folder', ''),
                        'assembly_folder': capture_info.get('assembly_folder', '')
                    }
                }

            return config

        return None

    def accept_with_result(self, result):
        """Accept dialog with specified result"""
        self.result = result
        super().accept()

    @staticmethod
    def get_action(block_name, current_config, assembly_data=None, parent=None):
        dialog = ConfigurationOptionsDialog(
            block_name=block_name,
            current_config=current_config,
            assembly_data=assembly_data,
            parent=parent
        )
        dialog.exec()
        return dialog.result