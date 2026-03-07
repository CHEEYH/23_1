import os
import random
import threading
import socket
import time
import json
import numpy as np
import cv2
from datetime import datetime
from PIL import Image
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton,
    QMessageBox, QLabel, QLineEdit, QFormLayout, QGroupBox
)
from PySide6.QtGui import QKeySequence, QShortcut, QColor
from PySide6.QtCore import Signal, QObject, QTimer, Qt, QRectF
from ui.components.annotator2 import AnnotationWidget
from config_manager import config_manager

# Import Heartbeat Manager
from ui.components.heartbeat_manager import HeartbeatManager

# Import camera capture function
try:
    from camera.camera import AutoCaptureFlow

    CAMERA_AVAILABLE = True
except ImportError as e:
    CAMERA_AVAILABLE = False
    print(f"Warning: camera module not found. Camera button will be disabled. Error: {e}")


class CameraSignals(QObject):
    """Signals for camera thread communication"""
    finished = Signal(bool, str, object)  # success, message, image_path


class Calibration:
    """Handles camera calibration data and transformations"""

    def __init__(self):
        self.pixel_points = []  # List of (x, y) pixel coordinates
        self.world_points = []  # List of (x, y) world coordinates
        self.calibration_matrix = None
        self.is_calibrated = False
        self.calibration_file = None

    def add_point_pair(self, pixel_point, world_point):
        """Add a pixel-world coordinate pair"""
        self.pixel_points.append(pixel_point)
        self.world_points.append(world_point)

    def perform_calibration(self):
        """Perform perspective transformation calibration"""
        if len(self.pixel_points) < 4:
            return False, "Need at least 4 points for calibration"

        try:
            # Convert to numpy arrays
            src = np.array(self.pixel_points, dtype=np.float32)
            dst = np.array(self.world_points, dtype=np.float32)

            # Calculate homography matrix (perspective transformation)
            self.calibration_matrix, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)

            if self.calibration_matrix is not None:
                self.is_calibrated = True
                return True, "Calibration successful"
            else:
                return False, "Failed to calculate calibration matrix"

        except Exception as e:
            return False, f"Calibration error: {str(e)}"

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

    def get_calibration_status(self):
        """Get calibration status information"""
        return {
            'is_calibrated': self.is_calibrated,
            'num_points': len(self.pixel_points),
            'calibration_file': self.calibration_file
        }


class MainWindow(QMainWindow):
    def __init__(self, parent=None, block_id=None, block_name=None):
        self.capture_folder = None
        super().__init__(parent)

        # ===== USE HEARTBEAT MANAGER =====
        self.heartbeat_manager = None
        self.tcp_connected = False
        self.server_ip = "127.0.0.1"
        self.server_port = 8888

        # ===== RECIPE AND BLOCK INFORMATION =====
        self.block_id = block_id or "1"
        self.block_name = block_name or f"Block_{self.block_id}"

        self.setWindowTitle(f"BMP Annotation Tool - {self.block_name}")
        self.resize(1400, 900)

        # ===== RECIPE-BASED PATHS =====
        self.base_path = "C://Users//PC_AI_DS//Pictures//LaserCalibration//calibration.json"

        # Get recipe path
        self.recipe_path = self.get_current_recipe_path()

        # Define recipe-based paths
        if self.recipe_path:
            # Use paths within the current recipe
            self.capture_image_path = os.path.join(self.recipe_path, "Capture")
            self.labeling_path = os.path.join(self.recipe_path, "Labeling")
            self.boxes_json_path = os.path.join(self.recipe_path, "BoxesData")
            self.annotation_path = os.path.join(self.recipe_path, "Annotation")
        else:
            # Fallback to desktop paths if no recipe
            self.capture_image_path = f"{self.base_path}\\Capture Image"
            self.labeling_path = f"{self.base_path}\\Labeling"
            self.boxes_json_path = f"{self.base_path}\\BoxesData"
            self.annotation_path = f"{self.base_path}\\Annotation"

        # ===== BLOCK-SPECIFIC PATHS =====
        self.block_capture_path = os.path.join(self.capture_image_path, f"Block_{self.block_id}")
        self.block_boxes_path = os.path.join(self.boxes_json_path, f"Block_{self.block_id}")
        self.block_annotation_path = os.path.join(self.annotation_path, f"Block_{self.block_id}")

        self.image_boxes = {}

        # Start with 0 as the first label
        self.labels = ["0"]
        self.label_counter = 0
        self.label_colors = {"0": QColor(255, 0, 0)}

        self.image_files = []
        self.current_index = -1
        self.pending_box = None
        self.pending_box_label = None
        self.box_saved = False

        # Add calibration object
        self.calibration = Calibration()

        # Add calibration status label
        self.calibration_status = QLabel("No calibration loaded")
        self.calibration_status.setStyleSheet("color: #666; font-style: italic;")

        # Create necessary folders
        self.create_required_folders()

        # Initialize signals
        self.camera_signals = CameraSignals()
        self.camera_signals.finished.connect(self.on_camera_finished)

        # Add a timer to track bounding box changes
        self.box_tracker_timer = QTimer()
        self.box_tracker_timer.timeout.connect(self.track_bounding_box_changes)
        self.box_tracker_timer.start(300)

        # Track previous box count
        self.previous_box_count = 0

        self.init_ui()

        # Connect to existing HeartbeatManager instead of creating new socket
        QTimer.singleShot(100, self.connect_to_heartbeat_manager)

        # Load images from block-specific annotation folder
        QTimer.singleShot(200, self.load_block_annotation_images)

    def connect_to_heartbeat_manager(self):
        """Connect to the existing Heartbeat Manager instance"""
        try:
            # Try multiple methods to get the HeartbeatManager instance

            # Method 1: Check if it's in the QApplication instance
            app = QApplication.instance()
            if hasattr(app, 'heartbeat_manager'):
                self.heartbeat_manager = app.heartbeat_manager
                print("✅ Found HeartbeatManager in QApplication")

            # Method 2: Check parent window
            elif self.parent() and hasattr(self.parent(), 'heartbeat_manager'):
                self.heartbeat_manager = self.parent().heartbeat_manager
                print("✅ Found HeartbeatManager in parent window")

            # Method 3: Look for global instance
            else:
                # Try to find any existing HeartbeatManager instance
                import gc
                for obj in gc.get_objects():
                    if isinstance(obj, HeartbeatManager):
                        self.heartbeat_manager = obj
                        print("✅ Found existing HeartbeatManager instance in memory")
                        break

            # If still not found, create a new one but don't connect
            if not self.heartbeat_manager:
                print("⚠️ No existing HeartbeatManager found, creating new one")
                self.heartbeat_manager = HeartbeatManager()
                # Note: Don't call connect() - let external system handle connection

            # Connect to heartbeat manager signals
            if self.heartbeat_manager:
                self.heartbeat_manager.connection_status_changed.connect(self.on_heartbeat_status_changed)

                # Check current connection status
                self.tcp_connected = self.heartbeat_manager.is_connected()

                if self.tcp_connected:
                    print(f"✅ Connected to existing Heartbeat Manager")
                    self.update_connection_status(True, "Connected via Heartbeat")
                else:
                    print(f"⚠️ Heartbeat Manager exists but not connected")
                    self.update_connection_status(False, "Heartbeat not connected")
            else:
                print(f"❌ Could not access Heartbeat Manager")
                self.update_connection_status(False, "Heartbeat Manager unavailable")

        except ImportError as e:
            print(f"❌ Could not import HeartbeatManager: {e}")
            self.update_connection_status(False, "Heartbeat Manager not found")
        except Exception as e:
            print(f"❌ Error connecting to Heartbeat Manager: {e}")
            self.update_connection_status(False, f"Error: {str(e)}")

    def on_heartbeat_status_changed(self, connected, message):
        """Handle heartbeat connection status changes"""
        self.tcp_connected = connected
        self.update_connection_status(connected, message)

        if connected:
            print(f"✅ Heartbeat connection active: {message}")
        else:
            print(f"⚠️ Heartbeat connection lost: {message}")

    def update_connection_status(self, connected, message=None):
        """Update the connection status UI"""
        if connected:
            self.connection_status.setText("🟢 Connected (Heartbeat)")
            self.connection_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            if message:
                self.connection_status.setToolTip(message)
        else:
            self.connection_status.setText("🔴 Disconnected")
            self.connection_status.setStyleSheet("color: #f39c12; font-style: italic;")
            if message:
                self.connection_status.setToolTip(message)
            else:
                self.connection_status.setToolTip("No Heartbeat connection")

    def send_coordinates(self, world_coord_string):
        """Send coordinates using Heartbeat Manager"""
        if not self.heartbeat_manager or not self.tcp_connected:
            print("⚠️ No Heartbeat connection - coordinates saved locally only")
            self.status_label.setText("⚠️ Coordinates saved locally only (no server connection)")
            return False

        try:
            # Use heartbeat manager to send data
            success = self.heartbeat_manager.send_data(world_coord_string)

            if success:
                print(f"✅ Sent coordinates via Heartbeat Manager")
                self.status_label.setText("✅ Coordinates sent to server")
                return True
            else:
                print(f"❌ Failed to send via Heartbeat Manager")
                self.status_label.setText("❌ Failed to send coordinates")
                return False

        except Exception as e:
            print(f"❌ Error sending via Heartbeat: {e}")
            self.status_label.setText(f"❌ Send error: {str(e)}")
            return False

    def get_current_recipe_path(self):
        """Get the path of current recipe folder"""
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

    def create_required_folders(self):
        """Create all required folders if they don't exist"""
        folders_to_create = [
            self.capture_image_path,
            self.labeling_path,
            self.boxes_json_path,
            self.annotation_path,
            self.block_capture_path,
            self.block_boxes_path,
            self.block_annotation_path,
        ]

        for folder in folders_to_create:
            try:
                os.makedirs(folder, exist_ok=True)
                print(f"Created/Verified folder: {folder}")
            except Exception as e:
                print(f"Error creating folder {folder}: {e}")

    def load_block_annotation_images(self):
        """Load images from block-specific annotation folder"""
        if os.path.exists(self.block_annotation_path):
            image_extensions = ['.bmp', '.jpg', '.jpeg', '.png']
            self.image_files = []

            for ext in image_extensions:
                pattern = os.path.join(self.block_annotation_path, f"*{ext}")
                self.image_files.extend(glob.glob(pattern))

            for ext in image_extensions:
                pattern = os.path.join(self.block_annotation_path, "**", f"*{ext}")
                self.image_files.extend(glob.glob(pattern, recursive=True))

            self.image_files = list(set(self.image_files))
            self.image_files.sort()

            if self.image_files:
                self.current_index = 0
                self.load_current_image()
                self.update_image_count_label()

    def update_image_count_label(self):
        """Update the image count information"""
        total = len(self.image_files)
        current = self.current_index + 1 if self.current_index >= 0 else 0
        self.image_count_label.setText(f"📸 {current}/{total} images")

    def init_ui(self):
        """Initialize the main annotation page"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # ---------- Recipe and Block Info Header ----------
        info_layout = QHBoxLayout()

        recipe_info = self.get_current_recipe_info()
        recipe_label = QLabel(f"📁 Recipe: {recipe_info}")
        recipe_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 6px 12px;
                border-radius: 4px;
            }
        """)

        block_label = QLabel(f"🔲 Block: {self.block_name}")
        block_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                color: white;
                background-color: #e67e22;
                padding: 6px 12px;
                border-radius: 4px;
            }
        """)

        info_layout.addWidget(recipe_label)
        info_layout.addWidget(block_label)
        info_layout.addStretch()

        self.image_count_label = QLabel("📸 0/0 images")
        self.image_count_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #2c3e50;
                padding: 6px;
                background-color: #ecf0f1;
                border-radius: 4px;
            }
        """)
        info_layout.addWidget(self.image_count_label)

        layout.addLayout(info_layout)

        # ---------- Top Toolbar ----------
        top_bar = QHBoxLayout()

        self.capture_btn = QPushButton("Capture Image")
        self.capture_btn.clicked.connect(self.capture_from_camera)
        if not CAMERA_AVAILABLE:
            self.capture_btn.setEnabled(False)
            self.capture_btn.setToolTip("Camera module not available")

        undo_btn = QPushButton("↶ Undo")
        undo_btn.clicked.connect(self.undo)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(self.delete_selected)

        self.save_box_btn = QPushButton("💾 Save Current Box")
        self.save_box_btn.clicked.connect(self.save_current_box)
        self.save_box_btn.setEnabled(False)
        self.save_box_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.previous_image)
        self.prev_btn.setEnabled(False)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_image)
        self.next_btn.setEnabled(False)

        top_bar.addWidget(self.capture_btn)
        top_bar.addWidget(undo_btn)
        top_bar.addWidget(delete_btn)
        top_bar.addWidget(self.save_box_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.prev_btn)
        top_bar.addWidget(self.next_btn)

        # ---------- Calibration Status Bar ----------
        cal_status_layout = QHBoxLayout()
        cal_status_layout.addWidget(QLabel("📐 Calibration:"))
        cal_status_layout.addWidget(self.calibration_status)
        cal_status_layout.addStretch()

        # Add connection status
        self.connection_status = QLabel("🔌 Connecting to Heartbeat...")
        self.connection_status.setStyleSheet("color: #f39c12; font-style: italic;")
        cal_status_layout.addWidget(self.connection_status)

        # ---------- Main Content Area ----------
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # ---------- Left Column: Annotation Viewer (70%) ----------
        left_column = QVBoxLayout()

        self.viewer = AnnotationWidget(
            self.get_current_label,
            self.get_label_color
        )

        self.viewer.status_message.connect(self.on_annotation_status)

        left_column.addWidget(self.viewer, 1)

        self.image_info_label = QLabel("No image loaded")
        self.image_info_label.setStyleSheet("color: #666; font-size: 12px; padding: 2px;")
        left_column.addWidget(self.image_info_label)

        content_layout.addLayout(left_column, 70)

        # ---------- Right Column: Block Info (30%) ----------
        right_column = QVBoxLayout()

        block_info_group = QGroupBox("Block Information")
        block_info_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #e67e22;
                border-radius: 8px;
                padding-top: 15px;
                margin-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #e67e22;
            }
        """)

        block_layout = QFormLayout(block_info_group)

        block_id_label = QLabel(self.block_id)
        block_id_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")

        block_name_label = QLabel(self.block_name)
        block_name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")

        block_layout.addRow("Block ID:", block_id_label)
        block_layout.addRow("Block Name:", block_name_label)

        if os.path.exists(self.block_capture_path):
            capture_status = "✅ Exists"
        else:
            capture_status = "❌ Not found"

        if os.path.exists(self.block_annotation_path):
            annotation_status = "✅ Exists"
        else:
            annotation_status = "❌ Not found"

        if os.path.exists(self.block_boxes_path):
            boxes_status = "✅ Exists"
        else:
            boxes_status = "❌ Not found"

        block_layout.addRow("Capture Folder:", QLabel(capture_status))
        block_layout.addRow("Annotation Folder:", QLabel(annotation_status))
        block_layout.addRow("Boxes Folder:", QLabel(boxes_status))

        right_column.addWidget(block_info_group)

        annotation_group = QGroupBox("Block Annotations")
        annotation_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #3498db;
                border-radius: 8px;
                padding-top: 15px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #3498db;
            }
        """)

        annotation_layout = QVBoxLayout(annotation_group)

        self.annotation_list_label = QLabel("Loading annotation images...")
        self.annotation_list_label.setWordWrap(True)
        self.annotation_list_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #7f8c8d;
                padding: 8px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
        """)
        annotation_layout.addWidget(self.annotation_list_label)

        refresh_btn = QPushButton("🔄 Refresh List")
        refresh_btn.clicked.connect(self.refresh_annotation_list)
        refresh_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                padding: 5px;
                background-color: #3498db;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        annotation_layout.addWidget(refresh_btn)

        right_column.addWidget(annotation_group)
        right_column.addStretch()

        content_layout.addLayout(right_column, 30)

        layout.addLayout(top_bar)
        layout.addLayout(cal_status_layout)
        layout.addLayout(content_layout)

        # ---------- Status Bar ----------
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # ---------- Shortcuts ----------
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_current_box)

    def refresh_annotation_list(self):
        """Refresh the annotation list display"""
        if os.path.exists(self.block_annotation_path):
            files = os.listdir(self.block_annotation_path)
            image_files = [f for f in files if f.lower().endswith(('.bmp', '.jpg', '.png'))]
            if image_files:
                text = "\n".join([f"• {f}" for f in image_files[:10]])
                if len(image_files) > 10:
                    text += f"\n... and {len(image_files) - 10} more"
                self.annotation_list_label.setText(text)
            else:
                self.annotation_list_label.setText("No annotation images found")
        else:
            self.annotation_list_label.setText("Annotation folder not found")

    def previous_image(self):
        """Navigate to previous image"""
        if self.current_index > 0:
            self.save_current()
            self.current_index -= 1
            self.load_current_image()
            self.update_navigation_buttons()
            self.update_image_count_label()

    def next_image(self):
        """Navigate to next image"""
        if self.current_index < len(self.image_files) - 1:
            self.save_current()
            self.current_index += 1
            self.load_current_image()
            self.update_navigation_buttons()
            self.update_image_count_label()

    def update_navigation_buttons(self):
        """Update navigation button states"""
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.image_files) - 1)

    def on_annotation_status(self, message):
        """Handle status messages from annotation widget"""
        self.status_label.setText(message)

    def track_bounding_box_changes(self):
        """Track when new bounding boxes are drawn"""
        if not hasattr(self.viewer, 'boxes'):
            return

        try:
            regular_count = len(self.viewer.boxes) if hasattr(self.viewer, 'boxes') else 0
            rotated_count = len(self.viewer.rotated_boxes) if hasattr(self.viewer, 'rotated_boxes') else 0
            current_count = regular_count + rotated_count

            if current_count > 1:
                self.viewer.safe_clear_boxes()

                self.last_bounding_box = None
                self.last_box_label = None
                self.pending_box = None
                self.pending_box_label = None
                self.previous_box_count = 0

                self.save_box_btn.setEnabled(False)
                self.save_box_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #cccccc;
                        color: #666666;
                        font-weight: bold;
                        padding: 5px;
                    }
                """)

                QTimer.singleShot(100, lambda: QMessageBox.critical(
                    self,
                    "Error",
                    "Only ONE bounding box allowed!\n\nAll boxes have been cleared."
                ))

                self.status_label.setText("Error: Only one box allowed. Boxes cleared.")

            else:
                self.previous_box_count = current_count

                if current_count == 1:
                    if regular_count == 1:
                        latest_box, latest_label = self.viewer.boxes[0]

                        self.last_bounding_box = (latest_box, latest_label)
                        self.last_box_label = latest_label
                        self.pending_box = latest_box
                        self.pending_box_label = latest_label

                        self.save_box_btn.setEnabled(True)
                        self.save_box_btn.setStyleSheet("""
                            QPushButton {
                                background-color: #4CAF50;
                                color: white;
                                font-weight: bold;
                                padding: 5px;
                            }
                        """)

                    elif rotated_count == 1:
                        rotated_box = self.viewer.rotated_boxes[0]
                        self.pending_box = None
                        self.pending_box_label = None
                        self.save_box_btn.setEnabled(False)
                else:
                    self.save_box_btn.setEnabled(False)
                    self.pending_box = None
                    self.pending_box_label = None
                    self.save_box_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #cccccc;
                            color: #666666;
                            font-weight: bold;
                            padding: 5px;
                        }
                    """)

        except Exception as e:
            print(f"Error in track_bounding_box_changes: {e}")
            self.viewer.safe_clear_boxes()
            self.save_box_btn.setEnabled(False)
            self.pending_box = None
            self.pending_box_label = None
            self.save_box_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc;
                    color: #666666;
                    font-weight: bold;
                    padding: 5px;
                }
            """)

    def save_current_box(self):
        """Save the current pending bounding box to JSON file and send via Heartbeat Manager"""
        if self.pending_box is None or self.pending_box_label is None:
            QMessageBox.warning(self, "No Box", "No bounding box available to save.")
            return

        if not hasattr(self, 'image_path') or not self.image_path:
            QMessageBox.warning(self, "No Image", "No image loaded.")
            return

        if not self.calibration.is_calibrated:
            QMessageBox.warning(
                self,
                "Calibration Required",
                "Calibration must be loaded before saving bounding box coordinates.\n\n"
                "Please capture an image with calibration first."
            )
            return

        if self.box_saved:
            QMessageBox.warning(
                self,
                "Box Already Saved",
                "Only one box can be saved per capture.\n\n"
                "Please capture a new image to save another box."
            )
            return

        try:
            image = Image.open(self.image_path)
            img_width, img_height = image.size

            box = self.pending_box

            x1 = max(0, int(box.x()))
            y1 = max(0, int(box.y()))
            x2 = min(img_width, int(box.x() + box.width()))
            y2 = min(img_height, int(box.y() + box.height()))

            corners_pixel = [
                (x1, y1),
                (x2, y1),
                (x2, y2),
                (x1, y2)
            ]

            world_corners = []
            for corner in corners_pixel:
                world_point = self.calibration.pixel_to_world(corner)
                if world_point:
                    world_corners.append(world_point)

            if not world_corners or len(world_corners) < 4:
                QMessageBox.critical(
                    self,
                    "Conversion Failed",
                    "Failed to convert pixel coordinates to world coordinates."
                )
                return

            preview_text = (
                f"Do you want to save this bounding box?\n\n"
                f"📍 World Coordinates:\n"
                f"   Point 1: ({world_corners[0][0]:.2f}, {world_corners[0][1]:.2f})\n"
                f"   Point 2: ({world_corners[1][0]:.2f}, {world_corners[1][1]:.2f})\n"
                f"   Point 3: ({world_corners[2][0]:.2f}, {world_corners[2][1]:.2f})\n"
                f"   Point 4: ({world_corners[3][0]:.2f}, {world_corners[3][1]:.2f})"
            )

            reply = QMessageBox.question(
                self,
                "Confirm Save",
                preview_text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                self.status_label.setText("Save cancelled")
                return

            # Save locally
            save_data = [
                [float(world_corners[0][0]), float(world_corners[0][1])],
                [float(world_corners[1][0]), float(world_corners[1][1])],
                [float(world_corners[2][0]), float(world_corners[2][1])],
                [float(world_corners[3][0]), float(world_corners[3][1])]
            ]

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"box_world_{timestamp_str}.json"
            save_path = os.path.join(self.block_boxes_path, filename)

            with open(save_path, 'w') as f:
                json.dump(save_data, f, indent=2)

            # Update UI
            self.box_saved = True
            self.save_box_btn.setEnabled(False)
            self.save_box_btn.setText("✓ Box Saved")
            self.save_box_btn.setStyleSheet("""
                QPushButton {
                    background-color: #808080;
                    color: white;
                    font-weight: bold;
                    padding: 5px;
                }
            """)
            self.pending_box = None
            self.pending_box_label = None

            # Show success message
            QMessageBox.information(
                self,
                "Box Saved",
                f"✅ Bounding box saved successfully!\n\n"
                f"📁 Block: {self.block_name}\n"
                f"📁 File: {filename}\n\n"
                f"Only one box can be saved per capture."
            )

            self.status_label.setText(f"Box saved: {filename}")

            # Format world coordinates for sending
            world_coord_string = (f"{world_corners[0][0]:.2f}_{world_corners[0][1]:.2f},"
                                  f"{world_corners[1][0]:.2f}_{world_corners[1][1]:.2f},"
                                  f"{world_corners[2][0]:.2f}_{world_corners[2][1]:.2f},"
                                  f"{world_corners[3][0]:.2f}_{world_corners[3][1]:.2f}")

            # Send using Heartbeat Manager
            self.send_coordinates(world_coord_string)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save bounding box:\n{str(e)}"
            )

    def delete_selected(self):
        """Delete selected bounding box"""
        self.viewer.delete_selected()
        if hasattr(self.viewer, 'boxes') and len(self.viewer.boxes) == 0:
            self.save_box_btn.setEnabled(False)
            self.pending_box = None
            self.pending_box_label = None

    def capture_from_camera(self):
        """Capture from camera and save to block-specific capture folder (only keep one image)"""
        calibration_file = "C://Users//PC_AI_DS//Pictures//LaserCalibration//calibration.json"

        if not os.path.exists(calibration_file):
            QMessageBox.critical(
                self,
                "Calibration File Not Found",
                f"Calibration file not found at:\n{calibration_file}\n\n"
                f"Please ensure the calibration.json file exists at this location."
            )
            return

        success, message = self.calibration.load_calibration(calibration_file)
        if success:
            self.calibration_status.setText(f"Calibration loaded - {len(self.calibration.pixel_points)} points")
            self.calibration_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.status_label.setText(f"✅ Calibration loaded from: {os.path.basename(calibration_file)}")
            print(f"✅ Calibration loaded from: {calibration_file}")
        else:
            QMessageBox.critical(
                self,
                "Calibration Failed",
                f"❌ Failed to load calibration file:\n{message}\n\n"
                f"File: {calibration_file}"
            )
            return

        self.capture_folder = self.block_capture_path
        self.save_current()
        os.makedirs(self.capture_folder, exist_ok=True)

        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("Capturing...")

        def run_capture():
            def callback(success, message, image_path):
                if success and image_path:
                    os.makedirs(self.capture_folder, exist_ok=True)

                    # 删除旧图，只保留最新一张
                    for file_name in os.listdir(self.capture_folder):
                        file_path = os.path.join(self.capture_folder, file_name)
                        if os.path.isfile(file_path) and file_name.lower().endswith((".bmp", ".jpg", ".jpeg", ".png")):
                            try:
                                os.remove(file_path)
                                print(f"Deleted old image: {file_path}")
                            except Exception as e:
                                print(f"Failed to delete old image {file_path}: {e}")

                    # 保存新图
                    base_name = os.path.basename(image_path)
                    save_path = os.path.join(self.capture_folder, base_name)

                    try:
                        os.replace(image_path, save_path)
                    except Exception:
                        import shutil
                        shutil.move(image_path, save_path)

                    image_path = save_path

                    # 只保留这一张
                    self.image_files = [image_path]
                    self.current_index = 0

                self.camera_signals.finished.emit(success, message, image_path)

            AutoCaptureFlow(callback=callback)

        thread = threading.Thread(target=run_capture, daemon=True)
        thread.start()

    def on_camera_finished(self, success, message, image_path):
        """Handle camera capture completion"""
        self.capture_btn.setEnabled(True)
        self.capture_btn.setText("Capture Image")

        self.box_saved = False
        self.save_box_btn.setText("💾 Save Current Box")
        self.save_box_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        if success and image_path:
            if os.path.exists(image_path):
                self.load_current_image()
                self.status_label.setText("Image captured and loaded successfully")
                self.update_navigation_buttons()
                self.update_image_count_label()
        else:
            QMessageBox.critical(self, "Capture Failed",
                                 f"Camera capture failed!\n{message}")

    def get_label_color(self, label):
        return self.label_colors.get(label, QColor(255, 255, 255))

    def generate_color(self):
        """Generate a random but distinct color for new labels"""
        hue = random.randint(0, 359)
        saturation = random.randint(150, 255)
        value = random.randint(150, 255)

        color = QColor.fromHsv(hue, saturation, value)
        return color

    def load_current_image(self):
        """Load the current image into the viewer"""
        if not self.image_files:
            return

        path = self.image_files[self.current_index]
        self.viewer.boxes.clear()
        self.viewer.load_image(path)
        self.image_path = path

        if path in self.image_boxes:
            self.viewer.boxes = self.image_boxes[path].copy()

        self.pending_box = None
        self.pending_box_label = None
        self.save_box_btn.setEnabled(False)
        self.box_saved = False
        self.save_box_btn.setText("💾 Save Current Box")
        self.save_box_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        self.setWindowTitle(
            f"BMP Annotation Tool – {self.block_name} – {os.path.basename(path)}"
        )

        self.image_info_label.setText(f"{os.path.basename(path)}")
        self.viewer.update()

    def get_current_label(self):
        """Get the current label from the combo box"""
        return self.label_combo.currentText() if hasattr(self, 'label_combo') else "0"

    def undo(self):
        """Undo last action"""
        self.viewer.undo_last()
        if hasattr(self.viewer, 'boxes') and len(self.viewer.boxes) == 0:
            self.save_box_btn.setEnabled(False)
            self.pending_box = None
            self.pending_box_label = None

    def save_current(self):
        """Save annotations for current image in YOLO format"""
        if hasattr(self, "image_path") and self.image_path:
            self.viewer.save_annotations(self.image_path)
            if hasattr(self.viewer, 'boxes'):
                self.image_boxes[self.image_path] = self.viewer.boxes.copy()

    def closeEvent(self, event):
        """Handle window close event - DON'T close the Heartbeat connection"""
        self.save_current()

        # Disconnect signals but don't close the heartbeat manager
        if self.heartbeat_manager:
            try:
                self.heartbeat_manager.connection_status_changed.disconnect(self.on_heartbeat_status_changed)
                print("🔌 Disconnected from Heartbeat Manager signals")
            except:
                pass

        # Clear references
        self.heartbeat_manager = None
        self.tcp_connected = False

        print("✅ MainWindow closed - Heartbeat Manager connection preserved")
        event.accept()


import sys
import glob
from PySide6.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--block_id', default='1')
    parser.add_argument('--block_name', default='Block_1')
    args = parser.parse_args()

    window = MainWindow(block_id=args.block_id, block_name=args.block_name)
    window.show()
    sys.exit(app.exec())