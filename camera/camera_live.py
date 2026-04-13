import sys
import socket
import struct
import json
import os
import ctypes
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout,
                               QWidget, QPushButton, QSpinBox, QGroupBox,
                               QGridLayout, QHBoxLayout, QLineEdit, QComboBox)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush
from camera.SciCam_class import *


class ColorValidator:
    """Validate colors against saved annotations with tolerance"""

    def __init__(self, tolerance=5):
        self.tolerance = tolerance

    def validate_color(self, current_rgb, saved_rgb):
        """Validate if current RGB is within tolerance of saved RGB"""
        r_diff = abs(current_rgb[0] - saved_rgb[0])
        g_diff = abs(current_rgb[1] - saved_rgb[1])
        b_diff = abs(current_rgb[2] - saved_rgb[2])

        is_valid = (r_diff <= self.tolerance and
                    g_diff <= self.tolerance and
                    b_diff <= self.tolerance)

        return is_valid, (r_diff, g_diff, b_diff)


class SciCamLiveView(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SciCam Live View - Real-time Color Validation")
        self.setMinimumSize(800, 600)

        self.camera = SciCamera()
        self.device_info = None
        self.is_live = False
        self.current_payload = None

        # Store image data
        self.current_image_data = None
        self.current_image_width = None
        self.current_image_height = None
        self.current_image_format = None

        # Tolerance
        self.tolerance = 5

        # Track last result with stability timer
        self.last_result = None
        self.last_rgb = None
        self.stable_result = None
        self.current_result = None
        self.result_start_time = None
        self.stability_duration = 3000  # 3 seconds in milliseconds
        self.stability_timer = QTimer()
        self.stability_timer.setSingleShot(True)
        #self.stability_timer.timeout.connect(self.on_result_stable)
        self.result_stable_time = None  # When the current result started
        self.stability_duration = 3000  # 3 seconds in milliseconds

        # Setup UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #1a1a2e; border: 2px solid #e94560;")
        self.image_label.setMinimumHeight(400)
        layout.addWidget(self.image_label)

        # Recipe selection
        recipe_layout = QHBoxLayout()
        recipe_layout.addWidget(QLabel("Recipe:"))
        self.recipe_combo = QComboBox()
        self.recipe_combo.setMinimumWidth(200)
        self.recipe_combo.currentTextChanged.connect(self.on_recipe_changed)
        recipe_layout.addWidget(self.recipe_combo)

        self.load_recipes_btn = QPushButton("Refresh")
        self.load_recipes_btn.clicked.connect(self.load_recipes)
        recipe_layout.addWidget(self.load_recipes_btn)
        layout.addLayout(recipe_layout)

        # Annotation file selection (contains color JSON)
        annotation_layout = QHBoxLayout()
        annotation_layout.addWidget(QLabel("Reference Image:"))
        self.annotation_combo = QComboBox()
        self.annotation_combo.setMinimumWidth(300)
        self.annotation_combo.currentTextChanged.connect(self.on_annotation_changed)
        annotation_layout.addWidget(self.annotation_combo)

        self.load_annotations_btn = QPushButton("Load Reference")
        self.load_annotations_btn.clicked.connect(self.load_annotation_files)
        annotation_layout.addWidget(self.load_annotations_btn)
        layout.addLayout(annotation_layout)

        # Tolerance setting
        tolerance_layout = QHBoxLayout()
        tolerance_layout.addWidget(QLabel("Tolerance (±):"))
        self.tolerance_spin = QSpinBox()
        self.tolerance_spin.setRange(0, 50)
        self.tolerance_spin.setValue(5)
        self.tolerance_spin.valueChanged.connect(self.on_tolerance_changed)
        tolerance_layout.addWidget(self.tolerance_spin)
        tolerance_layout.addStretch()
        layout.addLayout(tolerance_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Live View")
        self.start_btn.clicked.connect(self.start_live_view)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #27ae60; }
        """)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Live View")
        self.stop_btn.clicked.connect(self.stop_live_view)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        # Result label (shows PASS/NG in real-time)
        self.result_label = QLabel("Ready - Select a reference image")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 8px;
                margin-top: 10px;
                background-color: #f0f0f0;
                color: #333;
            }
        """)
        layout.addWidget(self.result_label)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    padding: 5px;
                    color: #666;
                }
            """)
        layout.addWidget(self.status_label)

        # RGB values display
        self.rgb_label = QLabel("RGB: --, --, --")
        self.rgb_label.setAlignment(Qt.AlignCenter)
        self.rgb_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                padding: 8px;
                font-family: monospace;
                background-color: #2c3e50;
                color: #ecf0f1;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.rgb_label)

        # Reference info label
        self.ref_label = QLabel("Reference: None selected (load JSON file)")
        self.ref_label.setAlignment(Qt.AlignCenter)
        self.ref_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                padding: 5px;
                color: #666;
            }
        """)
        layout.addWidget(self.ref_label)

        # Timer for continuous frame grabbing
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        # Load recipes on startup
        self.load_recipes()

    def load_recipes(self):
        """Load all available recipes"""
        try:
            recipes_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "recipes")

            if os.path.exists(recipes_dir):
                recipes = [d for d in os.listdir(recipes_dir)
                           if os.path.isdir(os.path.join(recipes_dir, d))]

                self.recipe_combo.clear()
                for recipe in recipes:
                    self.recipe_combo.addItem(recipe)

                self.status_label.setText(f"Found {len(recipes)} recipes")
            else:
                print("No recipes folder found")

        except Exception as e:
            print(f"Error loading recipes: {e}")

    def on_recipe_changed(self, recipe_name):
        """Handle recipe selection change"""
        if recipe_name:
            self.recipe_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                            "recipes", recipe_name)
            self.annotation_path = os.path.join(self.recipe_path, "Annotation")
            self.load_annotation_files()

    def load_annotation_files(self):
        """Load JSON files that contain color data (no BMP needed)"""
        if not self.annotation_path or not os.path.exists(self.annotation_path):
            return

        try:
            # Find all JSON files (they contain the color data)
            json_files = [f for f in os.listdir(self.annotation_path)
                          if f.lower().endswith('_colors.json')]

            self.annotation_combo.clear()

            for json_file in json_files:
                # Extract base name (remove _colors.json)
                base_name = json_file.replace('_colors.json', '')
                self.annotation_combo.addItem(base_name)

            if self.annotation_combo.count() > 0:
                self.annotation_combo.setCurrentIndex(0)
                self.status_label.setText(f"Found {self.annotation_combo.count()} reference files with color data")
            else:
                self.status_label.setText("No reference files with color data found")

        except Exception as e:
            print(f"Error loading annotation files: {e}")
            self.status_label.setText(f"Error loading annotations: {e}")

    def on_annotation_changed(self, base_name):
        """Load reference data from JSON file only (no BMP needed)"""
        if not base_name or not self.annotation_path:
            return

        try:
            json_path = os.path.join(self.annotation_path, f"{base_name}_colors.json")

            print(f"\n{'=' * 50}")
            print(f"Loading reference data from: {base_name}_colors.json")
            print(f"{'=' * 50}")

            # Load JSON only (ignore BMP)
            with open(json_path, 'r') as f:
                color_data = json.load(f)

            print(f"JSON contains {len(color_data)} entries")

            # Use the most recent entry
            ref_data = color_data[-1]

            # Get ROI from JSON (these coordinates are from 5120x5120 camera image)
            if 'bbox' in ref_data:
                bbox = ref_data['bbox']
                self.reference_roi = (
                    int(bbox.get('x', 0)),
                    int(bbox.get('y', 0)),
                    int(bbox.get('width', 100)),
                    int(bbox.get('height', 100))
                )
                print(f"Using bbox: ROI = {self.reference_roi}")

            # Set reference image size to match live camera (5120x5120)
            self.reference_image_size = (5120, 5120)

            # Extract RGB reference color
            avg_color = ref_data.get('average_color', {})
            self.reference_rgb = (
                avg_color.get('r', 0),
                avg_color.get('g', 0),
                avg_color.get('b', 0)
            )

            self.reference_label = ref_data.get('label', 'unknown')

            # Reset all tracking when new reference is loaded
            self.last_result = None
            self.last_rgb = None
            self.stable_result = None
            self.result_start_time = None
            self.stability_timer.stop()

            # Update display
            self.ref_label.setText(
                f"Reference: {base_name} | "
                f"Label: {self.reference_label} | "
                f"ROI: ({self.reference_roi[0]},{self.reference_roi[1]}) "
                f"Size: {self.reference_roi[2]}x{self.reference_roi[3]} | "
                f"Reference Color: RGB({self.reference_rgb[0]:.0f}, "
                f"{self.reference_rgb[1]:.0f}, {self.reference_rgb[2]:.0f})"
            )

            self.result_label.setText("✅ Reference loaded. Start live view to validate.")
            self.result_label.setStyleSheet("""
                QLabel {
                    background-color: #d4edda;
                    color: #155724;
                    border: 2px solid #28a745;
                    border-radius: 8px;
                    padding: 15px;
                    font-size: 14px;
                    font-weight: bold;
                }
            """)

            print(f"Reference ROI (from JSON): {self.reference_roi}")
            print(f"Reference RGB: {self.reference_rgb}")
            print(f"Reference image size set to: {self.reference_image_size}")

        except Exception as e:
            print(f"Error loading reference data: {e}")
            import traceback
            traceback.print_exc()
            self.reference_roi = None
            self.reference_rgb = None

    def on_tolerance_changed(self, value):
        """Update tolerance value"""
        self.tolerance = value
        print(f"Tolerance changed to: ±{value}")
        # Reset tracking when tolerance changes
        self.last_result = None
        self.stable_result = None
        self.result_start_time = None
        self.stability_timer.stop()

    # def on_result_stable(self):
    #     """Called when a result has been stable for 3 seconds"""
    #     if self.stable_result is not None:
    #         timestamp = datetime.now().strftime("%H:%M:%S")
    #         if self.stable_result == "PASS":
    #             print(f"[{timestamp}] ✅ OK - Color stable within tolerance (±{self.tolerance}) for 3 seconds")
    #         else:
    #             print(f"[{timestamp}] ❌ NG - Color stable OUT of tolerance (±{self.tolerance}) for 3 seconds")
    #
    #         # Also print the last RGB values
    #         if self.last_rgb:
    #             print(f"    Stable RGB: ({self.last_rgb[0]:.0f}, {self.last_rgb[1]:.0f}, {self.last_rgb[2]:.0f})")
    #             print(
    #                 f"    Reference RGB: ({self.reference_rgb[0]:.0f}, {self.reference_rgb[1]:.0f}, {self.reference_rgb[2]:.0f})")
    #
    #         # Reset stable result to avoid repeated prints
    #         self.stable_result = None

    def init_camera(self):
        """Initialize and open camera"""
        print("[1/4] Discovering devices...")
        devInfos = SCI_DEVICE_INFO_LIST()
        reVal = SciCamera.SciCam_DiscoveryDevices(devInfos, SciCamTLType.SciCam_TLType_Unkown)

        if reVal != SCI_CAMERA_OK or devInfos.count == 0:
            print("ERROR: No devices found!")
            return False

        self.device_info = devInfos.pDevInfo[0]

        # Show camera info
        if self.device_info.tlType == SciCamTLType.SciCam_TLType_Gige:
            cam_ip = self.uint32_to_ipv4(self.device_info.info.gigeInfo.ip)
            cam_name = ''
            for per in self.device_info.info.gigeInfo.modelName:
                if per == 0:
                    break
                cam_name = cam_name + chr(per)
            print(f"Found camera: {cam_name} - IP: {cam_ip}")
        else:
            print(f"Found camera: {self.device_info.info.usb3Info.modelName}")

        print("[2/4] Opening device...")
        reVal = self.camera.SciCam_CreateDevice(self.device_info)
        if reVal != SCI_CAMERA_OK:
            print(f"ERROR: Create device failed: {reVal}")
            return False

        reVal = self.camera.SciCam_OpenDevice()
        if reVal != SCI_CAMERA_OK:
            print(f"ERROR: Open device failed: {reVal}")
            return False

        # Set exposure time
        self.camera.SciCam_SetFloatValueEx(0, "ExposureTime", 15000)

        print("[3/4] Starting grabbing...")
        reVal = self.camera.SciCam_StartGrabbing()
        if reVal != SCI_CAMERA_OK:
            print(f"ERROR: Start grabbing failed: {reVal}")
            return False

        print("Camera ready for live view!")
        return True

    def get_average_color_from_roi(self, image_data, roi_rect, width, height, format_type):
        """Calculate average RGB color from ROI"""
        if image_data is None or roi_rect is None:
            return None

        x, y, w, h = roi_rect
        total_r = total_g = total_b = 0
        pixel_count = 0

        x_end = min(x + w, width)
        y_end = min(y + h, height)
        x = max(0, x)
        y = max(0, y)

        if format_type == SciCamPixelType.RGB8:
            for i in range(y, y_end):
                for j in range(x, x_end):
                    idx = (i * width + j) * 3
                    total_r += image_data[idx]
                    total_g += image_data[idx + 1]
                    total_b += image_data[idx + 2]
                    pixel_count += 1
        elif format_type == SciCamPixelType.Mono8:
            for i in range(y, y_end):
                for j in range(x, x_end):
                    idx = i * width + j
                    gray = image_data[idx]
                    total_r += gray
                    total_g += gray
                    total_b += gray
                    pixel_count += 1

        if pixel_count > 0:
            return (total_r / pixel_count, total_g / pixel_count, total_b / pixel_count)
        return None

    def update_frame(self):
        """Grab a frame, validate color, and update display"""
        if not self.is_live:
            return

        # Free previous payload
        if self.current_payload:
            self.camera.SciCam_FreePayload(self.current_payload)

        # Grab new frame
        ppayload = ctypes.c_void_p()
        reVal = self.camera.SciCam_Grab(ppayload)
        if reVal != SCI_CAMERA_OK:
            return

        self.current_payload = ppayload

        # Get image attributes
        payloadAttribute = SCI_CAM_PAYLOAD_ATTRIBUTE()
        reVal = SciCam_Payload_GetAttribute(ppayload, payloadAttribute)
        if reVal != SCI_CAMERA_OK:
            return

        imgWidth = payloadAttribute.imgAttr.width
        imgHeight = payloadAttribute.imgAttr.height
        imgPixelType = payloadAttribute.imgAttr.pixelType

        # Get image data
        imgData = ctypes.c_void_p()
        reVal = SciCam_Payload_GetImage(ppayload, imgData)
        if reVal != SCI_CAMERA_OK:
            return

        # Convert to RGB8 for display
        dstImgSize = ctypes.c_int()

        mono_formats = [
            SciCamPixelType.Mono1p, SciCamPixelType.Mono2p, SciCamPixelType.Mono4p,
            SciCamPixelType.Mono8s, SciCamPixelType.Mono8, SciCamPixelType.Mono10,
            SciCamPixelType.Mono10p, SciCamPixelType.Mono12, SciCamPixelType.Mono12p,
            SciCamPixelType.Mono14, SciCamPixelType.Mono16, SciCamPixelType.Mono10Packed,
            SciCamPixelType.Mono12Packed, SciCamPixelType.Mono14p
        ]

        if imgPixelType in mono_formats:
            target_format = SciCamPixelType.Mono8
        else:
            target_format = SciCamPixelType.RGB8

        reVal = SciCam_Payload_ConvertImage(payloadAttribute.imgAttr, imgData, target_format, None, dstImgSize, True)

        if reVal == SCI_CAMERA_OK:
            pDstData = (ctypes.c_ubyte * dstImgSize.value)()
            reVal = SciCam_Payload_ConvertImageEx(payloadAttribute.imgAttr, imgData, target_format, pDstData,
                                                  dstImgSize, True, 0)

            if reVal == SCI_CAMERA_OK:
                # Store image data
                self.current_image_data = pDstData
                self.current_image_width = imgWidth
                self.current_image_height = imgHeight
                self.current_image_format = target_format

                # Calculate color from ROI if reference exists
                if hasattr(self, 'reference_roi') and self.reference_roi and hasattr(self,
                                                                                     'reference_rgb') and self.reference_rgb:

                    # Check if ROI is within image bounds
                    x, y, w, h = self.reference_roi
                    if x + w <= self.current_image_width and y + h <= self.current_image_height:

                        self.current_rgb = self.get_average_color_from_roi(
                            self.current_image_data,
                            self.reference_roi,
                            self.current_image_width,
                            self.current_image_height,
                            self.current_image_format
                        )

                        if self.current_rgb:
                            # Validate color
                            validator = ColorValidator(tolerance=self.tolerance)
                            is_valid, differences = validator.validate_color(
                                self.current_rgb,
                                self.reference_rgb
                            )

                            # Update RGB display
                            self.rgb_label.setText(
                                f"Current RGB: ({self.current_rgb[0]:.0f}, {self.current_rgb[1]:.0f}, {self.current_rgb[2]:.0f}) | "
                                f"Diff: Δ{int(differences[0])}, Δ{int(differences[1])}, Δ{int(differences[2])}"
                            )

                            # Determine current result
                            current_result = "OK" if is_valid else "NG"

                            # Check if result changed
                            if current_result != self.current_result:
                                # Result changed - reset timer
                                self.current_result = current_result
                                self.result_stable_time = datetime.now()
                                self.stable_result = None  # Clear stable result until confirmed

                            elif self.stable_result is None:
                                # Result same - check if stable for 3 seconds
                                elapsed_ms = (datetime.now() - self.result_stable_time).total_seconds() * 1000
                                if elapsed_ms >= self.stability_duration:
                                    # Result has been stable for 3 seconds
                                    self.stable_result = current_result
                                    print(self.stable_result)

                            # Update result display
                            if is_valid:
                                self.result_label.setText(
                                    f"✅ PASS - Color within tolerance (±{self.tolerance})"
                                )
                                self.result_label.setStyleSheet("""
                                    QLabel {
                                        background-color: #d4edda;
                                        color: #155724;
                                        border: 2px solid #28a745;
                                        border-radius: 8px;
                                        padding: 15px;
                                        font-size: 18px;
                                        font-weight: bold;
                                    }
                                """)
                            else:
                                self.result_label.setText(
                                    f"❌ NG - Color OUT of tolerance (±{self.tolerance})"
                                )
                                self.result_label.setStyleSheet("""
                                    QLabel {
                                        background-color: #f8d7da;
                                        color: #721c24;
                                        border: 2px solid #dc3545;
                                        border-radius: 8px;
                                        padding: 15px;
                                        font-size: 18px;
                                        font-weight: bold;
                                    }
                                """)
                        else:
                            self.rgb_label.setText("RGB: Failed to calculate")
                    else:
                        self.rgb_label.setText(f"RGB: ROI out of bounds (x={x}, y={y})")

                # Convert to QImage for display
                if target_format == SciCamPixelType.Mono8:
                    qimage = QImage(pDstData, imgWidth, imgHeight, imgWidth, QImage.Format_Grayscale8)
                else:
                    qimage = QImage(pDstData, imgWidth, imgHeight, imgWidth * 3, QImage.Format_RGB888)

                # Draw ROI rectangle on image
                pixmap = QPixmap.fromImage(qimage)

                if hasattr(self, 'reference_roi') and self.reference_roi:
                    painter = QPainter(pixmap)
                    x, y, w, h = self.reference_roi

                    # Only draw if within bounds
                    if x + w <= pixmap.width() and y + h <= pixmap.height():
                        # Determine color based on stable result if available, otherwise current result
                        if self.stable_result == "OK":
                            pen_color = QColor(0, 255, 0)  # Green
                        elif self.stable_result == "NG":
                            pen_color = QColor(255, 0, 0)  # Red
                        elif hasattr(self, 'current_rgb') and self.current_rgb:
                            # Use current result if no stable result yet
                            validator = ColorValidator(tolerance=self.tolerance)
                            is_valid, _ = validator.validate_color(self.current_rgb, self.reference_rgb)
                            pen_color = QColor(0, 255, 0) if is_valid else QColor(255, 0, 0)
                        else:
                            pen_color = QColor(255, 255, 0)  # Yellow for no data

                        painter.setPen(QPen(pen_color, 3, Qt.SolidLine))
                        painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
                        painter.drawRect(x, y, w, h)

                        # Draw label
                        if hasattr(self, 'reference_label') and self.reference_label:
                            painter.setPen(QPen(pen_color, 2))
                            painter.drawText(x + 5, y + 20, f"{self.reference_label}")

                    painter.end()

                # Scale to fit label
                scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled_pixmap)

    def start_live_view(self):
        """Start live view"""
        if not hasattr(self, 'reference_roi') or not self.reference_roi:
            self.result_label.setText("⚠️ Please select a reference image first!")
            return

        if not self.init_camera():
            self.image_label.setText("Failed to initialize camera!")
            return

        self.is_live = True
        self.timer.start(50)

        # Reset all tracking when starting new session
        self.last_result = None
        self.last_rgb = None
        self.stable_result = None
        self.result_start_time = None
        self.stability_timer.stop()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        print("Live view started with real-time color validation!")

    def stop_live_view(self):
        """Stop live view"""
        self.is_live = False
        self.timer.stop()

        if self.current_payload:
            self.camera.SciCam_FreePayload(self.current_payload)
            self.current_payload = None

        self.camera.SciCam_StopGrabbing()
        self.camera.SciCam_CloseDevice()
        self.camera.SciCam_DeleteDevice()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        print("Live view stopped!")

    def uint32_to_ipv4(self, ip_uint32):
        """Convert uint32 IP address to dotted decimal format"""
        network_order_ip = socket.htonl(ip_uint32)
        packed_ip = struct.pack("!I", network_order_ip)
        ipv4_address = socket.inet_ntoa(packed_ip)
        return ipv4_address

    def closeEvent(self, event):
        """Cleanup on close"""
        self.stop_live_view()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SciCamLiveView()
    window.show()
    sys.exit(app.exec())