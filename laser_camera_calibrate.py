import os
import threading
import socket
import time
import json
import numpy as np
import cv2
import platform
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QMessageBox, QLabel,
    QLineEdit, QSpinBox, QFormLayout, QGroupBox,
    QTextEdit, QScrollArea, QProgressBar
)
from PySide6.QtCore import Signal, QObject, Qt, QTimer, QPoint
from PySide6.QtGui import QPixmap, QFont, QMouseEvent, QPainter, QPen, QColor, QTextCursor
from ui.components.heartbeat_manager import HeartbeatManager  # Add this import

# Import camera capture function
try:
    from camera.camera import AutoCaptureFlow

    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    print("Warning: camera_capture module not found. Camera button will be disabled.")


class HeartbeatManager(QObject):
    """Manages TCP connection heartbeat"""

    # Signals for UI updates
    connection_status_changed = Signal(bool, str)  # connected, message
    heartbeat_sent = Signal(str)  # heartbeat message
    message_received = Signal(str)  # NEW: signal for received messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self.socket = None
        self.connected = False
        self.server_ip = None
        self.server_port = None
        self.heartbeat_thread = None
        self.stop_heartbeat = threading.Event()
        self.lock = threading.Lock()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.message_queue = []  # Queue for messages to send

    def connect(self, server_ip, server_port, heartbeat_interval=5):
        """Connect to server and start heartbeat"""
        self.server_ip = server_ip
        self.server_port = server_port
        self.heartbeat_interval = heartbeat_interval

        # Close any existing connection
        self.disconnect()

        # Reset reconnect attempts on manual connect
        self.reconnect_attempts = 0

        try:
            # Create socket with better timeout settings
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Set socket options for better reconnection handling
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

            # Set a shorter connection timeout
            self.socket.settimeout(3)  # 3 second connection timeout

            # Connect with timeout
            self.socket.connect((server_ip, server_port))

            # Set longer timeout for operations after connection
            self.socket.settimeout(heartbeat_interval + 2)

            self.connected = True
            self.stop_heartbeat.clear()

            # Start heartbeat thread
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()

            self.connection_status_changed.emit(True, f"Connected to {server_ip}:{server_port}")
            return True, "Connected successfully"

        except socket.timeout:
            error_msg = f"Connection timeout to {server_ip}:{server_port}"
            self._cleanup_socket()
            self.connection_status_changed.emit(False, error_msg)
            return False, error_msg

        except ConnectionRefusedError:
            error_msg = f"Connection refused by {server_ip}:{server_port} - Server may be offline"
            self._cleanup_socket()
            self.connection_status_changed.emit(False, error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            self._cleanup_socket()
            self.connection_status_changed.emit(False, error_msg)
            return False, str(e)

    def _cleanup_socket(self):
        """Safely cleanup socket resources"""
        with self.lock:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                finally:
                    self.socket = None
            self.connected = False

    def disconnect(self):
        """Disconnect from server and stop heartbeat"""
        print("\n" + "=" * 60)
        print("🔌 HEARTBEAT MANAGER DISCONNECT")
        print("=" * 60)

        # Stop heartbeat thread first
        self.stop_heartbeat.set()
        print("  ✅ Stop signal set")

        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=3)
            if self.heartbeat_thread.is_alive():
                print("  ⚠️ Heartbeat thread still alive after timeout")
            else:
                print("  ✅ Heartbeat thread stopped")

        with self.lock:
            if self.socket:
                print(f"  Socket found: {self.socket}")
                try:
                    # Send proper disconnect message (if socket is still usable)
                    try:
                        disconnect_msg = "DISCONNECT\n"
                        self.socket.send(disconnect_msg.encode('utf-8'))
                        print(f"  📤 Sent disconnect message: {disconnect_msg.strip()}")
                    except (socket.error, BrokenPipeError) as e:
                        print(f"  ⚠️ Could not send disconnect message: {e}")

                    # Give server time to process
                    time.sleep(0.5)

                    # Shutdown and close socket
                    try:
                        self.socket.shutdown(socket.SHUT_RDWR)
                        print("  ✅ shutdown() successful")
                    except (socket.error, OSError) as e:
                        print(f"  ⚠️ shutdown() error (normal if already closed): {e}")

                    self.socket.close()
                    print("  ✅ close() successful")

                except Exception as e:
                    print(f"  ⚠️ Error during disconnect: {e}")
                    try:
                        self.socket.close()
                        print("  ✅ Forced close() successful")
                    except:
                        pass

                self.socket = None
                print("  ✅ Socket reference cleared")

            self.connected = False
            print("  ✅ Connected flag set to False")

        # Clear any pending signals
        try:
            self.connection_status_changed.emit(False, "Disconnected by client")
            print("  ✅ Status signal emitted")
        except:
            pass

        print("=" * 60)
        print("✅ HEARTBEAT MANAGER FULLY DISCONNECTED")
        print("=" * 60 + "\n")

    def _heartbeat_loop(self):
        """Send heartbeat messages periodically"""
        heartbeat_count = 0
        consecutive_failures = 0
        last_heartbeat_time = 0
        receive_buffer = ""

        while not self.stop_heartbeat.is_set() and self.connected:
            current_time = time.time()

            # Check for incoming messages (non-blocking)
            try:
                self.socket.settimeout(0.1)  # Short timeout for checking messages
                data = self.socket.recv(1024)
                if data:
                    receive_buffer += data.decode('utf-8')

                    # Process complete messages (separated by newlines)
                    while '\n' in receive_buffer:
                        message, receive_buffer = receive_buffer.split('\n', 1)
                        message = message.strip()
                        if message:  # Only emit non-empty messages
                            # Emit signal for received message
                            self.message_received.emit(message)
            except socket.timeout:
                # No data available, continue
                pass
            except Exception as e:
                if not self.stop_heartbeat.is_set():
                    print(f"Error receiving data: {e}")
                    consecutive_failures += 1

            # Send heartbeat if enough time has passed
            if current_time - last_heartbeat_time >= self.heartbeat_interval:
                try:
                    # Send heartbeat as a separate message
                    if self._send_message("HEARTBEAT", is_heartbeat=True):
                        self.heartbeat_sent.emit(f"Heartbeat #{heartbeat_count} sent")
                        consecutive_failures = 0
                        last_heartbeat_time = current_time
                        heartbeat_count += 1
                    else:
                        consecutive_failures += 1
                        print(f"Heartbeat send failed ({consecutive_failures} consecutive failures)")

                    # Check if we've had too many failures
                    if consecutive_failures >= 3:
                        print("Too many heartbeat failures, disconnecting...")
                        self.connected = False
                        self.connection_status_changed.emit(False, "Lost connection to server")
                        break

                except Exception as e:
                    if not self.stop_heartbeat.is_set():
                        print(f"Heartbeat loop error: {e}")
                        consecutive_failures += 1

                        if consecutive_failures >= 3:
                            self.connected = False
                            self.connection_status_changed.emit(False, f"Heartbeat failed: {str(e)}")
                            break

            # Short sleep to prevent CPU spinning
            time.sleep(0.05)

    def _send_message(self, message, is_heartbeat=False):
        """Send a message with proper formatting"""
        with self.lock:
            if not self.socket or not self.connected:
                return False

            try:
                # Check if socket is still valid
                try:
                    # This is a non-destructive way to check socket status
                    self.socket.getpeername()
                except socket.error:
                    print("Socket appears to be closed")
                    self.connected = False
                    return False

                # Ensure message ends with newline and send it
                formatted_msg = message if message.endswith("\n") else message + "\n"

                # For heartbeat messages, we can log differently
                if is_heartbeat:
                    # Just send without additional logging
                    self.socket.send(formatted_msg.encode('utf-8'))
                else:
                    # For regular commands, log them
                    print(f"📤 Sending command: {formatted_msg.strip()}")
                    self.socket.send(formatted_msg.encode('utf-8'))

                return True

            except BrokenPipeError:
                print("Broken pipe - connection lost")
                self.connected = False
                return False

            except ConnectionResetError:
                print("Connection reset by peer")
                self.connected = False
                return False

            except socket.error as e:
                print(f"Socket error during send: {e}")
                self.connected = False
                return False

            except Exception as e:
                print(f"Unexpected send error: {e}")
                return False

    def send_data(self, data):
        """Send data to server (for predictions, coordinates, etc.)"""
        # Ensure we're not sending during heartbeat
        with self.lock:
            # Add a small delay to ensure we're not sending right after a heartbeat
            time.sleep(0.05)  # 50ms delay to separate messages
        return self._send_message(data, is_heartbeat=False)

    def is_connected(self):
        """Check if connected"""
        with self.lock:
            if not self.connected or not self.socket:
                return False

            # Additional check to verify connection is still alive
            try:
                self.socket.getpeername()
                return True
            except:
                self.connected = False
                return False


class CameraSignals(QObject):
    """Signals for camera thread communication"""
    finished = Signal(bool, str, object)  # success, message, image_path


class TCPClientSignals(QObject):
    """Signals for TCP client communication"""
    connection_status = Signal(str, bool)  # message, is_connected
    message_received = Signal(str)  # received message
    message_sent = Signal(str)  # sent message


class ClickableImageLabel(QLabel):
    """Custom QLabel that emits click events with pixel coordinates"""
    clicked = Signal(QPoint, float)  # image_point, scale_factor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.scaled_pixmap = None
        self.scale_factor = 1.0
        self.click_points = []  # Store click points for drawing
        self.world_points = []  # Store corresponding world coordinates
        self.show_click_points = True
        self.click_radius = 5

    def setPixmap(self, pixmap):
        """Override setPixmap to store original image"""
        self.original_pixmap = pixmap
        self.update_scaled_pixmap()

    def update_scaled_pixmap(self):
        """Update the scaled pixmap based on current label size"""
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Scale the image to fit the label while maintaining aspect ratio
            self.scaled_pixmap = self.original_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Calculate scale factor
            if self.original_pixmap.width() > 0:
                self.scale_factor = self.scaled_pixmap.width() / self.original_pixmap.width()

            super().setPixmap(self.scaled_pixmap)

    def resizeEvent(self, event):
        """Handle resize events"""
        self.update_scaled_pixmap()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse click events"""
        if event.button() == Qt.LeftButton:
            # Get click position relative to the label
            label_point = event.position().toPoint()

            # Calculate image dimensions and position within label
            if self.scaled_pixmap and not self.scaled_pixmap.isNull():
                # Calculate image position within label (centered)
                img_width = self.scaled_pixmap.width()
                img_height = self.scaled_pixmap.height()
                img_x = (self.width() - img_width) // 2
                img_y = (self.height() - img_height) // 2

                # Check if click is within the image area
                if (img_x <= label_point.x() <= img_x + img_width and
                        img_y <= label_point.y() <= img_y + img_height):

                    # Calculate position relative to the scaled image
                    scaled_x = label_point.x() - img_x
                    scaled_y = label_point.y() - img_y

                    # Calculate original image coordinates
                    if self.scale_factor > 0:
                        original_x = int(scaled_x / self.scale_factor)
                        original_y = int(scaled_y / self.scale_factor)

                        # Emit signal with coordinates
                        self.clicked.emit(
                            QPoint(original_x, original_y),  # Original image coordinates
                            self.scale_factor  # Scale factor
                        )

        super().mousePressEvent(event)

    def paintEvent(self, event):
        """Override paint event to draw click points"""
        super().paintEvent(event)

        if self.show_click_points and self.click_points:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Calculate image position within label (centered)
            if self.scaled_pixmap and not self.scaled_pixmap.isNull():
                img_width = self.scaled_pixmap.width()
                img_height = self.scaled_pixmap.height()
                img_x = (self.width() - img_width) // 2
                img_y = (self.height() - img_height) // 2

                # Draw each click point
                for i, (point, world_point) in enumerate(zip(self.click_points, self.world_points)):
                    scaled_x, scaled_y, original_x, original_y = point

                    # Draw crosshair
                    color = QColor(0, 255, 0) if i < len(self.click_points) - 1 else QColor(255, 0, 0)
                    painter.setPen(QPen(color, 2))
                    # Horizontal line
                    painter.drawLine(
                        int(img_x + scaled_x - self.click_radius),
                        int(img_y + scaled_y),
                        int(img_x + scaled_x + self.click_radius),
                        int(img_y + scaled_y)
                    )
                    # Vertical line
                    painter.drawLine(
                        int(img_x + scaled_x),
                        int(img_y + scaled_y - self.click_radius),
                        int(img_x + scaled_x),
                        int(img_y + scaled_y + self.click_radius)
                    )

                    # Draw point
                    painter.setPen(QPen(QColor(0, 0, 255), 3))
                    painter.drawPoint(int(img_x + scaled_x), int(img_y + scaled_y))

                    # Draw coordinate text with index
                    painter.setPen(QPen(QColor(0, 0, 0), 1))
                    painter.setFont(QFont("Arial", 9, QFont.Bold))
                    coord_text = f"{i + 1}:({original_x},{original_y})"
                    if world_point and world_point[0] is not None:
                        world_x, world_y = world_point
                        coord_text += f"\n({world_x:.1f},{world_y:.1f})"

                    painter.drawText(
                        int(img_x + scaled_x - 40),
                        int(img_y + scaled_y - self.click_radius - 15),
                        coord_text
                    )

    def add_calibration_point(self, scaled_x, scaled_y, original_x, original_y, world_x=None, world_y=None):
        """Add a calibration point with optional world coordinates"""
        self.click_points.append((scaled_x, scaled_y, original_x, original_y))
        self.world_points.append((world_x, world_y) if world_x is not None else (None, None))
        self.update()

    def clear_points(self):
        """Clear all click points"""
        self.click_points.clear()
        self.world_points.clear()
        self.update()


class CalibrationData:
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

    def save_calibration(self, filepath):
        """Save calibration data to JSON file"""
        if not self.is_calibrated:
            return False, "Not calibrated"

        try:
            calibration_data = {
                'calibration_matrix': self.calibration_matrix.tolist(),
                'pixel_points': self.pixel_points,
                'world_points': self.world_points,
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(filepath, 'w') as f:
                json.dump(calibration_data, f, indent=2)

            self.calibration_file = filepath
            return True, f"Calibration saved to {filepath}"

        except Exception as e:
            return False, f"Failed to save calibration: {str(e)}"

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.capture_folder = None  # Will be set by setup_capture_folder
        self.current_image_path = None  # Store current image path
        self.calibration_file = None  # Will be set after folder setup

        self.setWindowTitle("Laser Camera Calibration Tool")
        #self.resize(1100, 850)
        self.showFullScreen()

        # Initialize Heartbeat Manager
        self.heartbeat_manager = HeartbeatManager()
        self.heartbeat_manager.connection_status_changed.connect(self.on_heartbeat_connection_status)
        self.heartbeat_manager.heartbeat_sent.connect(self.on_heartbeat_sent)
        self.heartbeat_manager.message_received.connect(self.on_tcp_message_received)

        # Initialize signals
        self.camera_signals = CameraSignals()
        self.camera_signals.finished.connect(self.on_camera_finished)

        self.tcp_signals = TCPClientSignals()
        self.tcp_signals.connection_status.connect(self.on_tcp_connection_status)
        self.tcp_signals.message_received.connect(self.on_tcp_message_received)
        self.tcp_signals.message_sent.connect(self.on_tcp_message_sent)

        # TCP Connection variables (for legacy compatibility)
        self.tcp_socket = None
        self.is_connected = False
        self.tcp_thread = None
        self.listening_thread = None

        # Calibration variables
        self.calibration = CalibrationData()
        self.calibration_points_needed = 9
        self.current_calibration_point = 0
        self.pending_world_coords = None
        self.stored_coordinates = []  # Store all received coordinates with their point indices
        self.calibration_active = False  # Flag to indicate calibration is in progress

        # Camera capture variables
        self.camera_capturing = False
        self.auto_capture_enabled = True  # Auto capture when receiving coordinates

        # Setup capture folder (no user prompt) - DO THIS FIRST
        self.setup_capture_folder()

        # Set calibration file path
        self.calibration_file = os.path.join(self.capture_folder, "calibration.json")

        # Create main widget and horizontal layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # ---------- LEFT PANEL (Controls) ----------
        left_panel = QWidget()
        left_panel.setMaximumWidth(450)  # Limit width of left panel
        left_panel.setMinimumWidth(350)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(10)

        # At the beginning of left_layout, before adding tcp_group
        title_widget = QWidget()
        title_widget.setStyleSheet("""
                    QWidget {
                        background-color: #2d2d2d;
                        border-radius: 5px;
                    }
                """)
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(10, 5, 10, 5)

        app_title = QLabel("🔬 Laser Camera Calibration Tool")
        app_title.setStyleSheet("""
                    QLabel {
                        color: white;
                        font-size: 18px;
                        font-weight: bold;
                        padding: 8px;
                    }
                """)
        title_layout.addWidget(app_title)
        title_layout.addStretch()

        left_layout.addWidget(title_widget)

        # ---------- Calibration Controls ----------
        self.calibration_group = QGroupBox("Calibration Settings")
        self.calibration_group.setStyleSheet("""
                    QGroupBox {
                        font-weight: bold;
                        border: 2px solid #cccccc;
                        border-radius: 5px;
                        margin-top: 1ex;
                        padding-top: 10px;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                    }
                """)

        self.calibration_progress = QProgressBar()
        self.calibration_progress.setRange(0, self.calibration_points_needed)
        self.calibration_progress.setValue(0)
        self.calibration_progress.setTextVisible(True)
        self.calibration_progress.setFormat("Calibration points: %v/%m")
        self.calibration_progress.setMinimumHeight(25)

        self.calibration_status = QLabel("Not calibrated - 0/9 points")
        self.calibration_status.setStyleSheet("color: #666; font-weight: bold;")
        self.calibration_status.setWordWrap(True)

        calibration_buttons = QHBoxLayout()

        self.save_calibration_btn = QPushButton("💾 Save Calibration")
        self.save_calibration_btn.clicked.connect(self.save_calibration)
        self.save_calibration_btn.setEnabled(False)
        self.save_calibration_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        font-weight: bold;
                        padding: 8px;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                    QPushButton:disabled {
                        background-color: #cccccc;
                    }
                """)

        self.load_calibration_btn = QPushButton("📂 Load Calibration")
        self.load_calibration_btn.clicked.connect(self.load_calibration)
        self.load_calibration_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        font-weight: bold;
                        padding: 8px;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #1976D2;
                    }
                """)

        self.clear_calibration_btn = QPushButton("🗑️ Clear Calibration")
        self.clear_calibration_btn.clicked.connect(self.clear_calibration)
        self.clear_calibration_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        font-weight: bold;
                        padding: 8px;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #d32f2f;
                    }
                """)

        calibration_buttons.addWidget(self.save_calibration_btn)
        calibration_buttons.addWidget(self.load_calibration_btn)
        calibration_buttons.addWidget(self.clear_calibration_btn)

        calibration_layout = QVBoxLayout()
        calibration_layout.addWidget(self.calibration_progress)
        calibration_layout.addWidget(self.calibration_status)
        calibration_layout.addLayout(calibration_buttons)
        self.calibration_group.setLayout(calibration_layout)

        # ---------- Coordinate Display ----------
        self.coord_group = QGroupBox("Coordinates")
        self.coord_group.setStyleSheet("""
                    QGroupBox {
                        font-weight: bold;
                        border: 2px solid #cccccc;
                        border-radius: 5px;
                        margin-top: 1ex;
                        padding-top: 10px;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                    }
                """)

        self.pixel_coord_label = QLabel("Pixel: (?, ?)")
        self.pixel_coord_label.setStyleSheet("color: #2196F3; font-weight: bold;")

        self.world_coord_label = QLabel("World: (?, ?)")
        self.world_coord_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

        self.calibration_point_label = QLabel("Calibration point: 0/9")
        self.calibration_point_label.setStyleSheet("color: #FF9800; font-style: italic;")

        coord_layout = QHBoxLayout()
        coord_layout.addWidget(self.pixel_coord_label)
        coord_layout.addWidget(self.world_coord_label)
        coord_layout.addWidget(self.calibration_point_label)
        coord_layout.addStretch()

        self.coord_group.setLayout(coord_layout)

        # ---------- TCP Connection Settings ----------
        self.tcp_group = QGroupBox("TCP/IP Connection Settings")
        self.tcp_group.setStyleSheet("""
                    QGroupBox {
                        font-weight: bold;
                        border: 2px solid #cccccc;
                        border-radius: 5px;
                        margin-top: 1ex;
                        padding-top: 10px;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                    }
                """)

        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setPlaceholderText("Enter host IP address")
        self.host_edit.setMinimumHeight(30)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8888)
        self.port_spin.setMinimumHeight(30)

        self.heartbeat_interval_spin = QSpinBox()
        self.heartbeat_interval_spin.setRange(1, 60)
        self.heartbeat_interval_spin.setValue(5)
        self.heartbeat_interval_spin.setSuffix(" seconds")

        self.connect_btn = QPushButton("🔌 Connect")
        self.connect_btn.clicked.connect(self.toggle_tcp_connection)
        self.connect_btn.setMinimumHeight(40)
        self.connect_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        font-weight: bold;
                        padding: 8px 15px;
                        border-radius: 4px;
                        font-size: 14px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                """)

        # Connection status label
        self.connection_status_label = QLabel("Status: Disconnected")
        self.connection_status_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
        self.connection_status_label.setWordWrap(True)

        # Heartbeat status label
        self.heartbeat_status_label = QLabel("Heartbeat: Not active")
        self.heartbeat_status_label.setStyleSheet("color: #666; font-size: 11px;")

        # TCP settings layout
        tcp_form = QFormLayout()
        tcp_form.setSpacing(8)
        tcp_form.addRow("Host:", self.host_edit)
        tcp_form.addRow("Port:", self.port_spin)

        tcp_buttons = QHBoxLayout()
        tcp_buttons.addWidget(self.connect_btn)

        tcp_layout = QVBoxLayout()
        tcp_layout.addLayout(tcp_form)
        tcp_layout.addLayout(tcp_buttons)
        tcp_layout.addWidget(self.connection_status_label)
        self.tcp_group.setLayout(tcp_layout)

        # ---------- TCP Messages Display (Scrollable) ----------
        self.tcp_messages_group = QGroupBox("TCP Messages & Calibration Log")
        self.tcp_messages_group.setStyleSheet("""
                    QGroupBox {
                        font-weight: bold;
                        border: 2px solid #cccccc;
                        border-radius: 5px;
                        margin-top: 1ex;
                        padding-top: 10px;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                    }
                """)

        # Create text edit for messages with scrollbars
        self.tcp_messages_display = QTextEdit()
        self.tcp_messages_display.setReadOnly(True)
        self.tcp_messages_display.setLineWrapMode(QTextEdit.WidgetWidth)
        self.tcp_messages_display.setStyleSheet("""
                    QTextEdit {
                        background-color: #f8f9fa;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        font-family: monospace;
                        font-size: 11px;
                        color: #495057;
                        padding: 8px;
                    }
                """)
        self.tcp_messages_display.setMinimumHeight(200)

        # Clear messages button
        self.clear_messages_btn = QPushButton("🗑️ Clear Messages")
        self.clear_messages_btn.clicked.connect(self.clear_tcp_messages)
        self.clear_messages_btn.setMaximumWidth(150)
        self.clear_messages_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #6c757d;
                        color: white;
                        font-weight: bold;
                        padding: 6px;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #5a6268;
                    }
                """)

        tcp_messages_layout = QVBoxLayout()
        tcp_messages_layout.addWidget(self.tcp_messages_display)

        messages_footer = QHBoxLayout()
        messages_footer.addStretch()
        messages_footer.addWidget(self.clear_messages_btn)

        tcp_messages_layout.addLayout(messages_footer)
        self.tcp_messages_group.setLayout(tcp_messages_layout)

        # Add all control groups to left panel
        left_layout.addWidget(self.tcp_group)
        left_layout.addWidget(self.calibration_group)
        left_layout.addWidget(self.coord_group)
        left_layout.addWidget(self.tcp_messages_group, 1)  # Give it stretch factor

        # ---------- RIGHT PANEL (Image Display) ----------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(5)

        # Create a container for image and close button
        image_container = QWidget()
        image_container_layout = QVBoxLayout(image_container)
        image_container_layout.setContentsMargins(0, 0, 0, 0)
        image_container_layout.setSpacing(5)

        # Close button container (top-right corner)
        close_button_container = QWidget()
        close_button_layout = QHBoxLayout(close_button_container)
        close_button_layout.setContentsMargins(0, 0, 0, 0)

        # Add stretch to push button to the right
        close_button_layout.addStretch()

        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(50, 40)
        self.close_btn.clicked.connect(self.close_application)
        self.close_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        font-weight: bold;
                        font-size: 14px;
                        border: none;
                        border-radius: 5px;
                        padding: 8px 15px;
                    }
                    QPushButton:hover {
                        background-color: #d32f2f;
                    }
                    QPushButton:pressed {
                        background-color: #b71c1c;
                    }
                """)
        close_button_layout.addWidget(self.close_btn)

        image_container_layout.addWidget(close_button_container)

        # Image Display Label
        self.image_label = ClickableImageLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText("Waiting for coordinates to capture image...")
        self.image_label.setStyleSheet("""
                    QLabel {
                        border: 2px solid #4CAF50;
                        border-radius: 5px;
                        background-color: #2d2d2d;
                        color: #ffffff;
                        font-size: 16px;
                        min-height: 600px;
                    }
                """)
        self.image_label.setMinimumSize(800, 600)
        self.image_label.clicked.connect(self.on_image_clicked)

        image_container_layout.addWidget(self.image_label, 1)  # Give it stretch factor

        # Image Info Label
        self.image_info_label = QLabel("")
        self.image_info_label.setAlignment(Qt.AlignCenter)
        self.image_info_label.setStyleSheet("""
                    QLabel {
                        color: #666;
                        font-size: 12px;
                        padding: 5px;
                        background-color: #f0f0f0;
                        border-radius: 3px;
                    }
                """)
        self.image_info_label.setMinimumHeight(30)

        image_container_layout.addWidget(self.image_info_label)

        right_layout.addWidget(image_container)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)  # Give right panel stretch factor

        # ---------- Status Bar ----------
        self.status_label = QLabel("Ready - Connect to server to start")
        self.statusBar().addWidget(self.status_label)
        self.statusBar().setStyleSheet("""
                    QStatusBar {
                        background-color: #f0f0f0;
                        color: #333;
                        font-size: 12px;
                        padding: 3px;
                    }
                """)

        # Show capture folder info
        self.update_tcp_messages(f"[System] 📁 Capture folder: {self.capture_folder}")
        self.update_tcp_messages(f"[System] 📁 Calibration file: {self.calibration_file}")

        # Auto-load calibration
        self.auto_load_calibration()

        # Add keyboard shortcut for fullscreen (F11)
        self.shortcut_fullscreen = QPushButton("Toggle Fullscreen (F11)")
        self.shortcut_fullscreen.setVisible(False)  # Hidden button for shortcut reference

    def keyPressEvent(self, event):
        """Handle keyboard events for fullscreen toggle"""
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showMaximized()
            else:
                self.showFullScreen()
        elif event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showMaximized()
        else:
            super().keyPressEvent(event)

    def close_application(self):
        """Close the application with confirmation"""
        reply = QMessageBox.question(
            self,
            "Exit Application",
            "Are you sure you want to exit the application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Clean up connections before closing
            if self.is_connected:
                self.disconnect_tcp()

            # Send C1_CANCEL if calibration is active
            if self.calibration_active and self.is_connected and self.tcp_socket:
                try:
                    self.tcp_socket.sendall("C1_CANCEL".encode('utf-8'))
                    self.tcp_signals.message_sent.emit("C1_CANCEL")
                except:
                    pass

            # Close the application
            self.close()

    def setup_capture_folder(self):
        """Setup capture folder that works on both Windows and Linux (no user prompt)"""

        # Get user's home directory
        home = str(Path.home())

        # Detect operating system
        current_os = platform.system()

        if current_os == "Windows":
            # Windows: Use Pictures folder
            self.capture_folder = os.path.join(home, "Pictures", "LaserCalibration")
        elif current_os == "Linux":
            # Linux: Use Pictures folder
            self.capture_folder = os.path.join(home, "Pictures", "laser_calibration")
        else:
            # Fallback for other OS (Mac, etc.)
            self.capture_folder = os.path.join(home, "Pictures", "laser_calibration")

        # Create the folder if it doesn't exist
        try:
            os.makedirs(self.capture_folder, exist_ok=True)
            print(f"📁 Running on: {current_os}")
            print(f"📁 Images will be saved to: {self.capture_folder}")
        except Exception as e:
            # If Pictures folder is not accessible, use a fallback
            print(f"⚠️ Could not create folder in Pictures: {e}")
            self.capture_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captured_images")
            os.makedirs(self.capture_folder, exist_ok=True)
            print(f"📁 Using fallback folder: {self.capture_folder}")

    def auto_load_calibration(self):
        """Automatically load calibration file if it exists (no user prompt)"""
        if not hasattr(self, 'tcp_messages_display'):
            # UI not ready yet, skip
            return

        if os.path.exists(self.calibration_file):
            success, message = self.calibration.load_calibration(self.calibration_file)
            if success:
                # Update UI
                self.calibration_progress.setValue(len(self.calibration.pixel_points))
                self.calibration_status.setText(
                    f"Auto-loaded calibration - {len(self.calibration.pixel_points)} points")
                self.save_calibration_btn.setEnabled(True)

                # Display points on image
                self.image_label.clear_points()
                for pixel, world in zip(self.calibration.pixel_points, self.calibration.world_points):
                    self.image_label.add_calibration_point(
                        pixel[0] * self.image_label.scale_factor,
                        pixel[1] * self.image_label.scale_factor,
                        pixel[0],
                        pixel[1],
                        world[0] if world else None,
                        world[1] if world else None
                    )

                self.update_tcp_messages(f"[Calibration] 📂 Auto-loaded: {self.calibration_file}")
                print(f"✅ Calibration auto-loaded from: {self.calibration_file}")
            else:
                self.update_tcp_messages(f"[Calibration] ⚠️ Failed to load calibration: {message}")
        else:
            self.update_tcp_messages("[Calibration] ℹ️ No existing calibration file found")

    # ---------- Heartbeat Manager Methods ----------
    def on_heartbeat_connection_status(self, connected, message):
        """Handle heartbeat connection status changes"""
        if connected:
            self.is_connected = True
            self.connect_btn.setText("🔌 Disconnect")
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-weight: bold;
                    padding: 5px 15px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            self.connection_status_label.setText(f"Status: {message}")
            self.heartbeat_status_label.setText("Heartbeat: Active")
            self.heartbeat_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")

            # Send C1_START after successful connection with a small delay
            # to ensure it's sent separately from the heartbeat
            def send_c1_start():
                time.sleep(0.5)  # 500ms delay to ensure heartbeat is established
                if self.heartbeat_manager.is_connected():  # Check if still connected
                    self.heartbeat_manager.send_data("C1_START")
                    # Update UI from main thread using QTimer
                    QTimer.singleShot(0, lambda: self.update_tcp_messages("[System] 🔵 Sent 'C1_START' command"))

            # Start in a separate thread to not block UI
            threading.Thread(target=send_c1_start, daemon=True).start()

            self.update_tcp_messages(f"[System] ✅ Connected with heartbeat: {message}")
        else:
            self.is_connected = False
            self.connect_btn.setText("🔌 Connect")
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                    padding: 5px 15px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
            self.connection_status_label.setText(f"Status: {message}")
            self.heartbeat_status_label.setText("Heartbeat: Inactive")
            self.heartbeat_status_label.setStyleSheet("color: #666; font-size: 11px;")
            self.update_tcp_messages(f"[System] ❌ Heartbeat connection lost: {message}")

    def on_heartbeat_sent(self, message):
        """Handle heartbeat messages sent"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] ❤️ {message}")

    # ---------- Camera Capture Methods ----------
    def capture_from_camera(self):
        """Start camera capture in a separate thread"""
        if self.camera_capturing:
            return

        self.camera_capturing = True
        self.status_label.setText("Capturing image...")
        self.image_label.setText("Capturing image...\nPlease wait")
        self.image_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                border-radius: 5px;
                background-color: #f5f5f5;
                min-height: 400px;
                font-size: 16px;
                color: #666;
            }
        """)
        self.image_info_label.setText("")

        def run_capture():
            def callback(success, message, image_path):
                if success and image_path:
                    # Move/rename captured image to chosen folder
                    base_name = os.path.basename(image_path)
                    save_path = os.path.join(self.capture_folder, base_name)

                    # Ensure unique filename
                    count = 1
                    name, ext = os.path.splitext(base_name)
                    while os.path.exists(save_path):
                        save_path = os.path.join(self.capture_folder, f"{name}_{count}{ext}")
                        count += 1

                    try:
                        os.rename(image_path, save_path)
                        image_path = save_path
                    except:
                        # If rename fails, copy the file
                        import shutil
                        shutil.copy2(image_path, save_path)
                        image_path = save_path

                # Emit signal to update GUI
                self.camera_signals.finished.emit(success, message, image_path)
                self.camera_capturing = False

            # Call the camera capture function
            if CAMERA_AVAILABLE:
                AutoCaptureFlow(callback=callback)
            else:
                self.camera_signals.finished.emit(False, "Camera module not available", None)
                self.camera_capturing = False

        thread = threading.Thread(target=run_capture, daemon=True)
        thread.start()

    def display_image(self, image_path):
        """Display the captured image in the GUI"""
        self.current_image_path = image_path

        if not os.path.exists(image_path):
            self.image_label.setText("Error: Image file not found")
            self.image_label.setStyleSheet("""
                QLabel {
                    border: 2px dashed #f00;
                    border-radius: 5px;
                    background-color: #ffe6e6;
                    min-height: 400px;
                    font-size: 16px;
                    color: #c00;
                }
            """)
            self.image_info_label.setText("")
            return

        # Load and display the image
        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            self.image_label.setText("Error: Cannot load image")
            self.image_label.setStyleSheet("""
                QLabel {
                    border: 2px dashed #f00;
                    border-radius: 5px;
                    background-color: #ffe6e6;
                    min-height: 400px;
                    font-size: 16px;
                    color: #c00;
                }
            """)
            self.image_info_label.setText("")
            return

        # Set the pixmap on our custom label
        self.image_label.setPixmap(pixmap)
        self.image_label.setStyleSheet("""
            QLabel {
                border: 2px solid #4CAF50;
                border-radius: 5px;
                background-color: #f0f0f0;
                min-height: 400px;
            }
        """)

        # Update image info
        file_size = os.path.getsize(image_path) / 1024  # Convert to KB
        dimensions = f"{pixmap.width()} x {pixmap.height()}"

        if self.calibration.is_calibrated:
            info_text = f"{os.path.basename(image_path)} | {dimensions} | Calibrated | Click to convert pixel→world"
        else:
            info_text = f"{os.path.basename(image_path)} | {dimensions} | Not calibrated | Click points to calibrate"

        self.image_info_label.setText(info_text)

        # Log image load
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] 📸 Captured image: {os.path.basename(image_path)}")

    def on_camera_finished(self, success, message, image_path):
        """Handle camera capture completion"""
        if success and image_path:
            # Display the captured image
            self.display_image(image_path)
            self.status_label.setText(f"Image saved: {os.path.basename(image_path)}")

            # Log success
            timestamp = time.strftime("%H:%M:%S")
            self.update_tcp_messages(f"[{timestamp}] ✅ Image captured successfully")
        else:
            # Show error state
            self.image_label.setText("Capture Failed")
            self.image_label.setStyleSheet("""
                QLabel {
                    border: 2px dashed #f00;
                    border-radius: 5px;
                    background-color: #ffe6e6;
                    min-height: 400px;
                    font-size: 16px;
                    color: #c00;
                }
            """)
            self.image_info_label.setText("")
            self.status_label.setText("Capture failed")

            # Log error
            timestamp = time.strftime("%H:%M:%S")
            self.update_tcp_messages(f"[{timestamp}] ❌ Capture failed: {message}")

    # ---------- Calibration Methods ----------
    def start_calibration(self):
        """Start calibration process automatically"""
        self.calibration_active = True
        self.calibration_status.setText("Calibration in progress - Click 9 points")
        self.update_tcp_messages("[Calibration] 🎯 Calibration started - Click 9 points on the image")

        # Check if we already have stored coordinates for point 1
        next_point = self.current_calibration_point + 1
        coordinate_found = False

        for stored in self.stored_coordinates:
            if stored['index'] == next_point:
                self.pending_world_coords = stored['coords']
                self.update_tcp_messages(
                    f"[Calibration] 📦 Using stored coordinate for point {next_point}: "
                    f"({stored['coords'][0]}, {stored['coords'][1]}) - Click on image to bind")
                coordinate_found = True
                break

        # If no stored coordinate found, send C1_START
        if not coordinate_found:
            try:
                self.heartbeat_manager.send_data("C1_START")
                self.tcp_signals.message_sent.emit("C1_START")
                self.update_tcp_messages("[Calibration] 🔵 Sent 'C1_START' - Waiting for world coordinate...")
            except Exception as e:
                self.update_tcp_messages(f"Error sending C1_START: {str(e)}")

    def add_calibration_point(self, pixel_point, world_point):
        """Add a calibration point pair"""
        # Convert QPoint to tuple
        pixel_tuple = (pixel_point.x(), pixel_point.y())
        world_tuple = world_point

        # Add to calibration data
        self.calibration.add_point_pair(pixel_tuple, world_tuple)

        # Update progress
        self.current_calibration_point += 1
        self.calibration_progress.setValue(self.current_calibration_point)
        self.calibration_point_label.setText(f"Calibration point: {self.current_calibration_point}/9")

        # Update status
        if self.current_calibration_point >= self.calibration_points_needed:
            self.calibration_status.setText("Calibration complete - Performing calibration...")
            self.perform_calibration_calculation()
        else:
            self.calibration_status.setText(f"Calibration - {self.current_calibration_point}/9 points")

        # Add point to image display
        self.image_label.add_calibration_point(
            pixel_point.x() * self.image_label.scale_factor,
            pixel_point.y() * self.image_label.scale_factor,
            pixel_point.x(),
            pixel_point.y(),
            world_tuple[0],
            world_tuple[1]
        )

        return self.current_calibration_point

    def perform_calibration_calculation(self):
        """Perform the actual calibration calculation"""
        success, message = self.calibration.perform_calibration()

        if success:
            self.calibration_status.setText("Calibration successful! Save calibration file.")
            self.save_calibration_btn.setEnabled(True)
            self.calibration_active = False

            # Test calibration with first point
            test_pixel = self.calibration.pixel_points[0]
            test_world = self.calibration.pixel_to_world(test_pixel)

            self.update_tcp_messages(f"[Calibration] ✅ Calibration successful!")
            self.update_tcp_messages(f"[Calibration] Test: Pixel {test_pixel} → World {test_world}")

            # Auto-save calibration
            self.save_calibration()

            QMessageBox.information(self, "Calibration Successful",
                                    f"Calibration completed and auto-saved successfully!\n\n"
                                    f"Test: Pixel {test_pixel} → World {test_world}")
        else:
            self.calibration_status.setText(f"Calibration failed: {message}")
            self.calibration_active = False

            self.update_tcp_messages(f"[Calibration] ❌ Calibration failed: {message}")
            QMessageBox.warning(self, "Calibration Failed", message)

    def save_calibration(self):
        """Save calibration to fixed file (no user prompt)"""
        if not self.calibration.is_calibrated:
            QMessageBox.warning(self, "Not Calibrated", "Please perform calibration first")
            return

        # Save to fixed location - NO DIALOG
        success, message = self.calibration.save_calibration(self.calibration_file)

        if success:
            self.update_tcp_messages(f"[Calibration] 💾 Auto-saved to: {self.calibration_file}")
            # Optional: Show brief success message
            QMessageBox.information(self, "Calibration Saved",
                                    f"Calibration saved to:\n{self.calibration_file}")
            print(f"✅ Calibration saved to: {self.calibration_file}")
        else:
            QMessageBox.warning(self, "Save Failed", message)

    def load_calibration(self):
        """Load calibration from fixed file (no user prompt)"""
        if not os.path.exists(self.calibration_file):
            QMessageBox.warning(self, "File Not Found",
                                f"No calibration file found at:\n{self.calibration_file}")
            return

        success, message = self.calibration.load_calibration(self.calibration_file)

        if success:
            # Update UI
            self.calibration_progress.setValue(len(self.calibration.pixel_points))
            self.calibration_status.setText(f"Loaded calibration - {len(self.calibration.pixel_points)} points")
            self.save_calibration_btn.setEnabled(True)

            # Clear and re-add points to image
            self.image_label.clear_points()
            for pixel, world in zip(self.calibration.pixel_points, self.calibration.world_points):
                self.image_label.add_calibration_point(
                    pixel[0] * self.image_label.scale_factor,
                    pixel[1] * self.image_label.scale_factor,
                    pixel[0],
                    pixel[1],
                    world[0] if world else None,
                    world[1] if world else None
                )

            self.update_tcp_messages(f"[Calibration] 📂 Loaded: {self.calibration_file}")
            QMessageBox.information(self, "Calibration Loaded",
                                    f"Calibration loaded from:\n{self.calibration_file}")
            print(f"✅ Calibration loaded from: {self.calibration_file}")
        else:
            QMessageBox.warning(self, "Load Failed", message)

    def clear_calibration(self):
        """Clear all calibration data and optionally delete the file"""
        reply = QMessageBox.question(
            self, "Clear Calibration",
            "Are you sure you want to clear all calibration data?\n"
            "This will also delete the saved calibration file.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Delete the calibration file if it exists
            if os.path.exists(self.calibration_file):
                try:
                    os.remove(self.calibration_file)
                    self.update_tcp_messages(f"[Calibration] 🗑️ Deleted: {self.calibration_file}")
                except Exception as e:
                    self.update_tcp_messages(f"[Calibration] ⚠️ Failed to delete file: {e}")

            # Send C1_CANCEL to server to abort calibration
            if self.is_connected and self.heartbeat_manager.is_connected():
                try:
                    self.heartbeat_manager.send_data("C1_CANCEL")
                    self.tcp_signals.message_sent.emit("C1_CANCEL")
                    self.update_tcp_messages("[Calibration] 🛑 Sent 'C1_CANCEL' to abort calibration on server")
                except Exception as e:
                    self.update_tcp_messages(f"Error sending C1_CANCEL: {str(e)}")

            # Reset calibration data
            self.calibration = CalibrationData()
            self.image_label.clear_points()
            self.calibration_progress.setValue(0)
            self.calibration_status.setText("Not calibrated - 0/9 points")
            self.calibration_point_label.setText("Calibration point: 0/9")
            self.save_calibration_btn.setEnabled(False)
            self.current_calibration_point = 0
            self.pending_world_coords = None
            self.stored_coordinates = []
            self.calibration_active = False

            self.update_tcp_messages("[Calibration] 🧹 Cleared all calibration data")

    # ---------- Pixel Coordinate Methods ----------
    def on_image_clicked(self, pixel_point, scale_factor):
        """Handle image click events"""
        # Update pixel coordinates display
        self.pixel_coord_label.setText(f"Pixel: ({pixel_point.x()}, {pixel_point.y()})")

        # If calibrated, convert to world coordinates
        if self.calibration.is_calibrated:
            world_point = self.calibration.pixel_to_world((pixel_point.x(), pixel_point.y()))
            if world_point:
                self.world_coord_label.setText(f"World: ({world_point[0]:.2f}, {world_point[1]:.2f})")
                self.update_tcp_messages(
                    f"📍 Pixel ({pixel_point.x()}, {pixel_point.y()}) → World ({world_point[0]:.2f}, {world_point[1]:.2f})")
            else:
                self.world_coord_label.setText("World: Conversion failed")
        else:
            # If calibration is active and we have pending world coordinates
            if self.calibration_active and self.pending_world_coords is not None:
                # Use the pending world coordinates
                world_coords = self.pending_world_coords
                self.pending_world_coords = None

                # Add calibration point
                point_num = self.add_calibration_point(pixel_point, world_coords)
                self.update_tcp_messages(
                    f"[Calibration] Point {point_num}: Pixel ({pixel_point.x()}, {pixel_point.y()}) ↔ World ({world_coords[0]}, {world_coords[1]})")

                # Send C1_NEXT for next point if calibration not complete
                if point_num < self.calibration_points_needed:
                    # Check if we already have the next point stored
                    next_point = point_num + 1
                    next_coord_found = False

                    for stored in self.stored_coordinates:
                        if stored['index'] == next_point:
                            self.pending_world_coords = stored['coords']
                            self.update_tcp_messages(
                                f"[Calibration] 📦 Using stored coordinate for point {next_point}: "
                                f"({stored['coords'][0]}, {stored['coords'][1]}) - Click on image to bind")
                            next_coord_found = True
                            break

                    # If no stored coordinate found, send C1_NEXT
                    if not next_coord_found:
                        try:
                            self.heartbeat_manager.send_data("C1_NEXT")
                            self.tcp_signals.message_sent.emit("C1_NEXT")
                            self.update_tcp_messages(
                                f"[Calibration] 🔵 Sent 'C1_NEXT', waiting for next world coordinate...")
                        except Exception as e:
                            self.update_tcp_messages(f"Error sending C1_NEXT: {str(e)}")
                else:
                    self.update_tcp_messages("[Calibration] ✅ All 9 points collected - Performing calibration...")

            # If calibration is active but no pending coordinates
            elif self.calibration_active:
                self.update_tcp_messages(
                    f"[Calibration] Clicked at ({pixel_point.x()}, {pixel_point.y()}) but no world coordinate available")
                self.update_tcp_messages(f"[Calibration] Waiting for server to send coordinates...")
            else:
                self.world_coord_label.setText("World: Not calibrated")
                self.update_tcp_messages(f"📍 Pixel click: ({pixel_point.x()}, {pixel_point.y()})")

        self.status_label.setText(f"Clicked at pixel: ({pixel_point.x()}, {pixel_point.y()})")

    # ---------- TCP Message Processing ----------
    def process_world_coordinates(self, message):
        """Parse world coordinates from TCP message"""
        try:
            # Parse C_POINT_X_Y format
            if message.startswith('C1_POINT_'):
                parts = message.split('_')
                if len(parts) >= 5:  # C, POINT, index, X, Y
                    point_index = int(parts[2])  # Get the point number (1, 2, 3...)
                    world_x = float(parts[-2])  # Second last is X
                    world_y = float(parts[-1])  # Last is Y

                    self.update_tcp_messages(
                        f"📥 World coordinates received: ({world_x}, {world_y}) for point {point_index}")
                    return (world_x, world_y, point_index)

            # Fallback: Try to parse as "x,y" format
            elif ',' in message:
                parts = message.split(',')
                if len(parts) >= 2:
                    world_x = float(parts[0].strip())
                    world_y = float(parts[1].strip())
                    self.update_tcp_messages(f"📥 World coordinates received: ({world_x}, {world_y})")
                    return (world_x, world_y, None)

            # Fallback: Try to parse as JSON
            try:
                data = json.loads(message)
                if 'x' in data and 'y' in data:
                    world_x = float(data['x'])
                    world_y = float(data['y'])
                    self.update_tcp_messages(f"📥 World coordinates received: ({world_x}, {world_y})")
                    return (world_x, world_y, None)
            except:
                pass

            return None

        except Exception as e:
            self.update_tcp_messages(f"Error parsing world coordinates: {str(e)}")
            return None

    # ---------- TCP/IP Connection Methods ----------
    def on_tcp_message_received(self, message):
        """Handle received TCP messages"""
        timestamp = time.strftime("%H:%M:%S")

        # Check if this is a coordinate message
        result = self.process_world_coordinates(message)

        if result:
            if len(result) == 3:  # C_POINT format with index
                world_x, world_y, point_index = result
                world_coords = (world_x, world_y)

                # Store ALL coordinates with their point numbers
                self.stored_coordinates.append({
                    'index': point_index,
                    'coords': world_coords,
                    'timestamp': timestamp
                })

                # Sort stored coordinates by index
                self.stored_coordinates.sort(key=lambda x: x['index'])

                # AUTO CAPTURE CAMERA when coordinate is received
                if self.auto_capture_enabled and not self.camera_capturing and CAMERA_AVAILABLE:
                    self.capture_from_camera()

                # If calibration is active, use as pending if it's the next expected point
                if self.calibration_active:
                    next_expected_point = self.current_calibration_point + 1
                    if point_index == next_expected_point:
                        self.pending_world_coords = world_coords
                        self.update_tcp_messages(
                            f"[Calibration] 📦 Stored world coordinates ({world_coords[0]}, {world_coords[1]}) for point {point_index} - Click on image to bind")
                    else:
                        self.update_tcp_messages(
                            f"[Calibration] 📦 Received point {point_index} ({world_coords[0]}, {world_coords[1]}) - Waiting for point {next_expected_point}")
                else:
                    # Not in calibration mode, just display and automatically start calibration on first point
                    self.update_tcp_messages(
                        f"[{timestamp}] 📥 Received point {point_index}: ({world_coords[0]}, {world_coords[1]})")

                    # Automatically start calibration on first received point
                    if point_index == 1 and not self.calibration_active and not self.calibration.is_calibrated:
                        self.start_calibration()
            else:
                # Old format without index
                world_x, world_y, _ = result
                world_coords = (world_x, world_y)
                self.update_tcp_messages(
                    f"[{timestamp}] 📥 Received coordinates: ({world_coords[0]}, {world_coords[1]})")
        else:
            # Regular message
            self.update_tcp_messages(f"[{timestamp}] 📥 Received: {message}")

    def on_tcp_message_sent(self, message):
        """Handle sent TCP messages"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] 📤 Sent: {message}")

    def update_tcp_messages(self, message):
        """Update TCP messages display with scrollable text"""
        # Check if tcp_messages_display exists
        if not hasattr(self, 'tcp_messages_display'):
            return

        # Get current text
        current_text = self.tcp_messages_display.toPlainText()

        # Add new message
        if current_text:
            new_text = f"{message}\n{current_text}"
        else:
            new_text = message

        # Update the text edit
        self.tcp_messages_display.setPlainText(new_text)

        # Keep cursor at the beginning to show newest messages
        cursor = self.tcp_messages_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.tcp_messages_display.setTextCursor(cursor)

    def clear_tcp_messages(self):
        """Clear all TCP messages"""
        if hasattr(self, 'tcp_messages_display'):
            self.tcp_messages_display.clear()
        self.status_label.setText("Messages cleared")

    # ---------- TCP Connection Methods ----------
    def toggle_tcp_connection(self):
        """Toggle TCP connection on/off"""
        if self.is_connected:
            self.disconnect_tcp()
        else:
            self.connect_tcp()

    def connect_tcp(self):
        """Establish TCP connection using HeartbeatManager"""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        interval = self.heartbeat_interval_spin.value()

        if not host:
            QMessageBox.warning(self, "Invalid Input", "Please enter a host address")
            return

        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting...")
        self.connection_status_label.setText(f"Status: Connecting to {host}:{port}...")

        # Use heartbeat manager to connect
        success, message = self.heartbeat_manager.connect(host, port, interval)

        if not success:
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("🔌 Connect")
            self.connection_status_label.setText(f"Status: {message}")

    def disconnect_tcp(self):
        """Close TCP connection using HeartbeatManager"""
        self.heartbeat_manager.disconnect()
        self.is_connected = False
        self.stored_coordinates = []
        self.pending_world_coords = None
        self.calibration_active = False

    def on_tcp_connection_status(self, message, is_connected):
        """Handle TCP connection status changes (legacy, now using heartbeat)"""
        # This is kept for compatibility but not actively used
        pass

    def _update_connection_status(self, message, is_connected):
        """Legacy method - not used with heartbeat"""
        pass

    def closeEvent(self, event):
        """Clean up connections when closing the application"""
        if hasattr(self, 'heartbeat_manager'):
            self.heartbeat_manager.disconnect()
        event.accept()


# For standalone testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())