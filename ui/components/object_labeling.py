import os
import random
import threading
import socket
import time
import json
from PIL import Image
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QWidget,
    QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QInputDialog,
    QMessageBox, QProgressDialog, QLabel,
    QLineEdit, QSpinBox, QStackedWidget,
    QGroupBox, QScrollArea, QTextEdit, QCheckBox, QProgressBar
)
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QPixmap, QTextCursor
from PySide6.QtCore import Signal, QObject, QTimer, Qt, QRectF, QPointF
from ui.components.annotator2 import AnnotationWidget

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

class TCPClientSignals(QObject):
    """Signals for TCP client communication"""
    connection_status = Signal(str, bool)  # message, is_connected
    message_received = Signal(str)  # received message
    message_sent = Signal(str)  # sent message


class MainWindow(QMainWindow):
    def __init__(self):
        self.capture_folder = None
        super().__init__()
        self.setWindowTitle("BMP Annotation Tool with Camera, Training & Label ID Scan")
        self.resize(1400, 900)

        # Define base paths
        self.base_path = "C:\\Users\\PC_AI_DS\\Desktop\\New folder"
        self.capture_image_path = f"{self.base_path}\\Capture Image"
        self.image_boxes = {}

        # Start with 0 as the first label
        self.labels = ["0"]
        self.label_counter = 0
        self.label_colors = {"0": QColor(255, 0, 0)}

        self.image_files = []
        self.current_index = -1

        # TCP related attributes
        self.tcp_socket = None
        self.tcp_connected = False
        self.tcp_thread = None
        self.listening_thread = None
        self.listening_active = False
        self.scan_data_received = ""
        self.last_bounding_box = None  # Store the last drawn bounding box
        self.last_box_label = None  # Store the label of the last box
        self.tcp_received_text = ""  # Store the latest TCP received text
        self.selected_class_for_prediction = None  # Add this line

        # Create necessary folders if they don't exist
        self.create_required_folders()

        # Initialize signals
        self.camera_signals = CameraSignals()
        self.camera_signals.finished.connect(self.on_camera_finished)

        # TCP signals
        self.tcp_signals = TCPClientSignals()
        self.tcp_signals.connection_status.connect(self.on_tcp_connection_status)
        self.tcp_signals.message_received.connect(self.on_tcp_message_received)
        self.tcp_signals.message_sent.connect(self.on_tcp_message_sent)

        # Add a timer to track bounding box changes
        self.box_tracker_timer = QTimer()
        self.box_tracker_timer.timeout.connect(self.track_bounding_box_changes)
        self.box_tracker_timer.start(300)  # Check every 300ms

        # Add a timer to periodically check and fix selection
        self.selection_check_timer = QTimer()
        self.selection_check_timer.timeout.connect(self.check_and_fix_selection)
        self.selection_check_timer.start(500)  # Check every 500ms

        # Track previous box count
        self.previous_box_count = 0

        self.init_ui()

    def init_ui(self):
        """Initialize the main annotation page with TCP functionality"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

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

        # Auto TCP Scan button
        self.labeling_btn = QPushButton("Image Labeling")
        self.labeling_btn.clicked.connect(self.auto_tcp_scan)
        self.labeling_btn.setStyleSheet("background-color: #795548; color: white; font-weight: bold;")
        self.labeling_btn.setToolTip("Auto connect TCP and send bounding box coordinates")

        # --- ADD CALIBRATION BUTTONS HERE, WITH THE OTHER BUTTONS ---
        top_bar.addWidget(self.capture_btn)
        top_bar.addWidget(undo_btn)
        top_bar.addWidget(delete_btn)
        top_bar.addWidget(self.labeling_btn)
        top_bar.addStretch()

        # ---------- Main Content Area ----------
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # ---------- Left Column: Annotation Viewer (70%) ----------
        left_column = QVBoxLayout()

        # FIX: Create AnnotationWidget FIRST before connecting signals
        self.viewer = AnnotationWidget(
            self.get_current_label,
            self.get_label_color
        )

        # FIX: Connect signals AFTER creating the viewer
        self.viewer.status_message.connect(self.on_annotation_status)

        left_column.addWidget(self.viewer, 1)

        # Image info label
        self.image_info_label = QLabel("No image loaded")
        self.image_info_label.setStyleSheet("color: #666; font-size: 12px; padding: 2px;")
        left_column.addWidget(self.image_info_label)

        content_layout.addLayout(left_column, 70)

        # ---------- Right Column: TCP Controls & Messages (30%) ----------
        right_column = QVBoxLayout()
        right_column.setSpacing(10)

        # TCP Connection Settings Group
        tcp_group = QGroupBox("TCP/IP Connection Settings")
        tcp_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #795548;
                border-radius: 5px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #795548;
            }
        """)

        tcp_layout = QVBoxLayout()

        # Host and Port inputs
        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("Host:"))
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setPlaceholderText("Server IP")
        form_layout.addWidget(self.host_edit)

        form_layout.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8888)
        form_layout.addWidget(self.port_spin)

        tcp_layout.addLayout(form_layout)

        # Connection status
        self.connection_status_label = QLabel("Status: Disconnected")
        self.connection_status_label.setStyleSheet("color: #666; font-style: italic; padding: 5px 0;")
        tcp_layout.addWidget(self.connection_status_label)

        tcp_group.setLayout(tcp_layout)
        right_column.addWidget(tcp_group)

        # Instructions Group
        instructions_group = QGroupBox("Auto TCP Scan Instructions")
        instructions_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #2196F3;
                border-radius: 5px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #2196F3;
            }
        """)

        instructions_layout = QVBoxLayout()

        instructions = QLabel(
            "📋 Auto TCP Scan Process:\n\n"
            "1. Draw bounding box on object\n"
            "2. Click 'Auto TCP Scan' button\n"
            "3. Auto connect to TCP server\n"
            "4. Send bounding box coordinates\n"
            "5. Auto crop image on response\n\n"
            "Note: Requires at least one bounding box"
        )
        instructions.setStyleSheet("font-size: 12px; color: #555; padding: 8px;")
        instructions.setWordWrap(True)
        instructions_layout.addWidget(instructions)

        instructions_group.setLayout(instructions_layout)
        right_column.addWidget(instructions_group)

        # TCP Messages Group
        data_group = QGroupBox("TCP Messages")
        data_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #9C27B0;
                border-radius: 5px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #9C27B0;
            }
        """)

        data_layout = QVBoxLayout()

        # Create scrollable text area for messages
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(150)
        scroll_area.setMaximumHeight(250)

        self.tcp_messages_display = QTextEdit()
        self.tcp_messages_display.setReadOnly(True)
        self.tcp_messages_display.setLineWrapMode(QTextEdit.NoWrap)
        self.tcp_messages_display.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: none;
                font-family: monospace;
                font-size: 11px;
                color: #495057;
                padding: 5px;
            }
        """)

        scroll_area.setWidget(self.tcp_messages_display)
        data_layout.addWidget(scroll_area)

        # Clear messages button
        clear_messages_btn = QPushButton("🗑️ Clear Messages")
        clear_messages_btn.clicked.connect(self.clear_tcp_messages)
        clear_messages_btn.setMaximumWidth(120)
        data_layout.addWidget(clear_messages_btn, 0, Qt.AlignRight)

        data_group.setLayout(data_layout)
        right_column.addWidget(data_group)

        content_layout.addLayout(right_column, 30)

        layout.addLayout(top_bar)
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
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self.auto_tcp_scan)

    def on_annotation_status(self, message):
        """Handle status messages from annotation widget"""
        self.status_label.setText(message)
        # Remove the OBB condition entirely or keep only TCP messages if needed
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] {message}")

    def create_required_folders(self):
        """Create all required folders if they don't exist"""
        folders_to_create = [
            self.capture_image_path,
        ]

        for folder in folders_to_create:
            try:
                os.makedirs(folder, exist_ok=True)
                print(f"Created/Verified folder: {folder}")
            except Exception as e:
                print(f"Error creating folder {folder}: {e}")

    def track_bounding_box_changes(self):
        """Track when new bounding boxes are drawn"""
        if not hasattr(self.viewer, 'boxes'):
            return

        try:
            # Count ONLY regular boxes (remove rotated_count)
            regular_count = len(self.viewer.boxes) if hasattr(self.viewer, 'boxes') else 0
            current_count = regular_count  # Remove rotated_count

            # If more than one box total
            if current_count > 1:
                # Use the safe clear method
                self.viewer.safe_clear_boxes()

                # Reset tracking variables
                self.last_bounding_box = None
                self.last_box_label = None
                self.previous_box_count = 0

                # Show error message
                QTimer.singleShot(100, lambda: QMessageBox.critical(
                    self,
                    "Error",
                    "Only ONE bounding box allowed!\n\nAll boxes have been cleared."
                ))

                self.status_label.setText("Error: Only one box allowed. Boxes cleared.")

            else:
                # Update previous count
                self.previous_box_count = current_count

                # Store the latest box if it exists
                if current_count == 1:
                    latest_box, latest_label = self.viewer.boxes[0]
                    self.last_bounding_box = (latest_box, latest_label)
                    self.last_box_label = latest_label

        except Exception as e:
            print(f"Error in track_bounding_box_changes: {e}")
            self.viewer.safe_clear_boxes()

    def auto_tcp_scan(self):
        """Auto connect TCP and perform Scan_ID"""
        # Check if bounding box exists
        if not hasattr(self.viewer, 'boxes') or not self.viewer.boxes:
            QMessageBox.warning(self, "No Bounding Box",
                                "Please draw at least one bounding box first!")
            return

        # Check if image is loaded
        if not hasattr(self, 'image_path') or not self.image_path:
            QMessageBox.warning(self, "No Image",
                                "Please load an image first!")
            return

        # Auto connect to TCP if not connected
        if not self.tcp_connected:
            self.status_label.setText("Auto connecting to TCP...")
            self.connect_tcp()

            # Wait a bit for connection
            QTimer.singleShot(1000, self.perform_scan_id_after_connect)
        else:
            # Already connected, perform scan immediately
            self.perform_scan_id()

    def perform_scan_id_after_connect(self):
        """Perform Scan_ID after TCP connection is established"""
        if self.tcp_connected:
            self.perform_scan_id()
        else:
            QMessageBox.warning(self, "Connection Failed",
                                "Failed to connect to TCP server. Please check settings.")

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
            message = "OK"

            self.tcp_socket.sendall(message.encode('utf-8'))
            self.tcp_signals.message_sent.emit(message)

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

    # ---------- TCP/IP Methods ----------
    def connect_tcp(self):
        """Establish TCP connection"""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()

        if not host:
            QMessageBox.warning(self, "Invalid Input", "Please enter a host address")
            return

        # Close existing connection if any
        self.disconnect_tcp()

        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(2)

            self.labeling_btn.setEnabled(False)
            self.labeling_btn.setText("Connecting...")
            self.connection_status_label.setText(f"Status: Connecting to {host}:{port}...")

            def connect_thread():
                try:
                    self.tcp_socket.connect((host, port))
                    self.tcp_connected = True
                    self.tcp_signals.connection_status.emit(f"Connected to {host}:{port}", True)
                    self.start_listening()
                except socket.error as e:
                    self.tcp_signals.connection_status.emit(f"Connection failed: {str(e)}", False)
                    self.tcp_socket = None
                finally:
                    # Re-enable button in main thread
                    QTimer.singleShot(0, lambda: self.labeling_btn.setEnabled(True))

            self.tcp_thread = threading.Thread(target=connect_thread, daemon=True)
            self.tcp_thread.start()

        except Exception as e:
            self.on_tcp_connection_status(f"Connection error: {str(e)}", False)
            self.labeling_btn.setEnabled(True)

    def disconnect_tcp(self):
        """Close TCP connection"""
        self.listening_active = False
        self.tcp_connected = False

        if self.tcp_socket:
            try:
                self.tcp_socket.shutdown(socket.SHUT_RDWR)
                self.tcp_socket.close()
            except:
                pass
            finally:
                self.tcp_socket = None

        self.labeling_btn.setText("Image Labeling")
        self.labeling_btn.setStyleSheet("background-color: #795548; color: white; font-weight: bold;")
        self.labeling_btn.setEnabled(True)
        self.connection_status_label.setText("Status: Disconnected")
        self.update_tcp_messages("[System] Disconnected from server")

    def start_listening(self):
        """Start listening for incoming messages"""
        self.listening_active = True

        def listen_thread():
            while self.tcp_connected and self.tcp_socket and self.listening_active:
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

    # ---------- TCP Signal Handlers ----------
    def on_tcp_connection_status(self, message, is_connected):
        """Handle TCP connection status changes"""
        self.tcp_connected = is_connected
        self.labeling_btn.setEnabled(True)

        if is_connected:
            self.labeling_btn.setText("ID Scan")
            self.labeling_btn.setStyleSheet("background-color: #795548; color: white; font-weight: bold;")
            self.connection_status_label.setText(
                f"Status: Connected to {self.host_edit.text()}:{self.port_spin.value()}")
            self.update_tcp_messages("[System] Connected to server")
        else:
            self.labeling_btn.setText("Image Labeling")
            self.labeling_btn.setStyleSheet("background-color: #795548; color: white; font-weight: bold;")
            self.connection_status_label.setText(f"Status: {message}")
            self.update_tcp_messages(f"[System] {message}")

    def on_tcp_message_received(self, message):
        """Handle received TCP messages"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] 📥 Received: {message}")
        self.status_label.setText(f"TCP: {message[:50]}..." if len(message) > 50 else f"TCP: {message}")

        # Store received data
        self.scan_data_received = message
        self.tcp_received_text = message.strip()  # Store the received text for filename

        # Automatically crop and save image when TCP receives text
        self.auto_crop_and_save_on_tcp_message(message)

    def on_tcp_message_sent(self, message):
        """Handle sent TCP messages"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_tcp_messages(f"[{timestamp}] 📤 Sent: {message}")

    def update_tcp_messages(self, message):
        """Update TCP messages display"""
        current_text = self.tcp_messages_display.toPlainText()

        # Add new message at the beginning (newest first)
        if current_text:
            new_text = f"{message}\n{current_text}"
        else:
            new_text = message

        # Update the text edit
        self.tcp_messages_display.setPlainText(new_text)

        # Keep cursor at the beginning to show newest messages
        cursor = self.tcp_messages_display.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.tcp_messages_display.setTextCursor(cursor)

    def clear_tcp_messages(self):
        """Clear all TCP messages"""
        self.tcp_messages_display.clear()
        self.status_label.setText("Messages cleared")

    def auto_crop_and_save_on_tcp_message(self, tcp_message):
        """Automatically crop and save image when TCP receives message"""
        # Check if we have the necessary components
        if not self.is_ready_for_auto_crop():
            self.update_tcp_messages(f"[AutoCrop] ⚠️ Not ready for auto-crop")
            return False

        # ALWAYS ask user where to save (every time)
        save_folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Save Cropped Image",
            os.path.expanduser("~"),  # Start from user's home directory
            QFileDialog.ShowDirsOnly
        )

        if not save_folder:
            self.update_tcp_messages(f"[AutoCrop] ⏹️ Auto-crop cancelled - no folder selected")
            return False

        # Keep original message for JSON
        original_message = tcp_message

        # Sanitize the TCP message for filename only (remove special characters)
        sanitized_text = self.sanitize_filename(tcp_message)
        if not sanitized_text:
            sanitized_text = "unknown"
            self.update_tcp_messages(f"[AutoCrop] ⚠️ Using 'unknown' as TCP text was empty")

        try:
            # Read the original image
            image = Image.open(self.image_path)
            img_width, img_height = image.size

            # Get the last drawn bounding box coordinates
            box, label = self.last_bounding_box

            # Convert QRectF coordinates to pixel integers
            x1 = max(0, int(box.x()))
            y1 = max(0, int(box.y()))
            x2 = min(img_width, int(box.x() + box.width()))
            y2 = min(img_height, int(box.y() + box.height()))

            # Validate box dimensions
            if x1 >= x2 or y1 >= y2:
                self.update_tcp_messages(f"[AutoCrop] ❌ Invalid bounding box dimensions")
                return False

            # Crop the image
            cropped_image = image.crop((x1, y1, x2, y2))

            # Generate filename using SANITIZED text (for filesystem safety)
            label_name = label.split()[0] if ' ' in label else label
            filename = f"{label_name}_{sanitized_text}.bmp"
            save_path = os.path.join(save_folder, filename)

            # Ensure unique filename
            counter = 1
            while os.path.exists(save_path):
                filename = f"{label_name}_{sanitized_text}_{counter}.bmp"
                save_path = os.path.join(save_folder, filename)
                counter += 1

            # Save as BMP format
            cropped_image.save(save_path, "BMP")

            # Get crop dimensions
            crop_width = x2 - x1
            crop_height = y2 - y1

            # Save TCP data to JSON (using ORIGINAL message with all characters)
            self.save_tcp_data_to_json(original_message, save_folder)

            # Update TCP messages
            self.update_tcp_messages(f"[AutoCrop] ✅ Auto-saved cropped image!")
            self.update_tcp_messages(f"[AutoCrop]   Filename: {filename}")
            self.update_tcp_messages(f"[AutoCrop]   Label: {label_name}")
            self.update_tcp_messages(f"[AutoCrop]   TCP Text (sanitized for file): {sanitized_text}")
            self.update_tcp_messages(f"[AutoCrop]   TCP Text (original for JSON): {original_message}")
            self.update_tcp_messages(f"[AutoCrop]   Dimensions: {crop_width}x{crop_height} pixels")
            self.update_tcp_messages(f"[AutoCrop]   Saved to: {save_folder}")
            self.update_tcp_messages(f"[AutoCrop]   📊 JSON: {original_message}")

            # Update status label
            self.status_label.setText(f"Auto-saved: {filename}")

            # Show brief notification
            QTimer.singleShot(100, lambda: self.show_auto_crop_notification(filename, label_name, original_message))

            return True

        except Exception as e:
            error_msg = f"Auto-crop failed: {str(e)}"
            self.update_tcp_messages(f"[AutoCrop] ❌ {error_msg}")
            print(f"Auto-crop error: {e}")
            return False

    def is_ready_for_auto_crop(self):
        """Check if all conditions are met for auto-cropping"""
        # Check if image is loaded
        if not hasattr(self, 'image_path') or not self.image_path or not os.path.exists(self.image_path):
            return False

        # Check if bounding box exists
        if not self.last_bounding_box:
            self.update_tcp_messages(f"[AutoCrop] ❌ No bounding box drawn")
            return False

        # Check if label exists
        if not self.last_box_label:
            self.update_tcp_messages(f"[AutoCrop] ❌ No label for bounding box")
            return False

        return True

    def sanitize_filename(self, text):
        """Sanitize TCP text for use in filename"""
        if not text:
            return "unknown"

        # Remove any non-alphanumeric characters (except underscore and dash)
        import re
        sanitized = re.sub(r'[^\w\-_]', '', text)

        # Trim length to reasonable size
        if len(sanitized) > 50:
            sanitized = sanitized[:50]

        # If empty after sanitization, use default
        if not sanitized:
            sanitized = "tcp_text"

        return sanitized

    def show_auto_crop_notification(self, filename, label_name, tcp_text):
        """Show a brief notification about auto-crop"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Auto Crop & Save")
        msg_box.setText(f"✅ Auto-saved cropped image!\n\n"
                        f"📄 {filename}\n"
                        f"🏷️ Label: {label_name}\n"
                        f"📡 TCP Text: {tcp_text}")
        msg_box.setIcon(QMessageBox.Information)

        # Auto-close after 2 seconds
        QTimer.singleShot(2000, msg_box.close)
        msg_box.show()

    def delete_selected(self):
        """Delete selected bounding box safely"""
        try:
            self.viewer.delete_selected()
            # Reset selection after deletion
            self.viewer.selected_index = -1
        except (IndexError, AttributeError) as e:
            print(f"Error in delete_selected: {e}")
            # If error occurs, just reset everything
            self.viewer.selected_index = -1
            self.viewer.boxes = []
            self.viewer.update()
            self.status_label.setText("Reset due to error")

    def capture_from_camera(self):
        """Capture from camera and save to Capture Image folder"""
        # Always use this specific path
        self.capture_folder = self.capture_image_path

        self.save_current()

        os.makedirs(self.capture_folder, exist_ok=True)

        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("Capturing...")

        def run_capture():
            def callback(success, message, image_path):
                if success and image_path:
                    os.makedirs(self.capture_folder, exist_ok=True)
                    print("capture_folder =", self.capture_folder)
                    print("files before delete =", os.listdir(self.capture_folder))

                    # 删掉旧 bmp
                    for file_name in os.listdir(self.capture_folder):
                        file_path = os.path.join(self.capture_folder, file_name)
                        if os.path.isfile(file_path) and file_name.lower().endswith(".bmp"):
                            try:
                                os.remove(file_path)
                            except Exception as e:
                                print(f"Failed to delete old image: {file_path}, error: {e}")

                    # 永远只存这一张
                    save_path = os.path.join(self.capture_folder, "capture.bmp")

                    import shutil
                    shutil.move(image_path, save_path)
                    image_path = save_path

                self.camera_signals.finished.emit(success, message, image_path)

            AutoCaptureFlow(callback=callback)

        thread = threading.Thread(target=run_capture, daemon=True)
        thread.start()

    def on_camera_finished(self, success, message, image_path):
        """Handle camera capture completion"""
        self.capture_btn.setEnabled(True)
        self.capture_btn.setText("Capture Image")

        if success and image_path:
            if os.path.exists(image_path):
                if image_path not in self.image_files:
                    self.image_files.append(image_path)
                    self.image_files.sort()

                self.current_index = self.image_files.index(image_path)
                self.load_current_image()
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
        path = self.image_files[self.current_index]
        self.viewer.boxes.clear()
        self.viewer.load_image(path)
        self.image_path = path

        if path in self.image_boxes:
            self.viewer.boxes = self.image_boxes[path].copy()

        self.setWindowTitle(
            f"BMP Annotation Tool – {os.path.basename(path)} "
            f"({self.current_index + 1}/{len(self.image_files)})"
        )

        # Update image info label
        self.image_info_label.setText(f"{os.path.basename(path)} ({self.current_index + 1}/{len(self.image_files)})")

        self.image_info_label.setText(f"{os.path.basename(path)} ({self.current_index + 1}/{len(self.image_files)})")

        # Force update
        self.viewer.update()

    def get_current_label(self):
        return self.label_combo.currentText()

    def undo(self):
        """Undo last action safely"""
        try:
            self.viewer.undo_last()
            # Reset selection after undo
            self.viewer.selected_index = -1
        except IndexError:
            self.viewer.selected_index = -1
            self.viewer.update()

    def save_current(self):
        """Save annotations for current image in YOLO format"""
        if hasattr(self, "image_path") and self.image_path:
            self.viewer.save_annotations(self.image_path)
            if hasattr(self.viewer, 'boxes'):
                self.image_boxes[self.image_path] = self.viewer.boxes.copy()

    def save_tcp_data_to_json(self, tcp_message, save_folder):
        """Save the original TCP message to JSON file (keeping all characters)"""
        try:
            # Create JSON file path in the selected folder
            json_path = os.path.join(save_folder, "tcp_received_data.json")

            # Use the original message WITHOUT sanitization
            # Keep all special characters, spaces, etc.

            # Load existing data or create new list
            existing_data = []
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as f:
                        existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []

            # Append the original message (keep all characters)
            existing_data.append(tcp_message)

            # Save back to file
            with open(json_path, 'w') as f:
                json.dump(existing_data, f, indent=2)

            self.update_tcp_messages(
                f"[JSON] 💾 Saved original message: {tcp_message[:50]}{'...' if len(tcp_message) > 50 else ''}")
            return True

        except Exception as e:
            self.update_tcp_messages(f"[JSON] ❌ Failed to save data: {str(e)}")
            return False

    def reset_viewer_selection(self):
        """Reset viewer selection to avoid index errors"""
        if hasattr(self.viewer, 'selected_index'):
            self.viewer.selected_index = -1
        if hasattr(self.viewer, 'drawing'):
            self.viewer.drawing = False
        if hasattr(self.viewer, 'current_rect'):
            self.viewer.current_rect = None
        if hasattr(self.viewer, 'temp_box_corners'):
            self.viewer.temp_box_corners = []
        # Remove obb_corners reference
        if hasattr(self.viewer, 'update'):
            self.viewer.update()

    def check_and_fix_selection(self):
        """Check if selected index is valid and fix if not"""
        if not hasattr(self.viewer, 'selected_index') or not hasattr(self.viewer, 'boxes'):
            return

        try:
            # If there are no boxes, ensure selected_index is -1
            if len(self.viewer.boxes) == 0:
                if self.viewer.selected_index != -1:
                    self.viewer.selected_index = -1
                    self.viewer.update()
            # If selected index is out of range, reset it
            elif self.viewer.selected_index >= len(self.viewer.boxes):
                self.viewer.selected_index = -1
                self.viewer.update()
        except Exception as e:
            print(f"Error in check_and_fix_selection: {e}")
            self.viewer.selected_index = -1

    def force_reset_viewer(self):
        """Force reset the viewer by directly manipulating its attributes"""
        try:
            # Direct attribute manipulation
            self.viewer.boxes = []
            self.viewer.selected_index = -1
            self.viewer.drawing = False
            self.viewer.current_rect = None
            self.viewer.temp_box_corners = []
            self.viewer.update()
        except Exception as e:
            print(f"Error in force_reset_viewer: {e}")

import sys
from PySide6.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())