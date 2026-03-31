import json
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QFileDialog, QSizePolicy
)

# Source camera auto capture
try:
    from camera.camera import AutoCaptureFlow
    SOURCE_CAMERA_AVAILABLE = True
except ImportError:
    SOURCE_CAMERA_AVAILABLE = False
    print("Warning: camera.camera AutoCaptureFlow not found. Source auto-capture disabled.")


def _np_bgr_to_qpixmap(frame_bgr: np.ndarray) -> QPixmap:
    if frame_bgr is None:
        return QPixmap()
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


class ClickableImageLabel(QLabel):
    point_clicked = Signal(float, float)

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(500, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("""
            QLabel {
                background-color: #030810;
                border: 1px solid #0E2A40;
                color: #AACCEE;
            }
        """)

        self._title = title
        self._base_pixmap: Optional[QPixmap] = None
        self._display_pixmap: Optional[QPixmap] = None

        self.image_points: List[Tuple[float, float]] = []
        self.display_points: List[Tuple[float, float]] = []

        self._img_rect = QRectF()
        self._scale_x = 1.0
        self._scale_y = 1.0

        self.setText(title if title else "No image")

    def set_image_from_pixmap(self, pixmap: QPixmap):
        self._base_pixmap = pixmap
        self._refresh_scaled_pixmap()

    def clear_points(self):
        self.image_points.clear()
        self.display_points.clear()
        self.update()

    def get_image_points(self) -> List[Tuple[float, float]]:
        return list(self.image_points)

    def has_image(self) -> bool:
        return self._base_pixmap is not None and not self._base_pixmap.isNull()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_scaled_pixmap()

    def _refresh_scaled_pixmap(self):
        if not self.has_image():
            return

        scaled = self._base_pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self._display_pixmap = scaled
        self.setPixmap(self._display_pixmap)

        x = (self.width() - scaled.width()) / 2.0
        y = (self.height() - scaled.height()) / 2.0
        self._img_rect = QRectF(x, y, scaled.width(), scaled.height())

        self._scale_x = self._base_pixmap.width() / self._img_rect.width() if self._img_rect.width() else 1.0
        self._scale_y = self._base_pixmap.height() / self._img_rect.height() if self._img_rect.height() else 1.0

        self.display_points = []
        for ix, iy in self.image_points:
            dx = self._img_rect.x() + ix / self._scale_x
            dy = self._img_rect.y() + iy / self._scale_y
            self.display_points.append((dx, dy))

        self.update()

    def mousePressEvent(self, event):
        if not self.has_image():
            return super().mousePressEvent(event)

        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        # limit to 4 points
        if len(self.image_points) >= 4:
            return

        px = float(event.position().x())
        py = float(event.position().y())

        if not self._img_rect.contains(px, py):
            return

        img_x = (px - self._img_rect.x()) * self._scale_x
        img_y = (py - self._img_rect.y()) * self._scale_y

        self.image_points.append((img_x, img_y))
        self.display_points.append((px, py))
        self.point_clicked.emit(img_x, img_y)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._title:
            painter.setPen(QColor("#AACCEE"))
            painter.drawText(12, 24, self._title)

        pen = QPen(QColor("#FF3344"), 6)
        painter.setPen(pen)

        for idx, (x, y) in enumerate(self.display_points, start=1):
            painter.drawEllipse(int(x - 4), int(y - 4), 8, 8)
            painter.drawText(int(x + 8), int(y - 8), str(idx))

        painter.end()


class Calibration(QDialog):
    def __init__(
        self,
        source_image_path: str = "",
        recipe_name: str = "",
        orbbec_thread=None,
        calibration_save_path: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Calibration")
        self.resize(1500, 900)
        self.setStyleSheet("""
            QDialog {
                background-color: #060C14;
                border: 1px solid #00AAFF33;
            }
            QLabel {
                color: #AACCEE;
                font-family: Consolas;
            }
            QPushButton {
                font-size: 14px;
                font-weight: 800;
                padding: 10px 18px;
                background-color: #081420;
                color: #AACCEE;
                border: 1px solid #0E2A40;
                border-left: 3px solid #00AAFF;
                font-family: Consolas;
            }
            QPushButton:hover {
                background-color: #0C1E30;
                color: #FFFFFF;
            }
        """)

        self.source_image_path = source_image_path or ""
        self.recipe_name = recipe_name
        self.orbbec_thread = orbbec_thread
        self.calibration_save_path = calibration_save_path or self._default_calibration_path()

        self.source_pixmap: Optional[QPixmap] = None
        self.target_pixmap: Optional[QPixmap] = None
        self.target_frame_bgr: Optional[np.ndarray] = None
        self.H: Optional[np.ndarray] = None

        self._build_ui()

        # If caller already passed a source image, load it.
        if self.source_image_path and os.path.exists(self.source_image_path):
            self._load_source_image()

        # Auto capture source camera first, then Orbbec
        QTimer.singleShot(300, self.capture_source_camera_frame)
        QTimer.singleShot(1200, self.capture_orbbec_frame)

    def _default_calibration_path(self) -> str:
        if self.recipe_name:
            return os.path.join("recipes", self.recipe_name, "orbbec_homography.json")
        return "orbbec_homography.json"

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        hdr = QLabel("CALIBRATION")
        hdr.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: 900;
                color: #FFFFFF;
                background-color: #050D18;
                border-bottom: 2px solid #00AAFF;
                border-left: 4px solid #00AAFF;
                padding: 12px 16px;
                letter-spacing: 2px;
                font-family: Consolas;
            }
        """)
        root.addWidget(hdr)

        self.info_label = QLabel(
            "Step 1: Auto-capture source camera    "
            "Step 2: Auto-capture Orbbec frame    "
            "Step 3: Click 4 points on LEFT image    "
            "Step 4: Click 4 matching points on RIGHT image    "
            "Step 5: Press Calibrate    "
            "Step 6: Save Calibration"
        )
        self.info_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                background-color: #030810;
                border-left: 3px solid #00AAFF44;
                padding: 8px 10px;
            }
        """)
        root.addWidget(self.info_label)

        images_row = QHBoxLayout()
        images_row.setSpacing(10)

        self.source_label = ClickableImageLabel("SOURCE CAMERA IMAGE")
        self.target_label = ClickableImageLabel("ORBBEC FRAME")

        self.source_label.point_clicked.connect(self._on_points_changed)
        self.target_label.point_clicked.connect(self._on_points_changed)

        images_row.addWidget(self.source_label, 1)
        images_row.addWidget(self.target_label, 1)
        root.addLayout(images_row, 1)

        counts_row = QHBoxLayout()
        self.source_count_label = QLabel("Source points: 0 / 4")
        self.target_count_label = QLabel("Target points: 0 / 4")
        self.status_label = QLabel("Status: Waiting")
        for w in (self.source_count_label, self.target_count_label, self.status_label):
            w.setStyleSheet("""
                QLabel {
                    font-size: 13px;
                    background-color: #030810;
                    border-left: 3px solid #00AAFF44;
                    padding: 8px 10px;
                }
            """)
        counts_row.addWidget(self.source_count_label)
        counts_row.addWidget(self.target_count_label)
        counts_row.addWidget(self.status_label, 1)
        root.addLayout(counts_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_capture_source = QPushButton("Capture Source Camera")
        self.btn_capture_orbbec = QPushButton("Capture Orbbec Frame")
        self.btn_clear = QPushButton("Clear Points")
        self.btn_undo_source = QPushButton("Undo Left")
        self.btn_undo_target = QPushButton("Undo Right")
        self.btn_calibrate = QPushButton("Calibrate")
        self.btn_preview = QPushButton("Preview Mapping")
        self.btn_save = QPushButton("Save Calibration")
        self.btn_load = QPushButton("Load Calibration")
        self.btn_close = QPushButton("Close")

        self.btn_capture_source.clicked.connect(self.capture_source_camera_frame)
        self.btn_capture_orbbec.clicked.connect(self.capture_orbbec_frame)
        self.btn_clear.clicked.connect(self.clear_points)
        self.btn_undo_source.clicked.connect(self.undo_left)
        self.btn_undo_target.clicked.connect(self.undo_right)
        self.btn_calibrate.clicked.connect(self.calibrate)
        self.btn_preview.clicked.connect(self.preview_mapping)
        self.btn_save.clicked.connect(self.save_calibration)
        self.btn_load.clicked.connect(self.load_calibration)
        self.btn_close.clicked.connect(self.reject)

        for b in (
            self.btn_capture_source, self.btn_capture_orbbec,
            self.btn_clear, self.btn_undo_source, self.btn_undo_target,
            self.btn_calibrate, self.btn_preview, self.btn_save,
            self.btn_load, self.btn_close
        ):
            btn_row.addWidget(b)

        root.addLayout(btn_row)

        self.preview_label = QLabel("Preview: not generated")
        self.preview_label.setMinimumHeight(42)
        self.preview_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                background-color: #030810;
                border-left: 3px solid #FFAA0044;
                padding: 8px 10px;
                color: #FFDD88;
            }
        """)
        root.addWidget(self.preview_label)

    def _load_source_image(self):
        if not self.source_image_path or not os.path.exists(self.source_image_path):
            self.status_label.setText("Status: Failed to load source image")
            return

        pm = QPixmap(self.source_image_path)
        if pm.isNull():
            self.status_label.setText("Status: Failed to load source image")
            return

        self.source_pixmap = pm
        self.source_label.set_image_from_pixmap(pm)
        self.status_label.setText(f"Status: Source image loaded ({pm.width()}x{pm.height()})")

    def _on_points_changed(self, *_):
        self.source_count_label.setText(f"Source points: {len(self.source_label.image_points)} / 4")
        self.target_count_label.setText(f"Target points: {len(self.target_label.image_points)} / 4")

    def capture_source_camera_frame(self):
        if not SOURCE_CAMERA_AVAILABLE:
            QMessageBox.warning(self, "No Source Camera", "AutoCaptureFlow is not available")
            self.status_label.setText("Status: Source camera module unavailable")
            return

        self.status_label.setText("Status: Capturing source camera image...")

        def on_capture_done(success, message, image_path):
            if not success or not image_path:
                QMessageBox.warning(self, "Source Camera", f"Capture failed:\n{message}")
                self.status_label.setText(f"Status: Source capture failed - {message}")
                return

            if not os.path.exists(image_path):
                QMessageBox.warning(self, "Source Camera", f"Captured file not found:\n{image_path}")
                self.status_label.setText("Status: Captured file not found")
                return

            self.source_image_path = image_path
            self._load_source_image()
            self.status_label.setText(f"Status: Source image captured ({os.path.basename(image_path)})")

        try:
            AutoCaptureFlow(callback=on_capture_done)
        except Exception as e:
            QMessageBox.critical(self, "Source Camera Error", str(e))
            self.status_label.setText(f"Status: Source camera error - {str(e)}")

    def capture_orbbec_frame(self, retry_count=0):
        if self.orbbec_thread is None:
            self.status_label.setText("Status: orbbec_thread is None")
            QMessageBox.warning(self, "No Orbbec", "orbbec_thread is None")
            return

        frame = getattr(self.orbbec_thread, "latest_frame", None)
        if frame is None:
            if retry_count < 10:
                self.status_label.setText(f"Status: Waiting for Orbbec frame... ({retry_count + 1})")
                QTimer.singleShot(300, lambda: self.capture_orbbec_frame(retry_count + 1))
            else:
                QMessageBox.warning(self, "No Frame", "No latest_frame available from Orbbec thread")
                self.status_label.setText("Status: No latest_frame available from Orbbec thread")
            return

        self.target_frame_bgr = frame.copy()
        self.target_pixmap = _np_bgr_to_qpixmap(self.target_frame_bgr)
        self.target_label.set_image_from_pixmap(self.target_pixmap)
        self.status_label.setText(
            f"Status: Orbbec frame captured ({self.target_pixmap.width()}x{self.target_pixmap.height()})"
        )

    def clear_points(self):
        self.source_label.clear_points()
        self.target_label.clear_points()
        self.H = None
        self.preview_label.setText("Preview: cleared")
        self._on_points_changed()
        self.status_label.setText("Status: Points cleared")

    def undo_left(self):
        if self.source_label.image_points:
            self.source_label.image_points.pop()
            if self.source_label.display_points:
                self.source_label.display_points.pop()
            self.source_label.update()
        self._on_points_changed()

    def undo_right(self):
        if self.target_label.image_points:
            self.target_label.image_points.pop()
            if self.target_label.display_points:
                self.target_label.display_points.pop()
            self.target_label.update()
        self._on_points_changed()

    def calibrate(self):
        src_points = self.source_label.get_image_points()
        dst_points = self.target_label.get_image_points()

        if len(src_points) != 4 or len(dst_points) != 4:
            QMessageBox.warning(self, "Need 4 Points", "Please click exactly 4 points on each image")
            return

        src = np.array(src_points, dtype=np.float32)
        dst = np.array(dst_points, dtype=np.float32)

        H, _ = cv2.findHomography(src, dst)
        if H is None:
            QMessageBox.warning(self, "Calibration Failed", "cv2.findHomography returned None")
            return

        self.H = H
        self.status_label.setText("Status: Calibration successful")
        self.preview_label.setText("Preview: Homography matrix computed")
        print("\n========== CALIBRATION RESULT ==========")
        print("Source points:", src_points)
        print("Target points:", dst_points)
        print("Homography:\n", self.H)
        print("========================================\n")

    def preview_mapping(self):
        if self.H is None:
            QMessageBox.warning(self, "No Calibration", "Please calibrate first")
            return

        if not self.source_label.has_image() or not self.target_label.has_image():
            QMessageBox.warning(self, "No Images", "Need both source and target images")
            return

        src_points = self.source_label.get_image_points()
        if len(src_points) < 4:
            QMessageBox.warning(self, "Need Points", "Please click 4 source points first")
            return

        pts = np.array([[list(p)] for p in src_points], dtype=np.float32)
        mapped = cv2.perspectiveTransform(pts, self.H)

        mapped_list = [(float(p[0][0]), float(p[0][1])) for p in mapped]
        self.preview_label.setText(f"Preview mapped points: {mapped_list}")
        print("\n========== PREVIEW MAPPED POINTS ==========")
        print(mapped_list)
        print("===========================================\n")

    def save_calibration(self):
        if self.H is None:
            QMessageBox.warning(self, "No Calibration", "Please calibrate first")
            return

        save_dir = os.path.dirname(self.calibration_save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)

        data = {
            "version": 1,
            "source_image_path": self.source_image_path,
            "source_points": self.source_label.get_image_points(),
            "target_points": self.target_label.get_image_points(),
            "homography": self.H.tolist(),
        }

        try:
            with open(self.calibration_save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.status_label.setText(f"Status: Saved -> {self.calibration_save_path}")
            QMessageBox.information(self, "Saved", f"Calibration saved:\n{self.calibration_save_path}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def load_calibration(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Calibration",
            os.path.dirname(self.calibration_save_path) or ".",
            "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            H = np.array(data["homography"], dtype=np.float32)
            self.H = H

            self.source_label.clear_points()
            self.target_label.clear_points()

            for p in data.get("source_points", []):
                self.source_label.image_points.append((float(p[0]), float(p[1])))
            for p in data.get("target_points", []):
                self.target_label.image_points.append((float(p[0]), float(p[1])))

            self.source_label._refresh_scaled_pixmap()
            self.target_label._refresh_scaled_pixmap()
            self._on_points_changed()

            self.status_label.setText(f"Status: Loaded -> {path}")
            self.preview_label.setText("Preview: Loaded calibration matrix")
        except Exception as e:
            QMessageBox.critical(self, "Load Failed", str(e))

    @staticmethod
    def map_bbox_with_homography(bbox: Tuple[float, float, float, float], H: np.ndarray) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = bbox[:4]

        corners = np.array([
            [[x1, y1]],
            [[x2, y1]],
            [[x2, y2]],
            [[x1, y2]],
        ], dtype=np.float32)

        mapped = cv2.perspectiveTransform(corners, H)
        xs = mapped[:, 0, 0]
        ys = mapped[:, 0, 1]

        nx1 = int(round(xs.min()))
        ny1 = int(round(ys.min()))
        nx2 = int(round(xs.max()))
        ny2 = int(round(ys.max()))
        return (nx1, ny1, nx2, ny2)

    @staticmethod
    def load_homography_from_file(path: str) -> Optional[np.ndarray]:
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return np.array(data["homography"], dtype=np.float32)
        except Exception as e:
            print(f"❌ Failed to load homography: {e}")
            return None