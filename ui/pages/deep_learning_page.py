import os
import random
import threading
import socket
import time
import queue
import re
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QWidget,
    QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QInputDialog,
    QMessageBox, QProgressDialog, QLabel,
    QLineEdit, QSpinBox, QStackedWidget,
    QGroupBox, QScrollArea, QTextEdit,
    QDialog, QRadioButton, QDialogButtonBox, QApplication,
    QTabWidget, QFrame, QSplitter, QSizePolicy
)
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QPixmap, QTextCursor, QFont, QIcon
from PySide6.QtCore import Signal, QObject, QTimer, Qt, QRectF, QPointF, QSize

from ui.components.buttons import create_button
from ui.components.annotator import AnnotationWidget
from config_manager import ConfigManager
from config_manager import config_manager

from PIL import Image

# Import camera capture function
try:
    from camera.camera import AutoCaptureFlow

    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    print("Warning: camera_capture module not found. Camera button will be disabled.")


class CameraSignals(QObject):
    """Signals for camera thread communication"""
    finished = Signal(bool, str, object)  # success, message, image_path


class TrainingSignals(QObject):
    """Signals for training thread communication"""
    progress = Signal(int, str, str)  # progress_percentage, status_message, time_remaining
    finished = Signal(bool, str)  # success, message


class PredictionSignals(QObject):
    """Signals for prediction thread communication"""
    progress = Signal(int, str)  # progress_percentage, status_message
    finished = Signal(bool, str, list)  # success, message, predictions
    image_ready = Signal(str)  # path to predicted image


class TCPClientSignals(QObject):
    """Signals for TCP client communication"""
    connection_status = Signal(str, bool)  # message, is_connected
    message_received = Signal(str)  # received message
    message_sent = Signal(str)  # sent message


class CameraWorker(QObject):
    finished = Signal(bool, str, str)  # success, message, image_path

    def __init__(self, capture_folder):
        super().__init__()
        self.capture_folder = capture_folder
        self._is_running = True

    def capture_image(self):
        """Capture image from camera"""
        try:
            if not CAMERA_AVAILABLE:
                self.finished.emit(False, "Camera module not available", "")
                return

            print("Starting camera capture...")

            def capture_callback(success, message, image_path):
                if success and image_path and self._is_running:
                    try:
                        # Save to recipe folder
                        base_name = os.path.basename(image_path)
                        save_path = os.path.join(self.capture_folder, base_name)

                        # Ensure unique filename
                        count = 1
                        name, ext = os.path.splitext(base_name)
                        while os.path.exists(save_path):
                            save_path = os.path.join(self.capture_folder, f"{name}_{count}{ext}")
                            count += 1

                        os.rename(image_path, save_path)
                        final_path = save_path
                        print(f"Image saved to: {final_path}")

                        # Emit success
                        self.finished.emit(True, "Capture successful", final_path)

                    except Exception as e:
                        print(f"Error saving image: {e}")
                        self.finished.emit(False, f"Save error: {str(e)}", "")
                else:
                    print(f"Capture failed or cancelled: {message}")
                    self.finished.emit(success, message, "")

            # Start capture with timeout
            import threading
            import time

            def run_capture():
                try:
                    AutoCaptureFlow(callback=capture_callback)
                except Exception as e:
                    print(f"Camera error: {e}")
                    self.finished.emit(False, f"Camera error: {str(e)}", "")

            # Start capture thread
            capture_thread = threading.Thread(target=run_capture, daemon=True)
            capture_thread.start()

            # Wait for thread with timeout
            capture_thread.join(timeout=10)  # 10 second timeout

            if capture_thread.is_alive():
                print("Camera capture timed out")
                self._is_running = False
                self.finished.emit(False, "Camera capture timed out (10s)", "")

        except Exception as e:
            print(f"Exception in camera worker: {e}")
            self.finished.emit(False, f"Capture error: {str(e)}", "")

    def stop(self):
        """Stop the capture process"""
        self._is_running = False


class DeepLearningPage(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.capture_folder = None
        self.capture_mode = "positive"  # default selected folder
        self.main_window = parent
        self.setWindowTitle("Deep Learning")
        self.resize(1600, 1000)

        # Start with object0 as the first label
        self.labels = ["0"]
        self.label_counter = 0
        self.label_colors = {"0": QColor(255, 0, 0)}

        self.image_files = []
        self.current_index = -1

        # Initialize image_boxes attribute to store bounding boxes
        self.image_boxes = {}  # <-- ADD THIS LINE

        # TCP related attributes
        self.tcp_socket = None
        self.tcp_connected = False
        self.tcp_thread = None
        self.listening_thread = None
        self.scan_data_received = ""
        self.last_bounding_box = None
        self.last_box_label = None
        self.labeling_path = None
        self.tcp_received_text = ""

        # Initialize based on current recipe
        self.update_paths_from_recipe()

        # Initialize signals
        self.camera_signals = CameraSignals()
        self.camera_signals.finished.connect(self.on_camera_finished)

        # Training related
        self.training_signals = TrainingSignals()
        self.training_signals.progress.connect(self.on_training_progress)
        self.training_signals.finished.connect(self.on_training_finished)

        # Prediction related
        self.prediction_signals = PredictionSignals()
        self.prediction_signals.progress.connect(self.on_prediction_progress)
        self.prediction_signals.finished.connect(self.on_prediction_finished)
        self.prediction_signals.image_ready.connect(self.on_prediction_image_ready)

        # TCP signals
        self.tcp_signals = TCPClientSignals()
        self.tcp_signals.connection_status.connect(self.on_tcp_connection_status)
        self.tcp_signals.message_received.connect(self.on_tcp_message_received)
        self.tcp_signals.message_sent.connect(self.on_tcp_message_sent)

        self.is_training = False
        self.is_predicting = False
        self.is_capturing_and_predicting = False
        self.training_start_time = None
        self.progress_dialog = None
        self.prediction_progress_dialog = None
        self.combined_progress_dialog = None
        self.current_model_path = None

        # Add a timer to track bounding box changes
        self.box_tracker_timer = QTimer()
        self.box_tracker_timer.timeout.connect(self.track_bounding_box_changes)
        self.box_tracker_timer.start(300)

        # Track previous box count
        self.previous_box_count = 0

        self.init_ui()

    def update_paths_from_recipe(self):
        """Update all paths based on the current recipe and selected capture mode"""
        if config_manager.current_recipe:
            recipe_folder = config_manager.get_current_recipe_folder()

            # Base dataset folder
            dataset_root = os.path.join(recipe_folder, "yolo_dataset")

            # Capture folder now depends on selected mode
            self.capture_folder = os.path.join(dataset_root, self.capture_mode)

            # Cropped save folder remains the same
            self.labeling_path = os.path.join(recipe_folder, "Annotation")

            # Create folders if they don't exist
            for folder in [dataset_root, self.capture_folder, self.labeling_path]:
                if folder:
                    os.makedirs(folder, exist_ok=True)

            print(f"Recipe: {config_manager.current_recipe}")
            print(f"Capture mode: {self.capture_mode}")
            print(f"Capture folder: {self.capture_folder}")

            # Update UI display
            if hasattr(self, 'recipe_label'):
                self.recipe_label.setText(
                    f"Recipe: {config_manager.current_recipe} | Mode: {self.capture_mode.capitalize()}"
                )
        else:
            self.capture_folder = None
            self.labeling_path = None
            print("No recipe selected - waiting for user to select a recipe")

            if hasattr(self, 'recipe_label'):
                self.recipe_label.setText("Recipe: None (Please select a recipe first)")

    def init_ui(self):
        """Initialize the main annotation page with all functions in one view"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ---------- Header Section ----------
        header_frame = QFrame()  # Create a frame for the header
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #001D3F;  /* Dark blue background */
                border-radius: 4px;
                padding: 0px;
            }
        """)

        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(6, 6, 6, 6)  # Add some padding inside

        # App title (with white text for contrast)
        title_label = QLabel("📸 Deep Learning")
        title_label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #ffffff;  /* White text */
            padding: 4px 8px;
        """)
        header_layout.addWidget(title_label)

        # Recipe info (light text on dark background)
        self.recipe_label = QLabel("Recipe: None")
        self.recipe_label.setStyleSheet("""
            font-size: 12px;
            color: #dbeafe;  /* Light blue text */
            padding: 6px 12px;
            border: 1px solid #3b82f6;
            border-radius: 4px;
            background-color: rgba(255, 255, 255, 0.1);  /* Slightly transparent */
        """)
        header_layout.addWidget(self.recipe_label)

        header_layout.addStretch()

        # Back button with white background
        back_btn = create_button("← Back", "#2c3e50", self.go_back_and_send_ok)  # Changed text color
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: white;  /* White background */
                color: #2c3e50;  /* Dark text */
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
                min-height: 28px;
                border: 1px solid #d1d5db;  /* Light gray border */
                margin-bottom: 10px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;  /* Slightly darker white on hover */
                border: 1px solid #9ca3af;
            }
            QPushButton:pressed {
                background-color: #e5e7eb;  /* Even darker when pressed */
            }
        """)
        back_btn.setFixedHeight(30)
        back_btn.setFixedWidth(100)
        header_layout.addWidget(back_btn)

        main_layout.addWidget(header_frame)  # Add the header frame instead of just the layout

        # # Recipe info (smaller)
        # self.recipe_label = QLabel("Recipe: None")
        # self.recipe_label.setStyleSheet("""
        #     font-size: 12px;
        #     color: #7f8c8d;
        #     padding: 6px 12px;
        #     border: 1px solid #bdc3c7;
        #     border-radius: 4px;
        #     background-color: #ecf0f1;
        # """)
        # header_layout.addWidget(self.recipe_label)

        # header_layout.addStretch()
        #
        # # Back button (smaller)
        # back_btn = create_button("← Back", "#999999", self.main_window.go_back)
        # back_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color: #999999;
        #         color: black;
        #         padding: 6px 8px;
        #         border-radius: 4px;
        #         font-weight: bold;
        #         font-size: 11px;
        #         min-height: 28px;
        #     }
        #     QPushButton:hover {
        #         background-color: #7f8c8d;
        #     }
        # """)
        # back_btn.setFixedHeight(28)
        # back_btn.setFixedWidth(80)
        # header_layout.addWidget(back_btn)
        #
        # main_layout.addLayout(header_layout)

        # ---------- Main Content with Splitter ----------
        splitter = QSplitter(Qt.Horizontal)

        # Left Panel - Image Viewer (70%)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)

        # Annotation widget
        self.viewer = AnnotationWidget(
            self.get_current_label,
            self.get_label_color
        )
        left_layout.addWidget(self.viewer, 1)

        # Image navigation (smaller)
        # Image navigation (smaller)
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)

        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.prev_image)
        self.prev_btn.setFixedHeight(32)
        self.prev_btn.setFixedWidth(100)  # Set fixed width for consistency
        self.prev_btn.setStyleSheet(self.get_button_style("#3498db", height=32))

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_image)
        self.next_btn.setFixedHeight(32)
        self.next_btn.setFixedWidth(100)  # Set same fixed width
        self.next_btn.setStyleSheet(self.get_button_style("#3498db", height=32))

        self.image_info = QLabel("No image loaded")
        self.image_info.setStyleSheet("""
            font-size: 11px; 
            color: #666; 
            padding: 6px;
            min-width: 200px;
        """)
        self.image_info.setAlignment(Qt.AlignCenter)  # Center align the text

        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(self.image_info)
        nav_layout.addStretch()

        left_layout.addLayout(nav_layout)

        splitter.addWidget(left_panel)

        # Right Panel - All Controls (30%)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        # ========== Annotation Tools ==========
        label_group = QGroupBox("📝 Annotation Tools")
        label_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #9b59b6;
                border-radius: 4px;
                padding-top: 8px;
                margin-top: 3px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
                color: #9b59b6;
            }
        """)

        label_form = QVBoxLayout()
        label_form.setSpacing(8)  # 稍微增加行间距

        # 第一行：标签选择器
        label_row = QHBoxLayout()
        label_row.setSpacing(8)

        # 标签文本 - 垂直居中对齐
        label = QLabel("Label:")
        label.setStyleSheet("""
            QLabel {
                padding: 0px;
                margin: 0px;
                font-size: 12px;
            }
        """)
        label.setAlignment(Qt.AlignVCenter)  # 垂直居中
        label.setMinimumHeight(30)  # 设置最小高度
        label_row.addWidget(label)

        # 下拉框
        self.label_combo = QComboBox()
        self.label_combo.addItems(self.labels)
        self.label_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                font-size: 11px;
                height: 30px;
                min-height: 30px;
                margin: 0px;
            }
        """)
        self.label_combo.setFixedHeight(30)  # 固定高度
        label_row.addWidget(self.label_combo)

        # "+ New" 按钮
        self.add_label_btn = QPushButton("+ New")
        self.add_label_btn.clicked.connect(self.auto_add_label)
        self.add_label_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
                height: 30px;
                min-height: 30px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:pressed {
                background-color: #7d3c98;
            }
        """)
        self.add_label_btn.setFixedHeight(30)  # 固定高度
        label_row.addWidget(self.add_label_btn)

        # 设置整行垂直居中对齐
        label_row.setAlignment(Qt.AlignVCenter)

        label_form.addLayout(label_row)

        # 第二行：快速按钮
        quick_buttons = QHBoxLayout()
        quick_buttons.setSpacing(8)

        self.undo_btn = QPushButton("↶ Undo")
        self.undo_btn.clicked.connect(self.undo)
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.undo_btn.setFixedHeight(30)

        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.clicked.connect(self.delete_selected)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.delete_btn.setFixedHeight(30)

        quick_buttons.addWidget(self.undo_btn)
        quick_buttons.addWidget(self.delete_btn)

        label_form.addLayout(quick_buttons)
        label_group.setLayout(label_form)
        right_layout.addWidget(label_group)

        # ========== Image Management ==========
        img_group = QGroupBox("📂 Image Management")
        img_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #3498db;
                border-radius: 4px;
                padding-top: 8px;
                margin-top: 3px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
                color: #3498db;
            }
        """)

        img_layout = QVBoxLayout()
        img_layout.setSpacing(6)

        self.open_folder_btn = QPushButton("📂 Open Folder")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.open_folder_btn.setStyleSheet(self.get_button_style("#3498db", height=30))

        self.capture_btn = QPushButton("📸 Capture Image")
        self.capture_btn.clicked.connect(self.capture_from_camera)
        if not CAMERA_AVAILABLE:
            self.capture_btn.setEnabled(False)
            self.capture_btn.setToolTip("Camera not available")
        self.capture_btn.setStyleSheet(self.get_button_style("#2ecc71", height=30))

        img_layout.addWidget(self.open_folder_btn)
        img_layout.addWidget(self.capture_btn)
        # Capture mode buttons
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(6)

        self.positive_btn = QPushButton("Positive")
        self.positive_btn.setCheckable(True)
        self.positive_btn.clicked.connect(lambda: self.set_capture_mode("positive"))
        self.positive_btn.setFixedHeight(30)

        self.negative_btn = QPushButton("Negative")
        self.negative_btn.setCheckable(True)
        self.negative_btn.clicked.connect(lambda: self.set_capture_mode("negative"))
        self.negative_btn.setFixedHeight(30)

        self.empty_btn = QPushButton("Empty")
        self.empty_btn.setCheckable(True)
        self.empty_btn.clicked.connect(lambda: self.set_capture_mode("empty"))
        self.empty_btn.setFixedHeight(30)

        mode_layout.addWidget(self.positive_btn)
        mode_layout.addWidget(self.negative_btn)
        mode_layout.addWidget(self.empty_btn)
        img_layout.addLayout(mode_layout)
        img_group.setLayout(img_layout)

        right_layout.addWidget(img_group)

        self.update_mode_buttons()

        # ========== AI Functions ==========
        ai_group = QGroupBox("🤖 AI Tools")
        ai_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #e67e22;
                border-radius: 4px;
                padding-top: 8px;
                margin-top: 3px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
                color: #e67e22;
            }
        """)

        ai_layout = QVBoxLayout()
        ai_layout.setSpacing(6)

        # Training
        self.train_btn = QPushButton("🚀 Train Model")
        self.train_btn.clicked.connect(self.train_model)
        self.train_btn.setStyleSheet(self.get_button_style("#e67e22", height=32))
        self.train_btn.setFixedHeight(32)
        ai_layout.addWidget(self.train_btn)

        # Prediction
        self.capture_predict_btn = QPushButton("📸 Auto Capture & Predict")
        self.capture_predict_btn.clicked.connect(self.capture_and_predict)
        self.capture_predict_btn.setStyleSheet(self.get_button_style("#e74c3c", height=32))
        self.capture_predict_btn.setFixedHeight(32)
        if not CAMERA_AVAILABLE:
            self.capture_predict_btn.setEnabled(False)
            self.capture_predict_btn.setToolTip("Camera not available")
        ai_layout.addWidget(self.capture_predict_btn)

        # Model info (smaller)
        self.model_info = QLabel("No model loaded")
        self.model_info.setStyleSheet("""
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 6px;
            color: #6c757d;
            font-size: 10px;
            margin-top: 3px;
        """)
        ai_layout.addWidget(self.model_info)

        ai_group.setLayout(ai_layout)
        right_layout.addWidget(ai_group)

        # ========== TCP & Automation ==========
        tcp_group = QGroupBox("🔌 TCP/Scan Automation")
        tcp_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #27ae60;
                border-radius: 4px;
                padding-top: 8px;
                margin-top: 3px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
                color: #27ae60;
            }
        """)

        tcp_layout = QVBoxLayout()
        tcp_layout.setSpacing(6)

        # Connection settings
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("IP:"))
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setPlaceholderText("Server IP")
        self.host_edit.setStyleSheet("""
            padding: 3px;
            font-size: 11px;
            height: 26px;
        """)
        conn_layout.addWidget(self.host_edit)

        conn_layout.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(1220)
        self.port_spin.setStyleSheet("""
            padding: 3px;
            font-size: 11px;
            height: 26px;
        """)
        self.port_spin.setFixedHeight(26)
        conn_layout.addWidget(self.port_spin)

        tcp_layout.addLayout(conn_layout)

        # Connection status (smaller)
        self.conn_status = QLabel("🔴 Disconnected")
        self.conn_status.setStyleSheet("""
            font-weight: bold;
            padding: 4px;
            border-radius: 4px;
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
            margin-top: 3px;
            font-size: 10px;
        """)
        tcp_layout.addWidget(self.conn_status)

        # Auto Scan button
        self.auto_tcp_btn = QPushButton("📡 Start Auto Scan")
        self.auto_tcp_btn.clicked.connect(self.auto_tcp_scan)
        self.auto_tcp_btn.setStyleSheet(self.get_button_style("#27ae60", height=32))
        self.auto_tcp_btn.setFixedHeight(32)
        tcp_layout.addWidget(self.auto_tcp_btn)

        # Scan instructions (smaller)
        scan_instructions = QLabel(
            "1. Draw bounding box\n"
            "2. Click 'Start Auto Scan'\n"
            "3. Auto-crop on TCP response"
        )
        scan_instructions.setStyleSheet("color: #666; font-size: 10px; padding: 6px;")
        tcp_layout.addWidget(scan_instructions)

        # TCP Messages
        msg_group = QGroupBox("TCP Messages")
        msg_group.setStyleSheet("""
            QGroupBox {
                font-weight: normal;
                border: 1px solid #8e44ad;
                border-radius: 4px;
                padding-top: 6px;
                margin-top: 3px;
                font-size: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px 0 3px;
                color: #8e44ad;
            }
        """)

        msg_layout = QVBoxLayout()
        msg_layout.setSpacing(4)

        # Create scrollable text area for messages
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(80)
        scroll_area.setMaximumHeight(120)

        self.tcp_messages_display = QTextEdit()
        self.tcp_messages_display.setReadOnly(True)
        self.tcp_messages_display.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 3px;
                font-family: monospace;
                font-size: 10px;
                color: #495057;
                padding: 4px;
            }
        """)

        scroll_area.setWidget(self.tcp_messages_display)
        msg_layout.addWidget(scroll_area)

        # Clear button
        clear_btn = QPushButton("Clear Messages")
        clear_btn.clicked.connect(self.clear_tcp_messages)
        clear_btn.setStyleSheet(self.get_button_style("#6c757d", height=26))
        clear_btn.setFixedHeight(26)
        msg_layout.addWidget(clear_btn, 0, Qt.AlignRight)

        msg_group.setLayout(msg_layout)
        tcp_layout.addWidget(msg_group)

        tcp_group.setLayout(tcp_layout)
        right_layout.addWidget(tcp_group)

        right_layout.addStretch()

        splitter.addWidget(right_panel)

        # Set splitter sizes
        splitter.setSizes([700, 300])
        main_layout.addWidget(splitter, 1)

        # ---------- Status Bar ----------
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.StyledPanel)
        status_frame.setStyleSheet("background-color: #f8f9fa; border-top: 1px solid #dee2e6;")

        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(6, 3, 6, 3)

        self.status_label = QLabel("✅ Ready")
        self.status_label.setStyleSheet("font-size: 11px; color: #495057;")

        # Recipe info
        self.recipe_info = QLabel("")
        self.recipe_info.setStyleSheet("font-size: 10px; color: #6c757d;")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.recipe_info)

        main_layout.addWidget(status_frame)

        self.setLayout(main_layout)

        # ---------- Shortcuts ----------
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.train_model)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.capture_and_predict)
        QShortcut(QKeySequence("Ctrl+A"), self, activated=self.auto_add_label)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.auto_tcp_scan)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_folder)

    def refresh_recipe_info(self):
        """Refresh all recipe-related information"""
        print("=== refresh_recipe_info called ===")

        # Get current recipe from config_manager
        current_recipe = config_manager.current_recipe
        print(f"Current recipe from config_manager: {current_recipe}")

        # Update paths based on current recipe
        self.update_paths_from_recipe()

        # Update UI labels
        if current_recipe:
            print(f"Recipe found: {current_recipe}")
            self.recipe_label.setText(f"Recipe: {current_recipe}")

            # Update status bar
            if hasattr(self, 'recipe_info'):
                self.recipe_info.setText(f"📁 {current_recipe}")

            # Update folder info in status
            if self.capture_folder:
                self.status_label.setText(
                    f"📸 Capture folder: {os.path.basename(self.capture_folder)} ({self.capture_mode})"
                )

            # Auto-load model if available and not loaded
            if not hasattr(self, 'current_model') or self.current_model is None:
                # Check if there are any models in the recipe folder
                models_folder = config_manager.get_current_yolo_model_folder()
                if models_folder and os.path.exists(models_folder):
                    model_files = [f for f in os.listdir(models_folder) if f.endswith('.pt')]
                    if model_files:
                        print(f"Found {len(model_files)} models in {models_folder}")
                        # Optionally auto-load the latest model
                        # self.auto_load_latest_model()
        else:
            print("No recipe found")
            self.recipe_label.setText("Recipe: None (Please select a recipe first)")
            if hasattr(self, 'recipe_info'):
                self.recipe_info.setText("")
            self.status_label.setText("✅ Ready - No recipe selected")

            # Clear any loaded model
            if hasattr(self, 'current_model'):
                self.current_model = None
            if hasattr(self, 'model_info'):
                self.model_info.setText("No model loaded")

    def showEvent(self, event):
        """Called when the page is shown - refresh recipe info"""
        print("=" * 50)
        print("DeepLearningPage showEvent triggered")
        print(f"Current recipe from config_manager: {config_manager.current_recipe}")
        print("=" * 50)

        # Refresh the recipe info
        self.refresh_recipe_info()

        # Also update paths
        self.update_paths_from_recipe()

        super().showEvent(event)

    def go_back_and_send_ok(self):
        """Go back to previous page and send OK to TCP server if connected"""

        # Send OK to TCP server if connected
        if self.tcp_connected and self.tcp_socket:
            try:
                message = "OK"
                self.tcp_socket.sendall(message.encode('utf-8'))
                self.tcp_signals.message_sent.emit(message)

                timestamp = time.strftime("%H:%M:%S")
                self.update_tcp_messages(f"[{timestamp}] 📤 Sent: {message} (from Back button)")

                # Optional: Show brief notification
                self.show_notification("Sent 'OK' to server", "success")

                # Wait a moment for the message to be sent before closing
                QTimer.singleShot(200, self.main_window.go_back)
            except socket.error as e:
                print(f"Failed to send OK on back button: {e}")
                self.main_window.go_back()  # Still go back even if send fails
        else:
            # Not connected, just go back
            self.main_window.go_back()

    def get_button_style(self, color, height=30):
        """Get consistent button style - smaller version"""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
                font-weight: bold;
                font-size: 11px;
                min-height: {height}px;
            }}
            QPushButton:hover {{
                background-color: {self.darken_color(color)};
            }}
            QPushButton:disabled {{
                background-color: #bdc3c7;
                color: #7f8c8d;
            }}
        """

    def darken_color(self, hex_color):
        """Darken a hex color for hover effect"""
        # Remove # if present
        hex_color = hex_color.lstrip('#')

        # Convert to RGB
        rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

        # Darken by 20%
        dark_rgb = tuple(max(0, int(c * 0.8)) for c in rgb)

        # Convert back to hex
        return f"#{dark_rgb[0]:02x}{dark_rgb[1]:02x}{dark_rgb[2]:02x}"

    # ---------- Simplified Core Functions ----------

    def open_folder(self):
        """Simplified folder opening"""
        self.update_paths_from_recipe()

        if not self.capture_folder:
            self.show_notification("Please select a recipe first", "warning")
            return

        folder = self.capture_folder
        os.makedirs(folder, exist_ok=True)

        self.image_files = sorted([
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith((".bmp", ".jpg", ".jpeg", ".png"))
        ])

        if not self.image_files:
            self.show_notification(f"No images found in:\n{folder}", "warning")
            return

        self.current_index = 0
        self.load_current_image()

        # Load existing annotations for all images
        self.load_all_existing_annotations()

        # Update status
        self.status_label.setText(f"Loaded {len(self.image_files)} images from Capture Image folder")

    def load_current_image(self):
        """Load the current image into the viewer"""
        if self.current_index < 0 or self.current_index >= len(self.image_files):
            return

        path = self.image_files[self.current_index]

        # Clear current boxes
        self.viewer.boxes.clear()

        # Load the image
        self.viewer.load_image(path)
        self.image_path = path

        # Restore boxes if we have them saved
        if hasattr(self, 'image_boxes') and path in self.image_boxes:
            self.viewer.boxes = self.image_boxes[path].copy()
            print(f"✓ Restored {len(self.viewer.boxes)} boxes for {os.path.basename(path)}")

        self.setWindowTitle(
            f"BMP Annotation Tool – {os.path.basename(path)} "
            f"({self.current_index + 1}/{len(self.image_files)})"
        )

        # Update image info label
        if hasattr(self, 'image_info'):
            self.image_info.setText(f"{os.path.basename(path)} ({self.current_index + 1}/{len(self.image_files)})")

        # Force update
        self.viewer.update()

    def load_all_existing_annotations(self):
        """Load all existing YOLO annotations into memory"""
        print("Loading existing annotations...")
        for image_path in self.image_files:
            # Check if YOLO annotation file exists
            yolo_path = os.path.splitext(image_path)[0] + ".txt"
            if os.path.exists(yolo_path):
                try:
                    # Load image to get dimensions
                    from PIL import Image
                    img = Image.open(image_path)
                    img_width, img_height = img.size

                    boxes = []
                    with open(yolo_path, 'r') as f:
                        for line in f:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                class_id = int(parts[0])
                                x_center = float(parts[1])
                                y_center = float(parts[2])
                                width = float(parts[3])
                                height = float(parts[4])

                                # Convert YOLO format to pixel coordinates
                                x1 = (x_center - width / 2) * img_width
                                y1 = (y_center - height / 2) * img_height
                                x2 = (x_center + width / 2) * img_width
                                y2 = (y_center + height / 2) * img_height

                                # Create QRectF
                                rect = QRectF(x1, y1, x2 - x1, y2 - y1)

                                # Store label (use class_id as label)
                                label = str(class_id)

                                boxes.append((rect, label))

                    if boxes:
                        self.image_boxes[image_path] = boxes
                        print(f"  Loaded {len(boxes)} boxes from {os.path.basename(yolo_path)}")

                except Exception as e:
                    print(f"Error loading annotation for {image_path}: {e}")

        print(f"✓ Total images with annotations: {len(self.image_boxes)}")

    def next_image(self):
        """Navigate to next image"""
        if self.current_index < 0:
            return
        self.save_current()  # This saves boxes
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.load_current_image()

    def prev_image(self):
        """Navigate to previous image"""
        if self.current_index < 0:
            return
        self.save_current()  # This saves boxes
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()

    def save_current(self):
        """Save annotations for current image in YOLO format"""
        if hasattr(self, "image_path") and self.image_path:
            # Save to file
            self.viewer.save_annotations(self.image_path)

            # Also store in memory
            if hasattr(self.viewer, 'boxes'):
                # Initialize image_boxes if it doesn't exist
                if not hasattr(self, 'image_boxes'):
                    self.image_boxes = {}

                self.image_boxes[self.image_path] = self.viewer.boxes.copy()
                print(f"✓ Saved boxes for {os.path.basename(self.image_path)}: {len(self.viewer.boxes)} boxes")

    # ---------- Annotation Functions ----------

    def auto_add_label(self):
        """Add new label with auto-numbering"""
        self.label_counter += 1
        new_label = str(self.label_counter)

        if new_label not in self.labels:
            self.labels.append(new_label)
            self.label_colors[new_label] = self.generate_color()
            self.label_combo.addItem(new_label)
            self.label_combo.setCurrentText(new_label)

            self.show_notification(f"Added label: {new_label}", "info")

    def delete_selected(self):
        self.viewer.delete_selected()
        self.show_notification("Deleted selected", "info")

    def undo(self):
        self.viewer.undo_last()
        self.show_notification("Undid last action", "info")

    def get_current_label(self):
        return self.label_combo.currentText()

    def get_label_color(self, label):
        return self.label_colors.get(label, QColor(255, 255, 255))

    def generate_color(self):
        """Generate random but distinct color"""
        hue = random.randint(0, 359)
        saturation = random.randint(150, 255)
        value = random.randint(150, 255)
        return QColor.fromHsv(hue, saturation, value)

    # ---------- Camera Functions ----------

    def capture_from_camera(self):
        """Simple camera capture"""
        self.update_paths_from_recipe()
        self.save_current()

        if not self.capture_folder:
            self.show_notification("Please select a recipe first", "warning")
            return

        os.makedirs(self.capture_folder, exist_ok=True)

        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("Capturing...")
        self.status_label.setText("📸 Capturing image...")

        def run_capture():
            def callback(success, message, image_path):
                if success and image_path:
                    base_name = os.path.basename(image_path)
                    save_path = os.path.join(self.capture_folder, base_name)

                    count = 1
                    name, ext = os.path.splitext(base_name)
                    while os.path.exists(save_path):
                        save_path = os.path.join(self.capture_folder, f"{name}_{count}{ext}")
                        count += 1

                    os.rename(image_path, save_path)
                    image_path = save_path

                self.camera_signals.finished.emit(success, message, image_path)

            AutoCaptureFlow(callback=callback)

        thread = threading.Thread(target=run_capture, daemon=True)
        thread.start()

    def on_camera_finished(self, success, message, image_path):
        """Handle camera completion"""
        self.capture_btn.setEnabled(True)
        self.capture_btn.setText("📸 Capture Image")

        if success and image_path:
            if image_path not in self.image_files:
                self.image_files.append(image_path)
                self.image_files.sort()

            self.current_index = self.image_files.index(image_path)
            self.load_current_image()
            self.show_notification("Image captured successfully!", "success")
        else:
            self.show_notification(f"Capture failed: {message}", "error")

    # ---------- Training Functions ----------

    def train_model(self):
        """Simplified training with auto setup"""
        if self.is_training:
            self.show_notification("Training already in progress", "warning")
            return

        config_manager = ConfigManager()
        if not config_manager.current_recipe:
            self.show_notification("Please select a recipe first", "warning")
            return

        recipe_name = config_manager.current_recipe
        folder_path = config_manager.get_current_yolo_dataset_folder()

        if not folder_path or not os.path.exists(folder_path):
            self.show_notification(f"No dataset folder for {recipe_name}", "error")
            return

        # Get recipe folder for class mapping
        recipe_folder = config_manager.get_current_recipe_folder()
        recipe_folder1 = os.path.join(recipe_folder, "Annotation")

        # Use recipe folder as labeling path
        labeling_path = recipe_folder1

        # Check if auto split needed
        train_images_dir = os.path.join(folder_path, "images", "train")
        if not os.path.exists(train_images_dir):
            reply = QMessageBox.question(
                self, "Auto Setup",
                "Dataset needs organization. Auto-setup for YOLO training?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            self.status_label.setText("Setting up dataset...")

            # FIXED: Call the correct method with proper parameters
            success = self.viewer.auto_split_and_generate_yaml(folder_path, labeling_path)

            if not success:
                self.show_notification("Setup failed", "error")
                return
            else:
                self.show_notification("Dataset setup complete!", "success")

        # Get training parameters with simple dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Training Settings")
        dialog.setModal(True)

        layout = QVBoxLayout()

        # Epochs
        epoch_layout = QHBoxLayout()
        epoch_layout.addWidget(QLabel("Epochs:"))
        epoch_spin = QSpinBox()
        epoch_spin.setRange(10, 1000)
        epoch_spin.setValue(100)
        epoch_layout.addWidget(epoch_spin)
        layout.addLayout(epoch_layout)

        # Batch size
        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("Batch Size:"))
        batch_spin = QSpinBox()
        batch_spin.setRange(1, 64)
        batch_spin.setValue(16)
        batch_layout.addWidget(batch_spin)
        layout.addLayout(batch_layout)

        # Model size
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Model:"))
        model_combo = QComboBox()
        model_combo.addItems(["Small (fast)", "Medium (balanced)", "Large (accurate)"])
        model_combo.setCurrentIndex(1)
        model_layout.addWidget(model_combo)
        layout.addLayout(model_layout)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setLayout(layout)

        if dialog.exec() != QDialog.Accepted:
            return

        # Map model selection
        model_map = {
            "Small (fast)": "yolo11n.pt",
            "Medium (balanced)": "yolo11m.pt",
            "Large (accurate)": "yolo11l.pt"
        }
        model_name = model_map[model_combo.currentText()]

        # Get save path
        save_dir = self.get_training_save_path(recipe_name)

        # Show progress
        self.progress_dialog = QProgressDialog(
            f"Training {recipe_name}...", "Cancel", 0, 100, self
        )
        self.progress_dialog.setWindowTitle("Training AI Model")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_training)

        self.is_training = True
        self.training_start_time = datetime.now()

        # Start training
        yaml_path = os.path.join(folder_path, "data.yaml")
        thread = threading.Thread(
            target=self.run_training_with_monitoring,
            args=(yaml_path, epoch_spin.value(), batch_spin.value(),
                  model_name, save_dir, recipe_name),
            daemon=True
        )
        thread.start()

    def on_training_progress(self, progress, status, time_remaining):
        """Update training progress dialog"""
        if not self.is_training:
            return

        if self.progress_dialog:
            try:
                self.progress_dialog.setValue(progress)

                elapsed_time = datetime.now() - self.training_start_time
                elapsed_str = str(elapsed_time).split('.')[0]

                status_text = f"{status}\n"
                status_text += f"Elapsed: {elapsed_str}\n"
                status_text += f"ETA: {time_remaining}"

                self.progress_dialog.setLabelText(status_text)
                self.status_label.setText(f"Training: {status.split('|')[0] if '|' in status else status}")

                self.setWindowTitle(f"Easy AI Tool - Training {progress}%")

            except Exception as e:
                print(f"Error updating progress: {e}")

    def on_training_finished(self, success, message):
        """Handle training completion"""
        self.is_training = False

        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Reset window title
        if hasattr(self, 'image_path') and self.image_path:
            self.setWindowTitle(f"Easy AI Tool - {os.path.basename(self.image_path)}")
        else:
            self.setWindowTitle("Deep Learning")

        if success:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except:
                pass

            # Show success message
            success_dialog = QMessageBox(self)
            success_dialog.setWindowTitle("🎉 Training Complete!")
            success_dialog.setText(message)
            success_dialog.setIcon(QMessageBox.Information)

            success_dialog.setStandardButtons(
                QMessageBox.Ok |
                QMessageBox.Open
            )

            success_dialog.button(QMessageBox.Ok).setText("ok")
            success_dialog.button(QMessageBox.Open).setText("Open Results")

            if success_dialog.exec() == QMessageBox.Open:
                import re
                match = re.search(r"Run directory: (.*?)\n", message)
                if match:
                    run_dir = match.group(1)
                    if os.path.exists(run_dir):
                        os.startfile(run_dir)

            self.show_notification("Training completed successfully!", "success")
        else:
            QMessageBox.critical(self, "Training Failed", message)
            self.show_notification("Training failed", "error")

    def run_training_with_monitoring(self, yaml_path, epochs, batch_size, model_name, save_dir, recipe_name):
        """Run YOLOv11 training - FORCE save to recipe's yolo_model folder"""
        try:
            from ultralytics import YOLO
            import torch
            import shutil

            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.training_signals.progress.emit(0, f"Initializing training on {device}...", "Starting...")

            # Create timestamped folder in yolo_model
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            run_name = f"train_{timestamp}"

            # DIRECT SAVE PATH - No "runs/detect" nonsense
            direct_save_dir = os.path.join(save_dir, run_name)
            os.makedirs(direct_save_dir, exist_ok=True)

            # Create weights folder inside our direct path
            direct_weights_dir = os.path.join(direct_save_dir, "weights")
            os.makedirs(direct_weights_dir, exist_ok=True)

            model = YOLO(model_name)
            self.training_signals.progress.emit(5, f"Model {model_name} loaded", "Preparing dataset...")

            start_time = datetime.now()

            try:
                # IMPORTANT: Train to a TEMP location first
                temp_project = os.path.join(save_dir, "_temp_training")
                os.makedirs(temp_project, exist_ok=True)

                # In the run_training_with_monitoring method, update the model.train() call:

                results = model.train(
                    data=yaml_path,
                    epochs=epochs,
                    batch=batch_size,
                    device=device,
                    project=save_dir,
                    name=run_name,
                    exist_ok=True,
                    verbose=True,
                    save=True,
                    save_period=min(10, epochs // 10),
                    plots=True,
                    workers=0,
                    patience=50,  # Early stopping patience
                    seed=42,

                    # --- ENHANCED PARAMETERS FOR BETTER SPECIFICITY ---
                    hsv_h=0.0,  # Keep as 0.0 - no color augmentation
                    hsv_s=0.0,  # Keep as 0.0 - no saturation changes
                    hsv_v=0.1,  # REDUCED from 0.2 - less brightness variation
                    degrees=0.0,  # Keep as 0.0 - no rotation
                    translate=0.01,  # REDUCED from 0.05 - less translation
                    scale=0.0,  # ADDED - minimal scaling (10%)
                    shear=0.0,  # ADDED - no shearing
                    perspective=0.0,  # ADDED - no perspective distortion
                    flipud=0.0,  # Keep as 0.0
                    fliplr=0.0,  # Keep as 0.0
                    mosaic=0.0,  # ADDED - disable mosaic augmentation
                    mixup=0.0,  # ADDED - disable mixup augmentation
                    copy_paste=0.0,  # ADDED - disable copy-paste augmentation

                    # Add these for better precision
                    overlap_mask=False,  # For segmentation, but works with detection too
                    mask_ratio=4,  # Not directly applicable but keep
                    dropout=0.1,  # ADDED - helps prevent overfitting to wrong features

                    # Increase confidence threshold during training (optional)
                    # This makes the model more selective
                    conf=0.3,  # Minimum confidence threshold

                    # Use focal loss for harder examples
                    fl_gamma=1.5,  # Focal loss gamma - focuses on hard examples

                    # Class weights if you have class imbalance
                    # class_weights={0: 1.0, 1: 1.5}  # Example
                )

                # AFTER TRAINING: Manually move files to desired location
                temp_run_dir = os.path.join(temp_project, run_name)
                if os.path.exists(temp_run_dir):
                    # Move everything from temp to our desired location
                    for item in os.listdir(temp_run_dir):
                        src = os.path.join(temp_run_dir, item)
                        dst = os.path.join(direct_save_dir, item)

                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)

                    # Clean up temp directory
                    shutil.rmtree(temp_project)

            except KeyboardInterrupt:
                results = None
                # Clean up temp on interrupt
                if os.path.exists(temp_project):
                    shutil.rmtree(temp_project, ignore_errors=True)

            if self.is_training and results:
                self.training_signals.progress.emit(100, "Training completed!", "Processing final results...")

                # Check for best.pt in our DIRECT location
                best_model_path = os.path.join(direct_weights_dir, "best.pt")

                if os.path.exists(best_model_path):
                    # Create easy-access copy
                    easy_access_name = f"best_{recipe_name}_{timestamp}.pt"
                    easy_access_path = os.path.join(save_dir, easy_access_name)
                    shutil.copy2(best_model_path, easy_access_path)

                    success_message = (
                        f"✅ Training completed!\n\n"
                        f"📁 Recipe: {recipe_name}\n"
                        f"📁 Model location: {direct_save_dir}\n"
                        f"📊 Best model: {easy_access_name}\n"
                        f"📏 File size: {os.path.getsize(easy_access_path) / 1024 / 1024:.1f} MB\n"
                        f"⏱ Training time: {str(datetime.now() - start_time).split('.')[0]}"
                    )
                else:
                    # Fallback: check if YOLO saved elsewhere
                    success_message = f"✅ Training completed!\nCheck folder: {direct_save_dir}"

                self.training_signals.finished.emit(True, success_message)

            elif not self.is_training:
                self.training_signals.finished.emit(False, "Training cancelled")
            else:
                self.training_signals.finished.emit(False, "Training completed but no results")

        except Exception as e:
            import traceback
            error_msg = f"Training failed:\n{str(e)}"
            print(traceback.format_exc())
            self.training_signals.finished.emit(False, error_msg)
        finally:
            self.is_training = False

    def get_training_save_path(self, recipe_name):
        """Get training save path - directly to recipe's yolo_model folder"""
        config_manager = ConfigManager()

        if not config_manager.current_recipe:
            return None

        # Get recipe folder
        recipe_folder = config_manager.get_current_recipe_folder()

        # Create yolo_model folder directly in recipe folder
        yolo_model_folder = os.path.join(recipe_folder, "yolo_model")
        os.makedirs(yolo_model_folder, exist_ok=True)

        return yolo_model_folder  # Returns: recipes\{current_recipe}\yolo_model

    def run_training_with_monitoring(self, yaml_path, epochs, batch_size, model_name, save_dir, recipe_name):
        """Run YOLOv11 training - SAVE to recipe's yolo_model folder, NOT runs/"""
        try:
            from ultralytics import YOLO
            import torch
            import os

            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.training_signals.progress.emit(0, f"Initializing training on {device}...", "Starting...")

            # Create our folder structure inside yolo_model
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            train_folder = f"train_{timestamp}"

            # OUR TARGET: recipes/{current_recipe}/yolo_model/train_{timestamp}/
            our_target_dir = os.path.join(save_dir, train_folder)

            # Create the directory
            os.makedirs(our_target_dir, exist_ok=True)

            print(f"🚀 Target save location: {our_target_dir}")
            print(f"📁 Should NOT be in: {os.path.join(os.getcwd(), 'runs', 'detect')}")

            # Load model
            model = YOLO(model_name)
            self.training_signals.progress.emit(5, f"Model {model_name} loaded", "Preparing dataset...")

            start_time = datetime.now()

            try:
                # CRITICAL: These parameters force YOLO to save to OUR location
                results = model.train(
                    data=yaml_path,
                    epochs=epochs,
                    batch=batch_size,
                    device=device,

                    # ==== THESE CONTROL SAVE LOCATION ====
                    project=save_dir,  # Base: recipes/{recipe}/yolo_model
                    name=train_folder,  # Subfolder: train_{timestamp}
                    save_dir=our_target_dir,  # Explicit: Force save here

                    # Prevent YOLO from using its defaults
                    exist_ok=True,
                    verbose=True,  # See where it's saving
                    save=True,
                    plots=True,
                )

                print(f"✅ Training complete. Check if saved to: {our_target_dir}")

            except KeyboardInterrupt:
                results = None
                print("Training interrupted")

            if self.is_training and results:
                self.training_signals.progress.emit(100, "Training completed!", "Processing final results...")

                # Verify save location
                verification = self._verify_save_location(our_target_dir, save_dir)

                success_message = verification

                self.training_signals.finished.emit(True, success_message)

            elif not self.is_training:
                self.training_signals.finished.emit(False, "Training cancelled")
            else:
                self.training_signals.finished.emit(False, "Training completed but no results")

        except Exception as e:
            import traceback
            error_msg = f"Training failed:\n{str(e)}"
            print(f"Error details:\n{traceback.format_exc()}")
            self.training_signals.finished.emit(False, error_msg)
        finally:
            self.is_training = False

    def _verify_save_location(self, target_dir, save_dir):
        """Verify and report where files were saved"""
        import glob

        message = "📊 Training Results:\n\n"

        # Check OUR target location
        target_files = []
        if os.path.exists(target_dir):
            for root, dirs, files in os.walk(target_dir):
                for file in files:
                    if file.endswith('.pt') or file.endswith('.png'):
                        target_files.append(os.path.join(root, file))

        message += f"1. TARGET location ({target_dir}):\n"
        if target_files:
            message += f"   ✅ Found {len(target_files)} model files\n"
            for f in target_files[:3]:  # Show first 3
                message += f"   - {os.path.relpath(f, target_dir)}\n"
            if len(target_files) > 3:
                message += f"   ... and {len(target_files) - 3} more\n"
        else:
            message += "   ❌ No model files found\n"

        # Check if YOLO defaulted to runs/detect
        runs_detect = os.path.join(os.getcwd(), "runs", "detect")
        if os.path.exists(runs_detect):
            run_folders = os.listdir(runs_detect)
            message += f"\n2. YOLO's default runs/detect folder:\n"
            if run_folders:
                message += f"   ⚠️ Found {len(run_folders)} run folders\n"
                latest = max([os.path.join(runs_detect, f) for f in run_folders],
                             key=os.path.getmtime)
                message += f"   Latest: {os.path.basename(latest)}\n"

                # If YOLO saved here instead, MOVE it
                if not target_files and run_folders:
                    moved = self._move_from_runs_to_target(latest, save_dir)
                    if moved:
                        message += f"\n   🔄 MOVED to recipe folder!\n"
            else:
                message += "   ✅ Empty (good!)\n"

        # Create easy-access model file
        best_model = self._create_easy_access_model(target_dir, save_dir)
        if best_model:
            message += f"\n3. Easy access model created:\n"
            message += f"   📁 {os.path.basename(best_model)}\n"
            message += f"   📍 {best_model}\n"

        return message

    def _move_from_runs_to_target(self, runs_folder, save_dir):
        """Move files from runs/detect to our recipe folder"""
        try:
            import shutil

            # Create timestamped folder
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            our_folder = os.path.join(save_dir, f"train_{timestamp}")

            # Copy everything
            if os.path.exists(runs_folder):
                shutil.copytree(runs_folder, our_folder)

                # Clean up runs folder
                shutil.rmtree(runs_folder)

                return our_folder
        except Exception as e:
            print(f"Move failed: {e}")

        return None

    def _create_easy_access_model(self, target_dir, save_dir):
        """Create a best.pt file in the yolo_model root for easy loading"""
        try:
            # Look for best.pt in the target directory
            best_pt = None

            # Check common locations
            possible_paths = [
                os.path.join(target_dir, "weights", "best.pt"),
                os.path.join(target_dir, "best.pt"),
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    best_pt = path
                    break

            if best_pt:
                # Copy to root of yolo_model for easy access
                import shutil
                easy_name = f"best_{os.path.basename(save_dir)}_{datetime.now().strftime('%Y%m%d')}.pt"
                easy_path = os.path.join(save_dir, easy_name)
                shutil.copy2(best_pt, easy_path)
                return easy_path

        except Exception as e:
            print(f"Create easy access failed: {e}")

        return None

    # ---------- Prediction Functions ----------

    def load_model(self):
        """Simplified model loading"""
        config_manager = ConfigManager()
        if not config_manager.current_recipe:
            self.show_notification("Select a recipe first", "warning")
            return

        default_folder = config_manager.get_current_yolo_model_folder()

        model_path, _ = QFileDialog.getOpenFileName(
            self, "Select AI Model",
            default_folder if os.path.exists(default_folder) else "",
            "Model Files (*.pt)"
        )

        if not model_path:
            return

        self.status_label.setText("Loading model...")

        try:
            from ultralytics import YOLO
            import torch

            self.current_model = YOLO(model_path)
            self.current_model_path = model_path

            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            model_name = os.path.basename(model_path)
            model_size = os.path.getsize(model_path) / (1024 * 1024)

            self.capture_predict_btn.setEnabled(True)
            self.capture_predict_btn.setEnabled(CAMERA_AVAILABLE)

            self.model_info.setText(
                f"✅ Model loaded\n"
                f"Name: {model_name}\n"
                f"Size: {model_size:.1f} MB\n"
                f"Device: {device}"
            )

            self.show_notification(f"Model '{model_name}' loaded", "success")

        except Exception as e:
            self.show_notification(f"Failed to load model: {str(e)}", "error")
            self.current_model = None
            self.capture_predict_btn.setEnabled(False)

    def predict_current_image(self, class_filter=None, show_progress=True):
        """Simple prediction"""
        if not hasattr(self, 'current_model') or self.current_model is None:
            self.show_notification("Load a model first", "warning")
            return

        if not hasattr(self, 'image_path') or not self.image_path:
            self.show_notification("Open an image first", "warning")
            return

        # 先清掉旧的 dialog 参考，避免残留
        self.prediction_progress_dialog = None

        if show_progress:
            self.prediction_progress_dialog = QProgressDialog(
                "Running AI detection.", "Cancel", 0, 100, self
            )
            self.prediction_progress_dialog.setWindowTitle("AI Detection")
            self.prediction_progress_dialog.setMinimumDuration(0)
            self.prediction_progress_dialog.canceled.connect(self.cancel_prediction)
            self.prediction_progress_dialog.show()

        self.is_predicting = True

        thread = threading.Thread(
            target=self.run_prediction,
            args=(self.image_path, class_filter),
            daemon=True
        )
        thread.start()

    def on_prediction_progress(self, progress, status):
        """Update prediction progress"""
        if self.prediction_progress_dialog:
            self.prediction_progress_dialog.setValue(progress)
            self.prediction_progress_dialog.setLabelText(status)
            self.status_label.setText(f"Prediction: {status}")

    def on_prediction_finished(self, success, message, predictions):
        """Handle prediction completion"""
        self.is_predicting = False

        if self.prediction_progress_dialog:
            self.prediction_progress_dialog.close()
            self.prediction_progress_dialog = None

        if success:
            self.show_notification(f"Prediction complete: {message}", "success")

            # if predictions:
            #     dialog = QDialog(self)
            #     dialog.setWindowTitle("Save Predictions")
            #     dialog.setModal(True)
            #
            #     layout = QVBoxLayout()
            #     layout.addWidget(QLabel(f"Found {len(predictions)} objects.\nSelect format to save:"))
            #
            #     radio_yolo = QRadioButton("YOLO format")
            #     radio_pixel = QRadioButton("Pixel coordinates")
            #     radio_both = QRadioButton("Both formats")
            #     radio_yolo.setChecked(True)
            #
            #     layout.addWidget(radio_yolo)
            #     layout.addWidget(radio_pixel)
            #     layout.addWidget(radio_both)
            #
            #     buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            #     buttons.accepted.connect(dialog.accept)
            #     buttons.rejected.connect(dialog.reject)
            #     layout.addWidget(buttons)
            #
            #     dialog.setLayout(layout)
            #
            #     if dialog.exec() == QDialog.Accepted:
            #         if radio_yolo.isChecked():
            #             format_type = "yolo"
            #         elif radio_pixel.isChecked():
            #             format_type = "pixel"
            #         elif radio_both.isChecked():
            #             format_type = "both"
            #
            #         self.viewer.save_predictions_as_annotations(self.image_path, predictions, format_type)
            #         self.show_notification("Predictions saved", "success")
        else:
            self.show_notification(f"Prediction failed: {message}", "error")

    def on_prediction_image_ready(self, image_path):
        """Load predicted image"""
        try:
            if os.path.exists(image_path):
                self.viewer.load_image(image_path)
                self.viewer.update()
                self.setWindowTitle(f"Easy AI Tool - {os.path.basename(image_path)} (Predicted)")
        except Exception as e:
            print(f"Error loading predicted image: {e}")

    def run_prediction(self, image_path, class_filter=None):
        """Run prediction on image"""
        try:
            from ultralytics import YOLO
            import torch

            self.prediction_signals.progress.emit(10, "Loading model...")

            if not hasattr(self, 'current_model') or self.current_model is None:
                if hasattr(self, 'current_model_path') and self.current_model_path:
                    self.current_model = YOLO(self.current_model_path)
                else:
                    self.prediction_signals.finished.emit(False, "No model loaded", [])
                    return

            device = 'cuda' if torch.cuda.is_available() else 'cpu'

            if class_filter is not None:
                self.prediction_signals.progress.emit(30, f"Detecting class {class_filter} on {device}...")
            else:
                self.prediction_signals.progress.emit(30, f"Detecting all classes on {device}...")

            results = self.current_model.predict(
                source=image_path,
                conf=0.5,
                iou=0.45,
                device=device,
                save=False,
                save_txt=False,
                save_conf=True,
                show=False,
                verbose=False,
                classes=[class_filter] if class_filter is not None else None
            )

            self.prediction_signals.progress.emit(70, "Processing results...")

            predictions = []
            if results and len(results) > 0:
                result = results[0]

                if hasattr(result, 'boxes') and result.boxes is not None:
                    boxes = result.boxes

                    if hasattr(boxes, 'xyxy') and boxes.xyxy is not None:
                        num_detections = len(boxes.xyxy)
                    else:
                        num_detections = 0

                    for i in range(num_detections):
                        try:
                            box = boxes.xyxy[i].cpu().numpy()
                            conf = float(boxes.conf[i].cpu().numpy()) if boxes.conf is not None else 0.0
                            cls = int(boxes.cls[i].cpu().numpy()) if boxes.cls is not None else 0

                            actual_class_name = ""
                            if hasattr(result, 'names') and result.names:
                                actual_class_name = result.names.get(cls, f"class_{cls}")
                            else:
                                actual_class_name = f"class_{cls}"

                            predictions.append({
                                'bbox': box.tolist(),
                                'confidence': conf,
                                'class_id': cls,
                                'class_name': actual_class_name,
                                'class_name_original': actual_class_name
                            })
                        except Exception as e:
                            print(f"Error processing detection {i}: {e}")
                            continue

            output_dir = os.path.join(os.path.dirname(image_path), "predictions")
            os.makedirs(output_dir, exist_ok=True)

            output_filename = f"pred_{os.path.basename(image_path)}"
            output_path = os.path.join(output_dir, output_filename)

            if results and len(results) > 0:
                result.save(filename=output_path)

            self.prediction_signals.progress.emit(90, "Saving results...")

            self.viewer.display_predictions(predictions)

            if class_filter is not None:
                class_names = self.current_model.names if hasattr(self.current_model, 'names') else {}
                class_name = class_names.get(class_filter, f"class_{class_filter}")
                message = f"Found {len(predictions)} objects of class {class_filter} ({class_name})"
            else:
                message = f"Found {len(predictions)} objects"

            self.prediction_signals.progress.emit(100, "Done!")
            self.prediction_signals.finished.emit(True, message, predictions)
            self.prediction_signals.image_ready.emit(output_path)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            error_msg = f"Prediction failed:\n{str(e)}"
            print(error_details)
            self.prediction_signals.finished.emit(False, error_msg, [])
        finally:
            self.is_predicting = False

    def capture_and_predict(self):
        """Simplified capture and predict with auto model loading"""
        if not CAMERA_AVAILABLE:
            self.show_notification("Camera not available", "error")
            return

        self.update_paths_from_recipe()

        # First, try to auto-load the latest model for current recipe
        if not hasattr(self, 'current_model') or self.current_model is None:
            model_loaded = self.auto_load_latest_model()
            if not model_loaded:
                return  # Stop if no model found

        self.save_current()

        # Ask for detection mode
        dialog = QDialog(self)
        dialog.setWindowTitle("Detection Mode")
        dialog.setModal(True)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("What to detect?"))

        all_classes = QRadioButton("All objects")
        specific_class = QRadioButton("Specific object type")
        all_classes.setChecked(True)

        layout.addWidget(all_classes)
        layout.addWidget(specific_class)

        # Class selection if specific
        class_combo = QComboBox()
        if hasattr(self.current_model, 'names'):
            for class_id, class_name in sorted(self.current_model.names.items()):
                class_combo.addItem(f"{class_id}: {class_name}", class_id)
        layout.addWidget(class_combo)
        class_combo.setVisible(False)

        # Show/hide combo based on selection
        def toggle_class_combo():
            class_combo.setVisible(specific_class.isChecked())

        all_classes.toggled.connect(lambda: class_combo.setVisible(False))
        specific_class.toggled.connect(lambda: class_combo.setVisible(True))

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setLayout(layout)

        if dialog.exec() != QDialog.Accepted:
            return

        # Determine class filter
        class_filter = None
        if specific_class.isChecked() and class_combo.currentIndex() >= 0:
            class_filter = class_combo.currentData()

        # Capture image
        self.capture_predict_btn.setEnabled(False)
        self.capture_predict_btn.setText("Capturing...")

        self.camera_worker = CameraWorker(self.capture_folder)
        self.camera_worker.finished.connect(
            lambda success, msg, path: self.on_capture_for_prediction(success, msg, path, class_filter)
        )

        thread = threading.Thread(target=self.camera_worker.capture_image, daemon=True)
        thread.start()

    def set_capture_mode(self, mode):
        """Switch between positive / negative / empty capture folders"""
        self.capture_mode = mode
        self.update_paths_from_recipe()
        self.update_mode_buttons()

        # Clear currently loaded image list when switching folder
        self.image_files = []
        self.current_index = -1
        self.viewer.boxes.clear()
        self.viewer.update()

        if hasattr(self, 'image_info'):
            self.image_info.setText(f"No image loaded ({mode})")

        self.show_notification(f"Switched to {mode} folder", "info")

    def update_mode_buttons(self):
        """Update button checked states and colors"""
        buttons = {
            "positive": self.positive_btn,
            "negative": self.negative_btn,
            "empty": self.empty_btn
        }

        for mode, btn in buttons.items():
            is_active = (self.capture_mode == mode)
            btn.setChecked(is_active)

            if is_active:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2ecc71;
                        color: white;
                        border: 2px solid #1e8449;
                        border-radius: 4px;
                        padding: 6px 12px;
                        font-weight: bold;
                        font-size: 11px;
                        min-height: 30px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ecf0f1;
                        color: #2c3e50;
                        border: 1px solid #bdc3c7;
                        border-radius: 4px;
                        padding: 6px 12px;
                        font-weight: bold;
                        font-size: 11px;
                        min-height: 30px;
                    }
                    QPushButton:hover {
                        background-color: #dfe6e9;
                    }
                """)

    def auto_load_latest_model(self):
        """Automatically find and load the latest model for current recipe"""
        config_manager = ConfigManager()
        if not config_manager.current_recipe:
            self.show_notification("Select a recipe first", "warning")
            return False

        # Look for models in the recipe's yolo_model folder
        models_folder = config_manager.get_current_yolo_model_folder()

        if not os.path.exists(models_folder):
            self.show_notification(f"No model folder found for {config_manager.current_recipe}", "error")
            return False

        # Find all .pt files
        model_files = []
        for root, dirs, files in os.walk(models_folder):
            for file in files:
                if file.lower().endswith('.pt'):
                    full_path = os.path.join(root, file)
                    # Skip temp or partial files
                    if 'temp' not in file.lower() and 'partial' not in file.lower():
                        model_files.append(full_path)

        if not model_files:
            self.show_notification(f"No AI models found in {config_manager.current_recipe}", "error")
            return False

        # Sort by modification time (newest first)
        model_files.sort(key=os.path.getmtime, reverse=True)

        # Try to load the newest model
        latest_model = model_files[0]
        model_name = os.path.basename(latest_model)

        self.status_label.setText(f"Auto-loading {model_name}...")

        try:
            from ultralytics import YOLO
            import torch

            self.current_model = YOLO(latest_model)
            self.current_model_path = latest_model

            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            model_size = os.path.getsize(latest_model) / (1024 * 1024)

            self.capture_predict_btn.setEnabled(True)
            self.capture_predict_btn.setEnabled(True)

            self.model_info.setText(
                f"✅ Auto-loaded model\n"
                f"Name: {model_name}\n"
                f"Size: {model_size:.1f} MB\n"
                f"Device: {device}\n"
                f"Classes: {len(self.current_model.names) if hasattr(self.current_model, 'names') else 'Unknown'}"
            )

            self.show_notification(f"Auto-loaded model: {model_name}", "success")
            return True

        except Exception as e:
            self.show_notification(f"Failed to auto-load model: {str(e)}", "error")
            self.current_model = None
            self.capture_predict_btn.setEnabled(False)
            return False

    def on_capture_for_prediction(self, success, message, image_path, class_filter):
        """Handle capture for prediction"""
        self.capture_predict_btn.setEnabled(True)
        self.capture_predict_btn.setText("📸 Auto Capture & Predict")

        if success and image_path:
            if image_path not in self.image_files:
                self.image_files.append(image_path)
                self.image_files.sort()

            self.current_index = self.image_files.index(image_path)
            self.load_current_image()

            # Double-check model is loaded
            if not hasattr(self, 'current_model') or self.current_model is None:
                self.show_notification("Model not loaded for prediction", "error")
                return

            # Wait and predict
            QTimer.singleShot(1000, lambda: self.predict_current_image(class_filter))
        else:
            self.show_notification(f"Capture failed: {message}", "error")

    # ---------- TCP Functions ----------

    def auto_tcp_scan(self):
        """Simplified TCP scan"""
        if not hasattr(self.viewer, 'boxes') or not self.viewer.boxes:
            self.show_notification("Draw a bounding box first", "warning")
            return

        if not hasattr(self, 'image_path') or not self.image_path:
            self.show_notification("Load an image first", "warning")
            return

        self.status_label.setText("Connecting TCP...")

        if not self.tcp_connected:
            self.connect_tcp()
            QTimer.singleShot(1000, self.perform_scan_id_after_connect)
        else:
            self.perform_scan_id()

    def connect_tcp(self):
        """Connect to TCP server"""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()

        if not host:
            self.show_notification("Enter server IP", "warning")
            return

        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(2)

            self.auto_tcp_btn.setEnabled(False)
            self.auto_tcp_btn.setText("Connecting...")
            self.conn_status.setText("🟡 Connecting...")

            def connect_thread():
                try:
                    self.tcp_socket.connect((host, port))
                    self.tcp_connected = True
                    self.tcp_signals.connection_status.emit(f"Connected to {host}:{port}", True)
                    self.start_listening()
                except socket.error as e:
                    self.tcp_signals.connection_status.emit(f"Connection failed: {str(e)}", False)
                    self.tcp_socket = None

            self.tcp_thread = threading.Thread(target=connect_thread, daemon=True)
            self.tcp_thread.start()

        except Exception as e:
            self.on_tcp_connection_status(f"Connection error: {str(e)}", False)

    def perform_scan_id_after_connect(self):
        """Perform scan after connection"""
        if self.tcp_connected:
            self.perform_scan_id()
        else:
            self.show_notification("Failed to connect to TCP server", "error")

    def perform_scan_id(self):
        """Send OK message via TCP"""
        if not self.tcp_connected or not self.tcp_socket:
            QMessageBox.warning(self, "Not Connected",
                                "TCP connection failed. Please check settings.")
            return

        if not hasattr(self.viewer, 'boxes') or not self.viewer.boxes:
            QMessageBox.warning(self, "No Bounding Boxes",
                                "Please draw at least one bounding box first")
            return

        try:
            # Just send "OK" instead of coordinates
            message = "learn"
            message1 = "scan"

            self.tcp_socket.sendall(message.encode('utf-8'))
            self.tcp_signals.message_sent.emit(message)
            self.tcp_signals.message_sent.emit(message1)

            timestamp = time.strftime("%H:%M:%S")
            self.update_tcp_messages(f"[{timestamp}] 📡 Sent: {message}")

            self.status_label.setText("Message 'OK' sent to server")

            # Show brief notification
            self.show_scan_success_notification(message)

        except socket.error as e:
            self.update_tcp_messages(f"[Error] Failed to send: {str(e)}")
            QMessageBox.critical(self, "Send Failed",
                                 f"Failed to send message:\n{str(e)}")

    def show_scan_success_notification(self, message):
        """Show a brief success notification"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("TCP Message Sent")
        msg_box.setText(f"✅ Message sent!\n\n"
                        f"Message: {message}\n"
                        f"Server: {self.host_edit.text()}:{self.port_spin.value()}")
        msg_box.setIcon(QMessageBox.Information)

        # Auto-close after 2 seconds
        QTimer.singleShot(2000, msg_box.close)
        msg_box.show()

    def start_listening(self):
        """Start listening for TCP messages"""

        def listen_thread():
            while self.tcp_connected and self.tcp_socket:
                try:
                    data = self.tcp_socket.recv(1024)
                    if data:
                        message = data.decode('utf-8').strip()
                        self.tcp_signals.message_received.emit(message)
                    else:
                        if self.tcp_connected:
                            self.tcp_signals.connection_status.emit("Server disconnected", False)
                        break
                except socket.timeout:
                    continue
                except socket.error:
                    if self.tcp_connected:
                        self.tcp_signals.connection_status.emit("Connection lost", False)
                    break

        self.listening_thread = threading.Thread(target=listen_thread, daemon=True)
        self.listening_thread.start()

    # ---------- Helper Functions ----------

    def show_notification(self, message, type="info"):
        """Show notification message"""
        colors = {
            "success": "#d4edda",
            "error": "#f8d7da",
            "warning": "#fff3cd",
            "info": "#d1ecf1"
        }

        text_colors = {
            "success": "#155724",
            "error": "#721c24",
            "warning": "#856404",
            "info": "#0c5460"
        }

        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"""
            font-weight: bold;
            padding: 5px;
            border-radius: 3px;
            background-color: {colors.get(type, '#f8f9fa')};
            color: {text_colors.get(type, '#495057')};
            border: 1px solid {text_colors.get(type, '#dee2e6')};
        """)

        clear_time = 5000 if type in ["success", "error"] else 3000
        QTimer.singleShot(clear_time, lambda: self.status_label.setText("✅ Ready"))

    def track_bounding_box_changes(self):
        """Track when new bounding boxes are drawn"""
        if hasattr(self.viewer, 'boxes'):
            current_count = len(self.viewer.boxes)

            if current_count > self.previous_box_count:
                latest_box, latest_label = self.viewer.boxes[-1]
                self.last_bounding_box = (latest_box, latest_label)
                self.last_box_label = latest_label

                timestamp = time.strftime("%H:%M:%S")
                self.update_tcp_messages(f"[{timestamp}] 📦 Box drawn: {latest_label}")

            self.previous_box_count = current_count

    def update_tcp_messages(self, message):
        """Update TCP messages display"""
        current_text = self.tcp_messages_display.toPlainText()

        if current_text:
            new_text = f"{message}\n{current_text}"
        else:
            new_text = message

        self.tcp_messages_display.setPlainText(new_text)

        cursor = self.tcp_messages_display.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.tcp_messages_display.setTextCursor(cursor)

    def clear_tcp_messages(self):
        """Clear TCP messages"""
        self.tcp_messages_display.clear()
        self.show_notification("Messages cleared", "info")

    # ---------- Signal Handlers ----------

    def on_tcp_connection_status(self, message, is_connected):
        """Handle TCP connection status"""
        self.tcp_connected = is_connected
        self.auto_tcp_btn.setEnabled(True)
        self.auto_tcp_btn.setText("📡 Start Auto Scan")

        if is_connected:
            self.conn_status.setText("🟢 Connected")
            self.conn_status.setStyleSheet("""
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            """)
            self.show_notification("TCP connected", "success")
        else:
            self.conn_status.setText("🔴 Disconnected")
            self.conn_status.setStyleSheet("""
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            """)
            self.show_notification(f"TCP: {message}", "error")

    def on_tcp_message_received(self, message):
        """Handle received TCP messages"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] 📥 {message}")
        self.status_label.setText(f"TCP: {message[:50]}...")

        self.scan_data_received = message
        self.tcp_received_text = message.strip()

        # Auto crop on TCP message
        self.auto_crop_and_save_on_tcp_message(message)

    def on_tcp_message_sent(self, message):
        """Handle sent TCP messages"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] 📤 {message}")

    def auto_crop_and_save_on_tcp_message(self, tcp_message):
        """Auto crop and save image when TCP receives message"""
        if not self.is_ready_for_auto_crop():
            self.update_tcp_messages(f"[AutoCrop] ⚠️ Not ready for auto-crop")
            return False

        sanitized_text = self.sanitize_filename(tcp_message)
        if not sanitized_text:
            sanitized_text = "unknown"
            self.update_tcp_messages(f"[AutoCrop] ⚠️ Using 'unknown' as TCP text was empty")

        try:
            image = Image.open(self.image_path)
            img_width, img_height = image.size

            box, label = self.last_bounding_box

            x1 = max(0, int(box.x()))
            y1 = max(0, int(box.y()))
            x2 = min(img_width, int(box.x() + box.width()))
            y2 = min(img_height, int(box.y() + box.height()))

            if x1 >= x2 or y1 >= y2:
                self.update_tcp_messages(f"[AutoCrop] ❌ Invalid bounding box dimensions")
                return False

            cropped_image = image.crop((x1, y1, x2, y2))

            label_name = label.split()[0] if ' ' in label else label
            filename = f"{label_name}_{sanitized_text}.bmp"
            save_path = os.path.join(self.labeling_path, filename)

            counter = 1
            while os.path.exists(save_path):
                filename = f"{label_name}_{sanitized_text}_{counter}.bmp"
                save_path = os.path.join(self.labeling_path, filename)
                counter += 1

            cropped_image.save(save_path, "BMP")

            crop_width = x2 - x1
            crop_height = y2 - y1

            self.update_tcp_messages(f"[AutoCrop] ✅ Auto-saved cropped image!")
            self.update_tcp_messages(f"[AutoCrop]   Filename: {filename}")
            self.update_tcp_messages(f"[AutoCrop]   Label: {label_name}")
            self.update_tcp_messages(f"[AutoCrop]   TCP Text: {sanitized_text}")
            self.update_tcp_messages(f"[AutoCrop]   Dimensions: {crop_width}x{crop_height} pixels")
            self.update_tcp_messages(f"[AutoCrop]   Saved to: {self.labeling_path}")

            config_manager = ConfigManager()
            if config_manager.current_recipe:
                self.update_tcp_messages(f"[AutoCrop]   Recipe: {config_manager.current_recipe}")

            self.status_label.setText(f"Auto-saved: {filename}")

            if self.tcp_connected and self.tcp_socket:
                try:
                    response = f"AUTO_CROP_SAVED: {filename}"
                    self.tcp_socket.sendall(response.encode('utf-8'))
                    self.tcp_signals.message_sent.emit(response)
                except socket.error as e:
                    self.update_tcp_messages(f"[Error] Failed to send confirmation: {str(e)}")

            QTimer.singleShot(100, lambda: self.show_auto_crop_notification(filename, label_name, sanitized_text))

            return True

        except Exception as e:
            error_msg = f"Auto-crop failed: {str(e)}"
            self.update_tcp_messages(f"[AutoCrop] ❌ {error_msg}")
            print(f"Auto-crop error: {e}")
            return False

    def is_ready_for_auto_crop(self):
        """Check if ready for auto-cropping"""
        if not hasattr(self, 'image_path') or not self.image_path or not os.path.exists(self.image_path):
            return False

        if not self.last_bounding_box:
            self.update_tcp_messages(f"[AutoCrop] ❌ No bounding box drawn")
            return False

        if not self.last_box_label:
            self.update_tcp_messages(f"[AutoCrop] ❌ No label for bounding box")
            return False

        if not os.path.exists(self.labeling_path):
            try:
                os.makedirs(self.labeling_path, exist_ok=True)
            except:
                self.update_tcp_messages(f"[AutoCrop] ❌ Cannot create save folder")
                return False

        return True

    def sanitize_filename(self, text):
        """Sanitize TCP text for filename"""
        if not text:
            return "unknown"

        import re
        sanitized = re.sub(r'[^\w\-_]', '', text)

        if len(sanitized) > 50:
            sanitized = sanitized[:50]

        if not sanitized:
            sanitized = "tcp_text"

        return sanitized

    def show_auto_crop_notification(self, filename, label_name, tcp_text):
        """Show auto-crop notification"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Auto Crop & Save")
        msg_box.setText(f"✅ Auto-saved cropped image!\n\n"
                        f"📄 {filename}\n"
                        f"🏷️ Label: {label_name}\n"
                        f"📡 TCP Text: {tcp_text}")
        msg_box.setIcon(QMessageBox.Information)

        QTimer.singleShot(2000, msg_box.close)
        msg_box.show()

    # ---------- Cancel Functions ----------

    def cancel_training(self):
        """Cancel training"""
        if self.is_training:
            self.is_training = False
            self.status_label.setText("Training cancelled")

            try:
                import signal
                import os
                print("Attempting to cancel training...")
            except:
                pass

            self.show_notification("Training cancelled", "info")

    def cancel_prediction(self):
        """Cancel prediction"""
        if self.is_predicting:
            self.is_predicting = False
            self.status_label.setText("Prediction cancelled")
            self.show_notification("Prediction cancelled", "info")

    def disconnect_tcp(self):
        """Disconnect TCP"""
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass

        self.tcp_connected = False
        self.tcp_socket = None
        self.auto_tcp_btn.setText("📡 Start Auto Scan")
        self.auto_tcp_btn.setEnabled(True)
        self.conn_status.setText("🔴 Disconnected")
        self.update_tcp_messages("[System] Disconnected from server")



    def closeEvent(self, event):
        """Handle window close"""
        self.box_tracker_timer.stop()

        if self.is_training or self.is_predicting:
            reply = QMessageBox.question(
                self, "Operation in Progress",
                "Stop and exit?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            else:
                self.is_training = False
                self.is_predicting = False

        self.save_current()

        if self.tcp_connected:
            self.disconnect_tcp()

        event.accept()