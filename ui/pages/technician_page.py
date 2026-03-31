# ui/pages/technician_page.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ui.components.buttons import create_button, SPACING, TITLE_FONT
from camera import CameraThread
from config_manager import config_manager
from camera.camera_setting import MainWindow as CameraSettingWindow

import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import laser calibration tool
try:
    from laser_camera_calibrate import MainWindow as CalibrationWindow
    LASER_CALIBRATION_AVAILABLE = True
except ImportError:
    LASER_CALIBRATION_AVAILABLE = False
    print("Warning: laser_camera_calibrate.py not found. Laser calibration button will be disabled.")

# Import Orbbec calibration page
try:
    from ui.components.calibration import Calibration
    ORBBEC_CALIBRATION_AVAILABLE = True
except ImportError:
    ORBBEC_CALIBRATION_AVAILABLE = False
    print("Warning: ui.components.calibration not found. Calibration button will be disabled.")

# Import Orbbec thread
try:
    from camera.orbbec_camera_thread import OrbbecCameraThread
    ORBBEC_THREAD_AVAILABLE = True
except ImportError:
    ORBBEC_THREAD_AVAILABLE = False
    print("Warning: camera.orbbec_camera_thread not found. Calibration live capture will be disabled.")


class TechnicianPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.cam = None

        self.camera_settings_window = None
        self.calibration_window = None            # laser calibration window
        self.orbbec_calibration_window = None     # orbbec calibration page
        self.orbbec_thread = None                 # live orbbec thread for calibration page

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(SPACING)
        layout.addSpacing(30)

        title = QLabel("👨‍🔧 TECHNICIAN")
        title.setStyleSheet(f"font-size:{TITLE_FONT}px;font-weight:600;color:#4b5563;")
        layout.addWidget(title)

        # Optional video display area (currently unused)
        # self.video = QLabel()
        # self.video.setFixedSize(560, 420)
        # self.video.setStyleSheet("""
        #     QLabel {
        #         background:black;
        #         border:2px solid #ccc;
        #         border-radius:8px;
        #         color:white;
        #         font-size:20px;
        #         font-weight:bold;
        #     }
        # """)
        # self.video.setAlignment(Qt.AlignCenter)
        # self.video.setText("Camera Off")
        # layout.addWidget(self.video)

        layout.addSpacing(150)

        buttons = [
            # ("📷 Camera ON / OFF", "#33CCFF", self.toggle_camera),
            ("⚙️ Camera Settings", "#666666", self.open_camera_settings),
        ]

        if LASER_CALIBRATION_AVAILABLE:
            buttons.append(("🎯 Laser Calibration", "#FF9900", self.open_laser_calibration))

        if ORBBEC_CALIBRATION_AVAILABLE:
            buttons.append(("📐 Calibration", "#00AAFF", self.open_orbbec_calibration))

        buttons.extend([
            ("📋 Recipe Menu", "#3399FF", lambda: self.main.go_to(self.main.recipe_menu_page)),
            ("📝 Edit Flow", "#FFCC00", lambda: self.main.go_to(self.main.edit_flow_page)),
            ("🤖 Deep Learning", "#8B5CF6", self.go_to_deep_learning),
            ("🚪 Logout", "#FF3333", self.main.go_back),
        ])

        for b in buttons:
            layout.addWidget(create_button(*b))

        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(QWidget())
        QVBoxLayout(scroll.widget()).addLayout(layout)

        QVBoxLayout(self).addWidget(scroll)

    def toggle_camera(self):
        if not self.cam:
            self.cam = CameraThread()
            self.cam.frame_ready.connect(self.update_image)
            self.cam.start()
        else:
            self.cam.stop()
            self.cam = None
            self.video.clear()
            self.video.setText("Camera Off")

    def update_image(self, img):
        h, w, ch = img.shape
        qimg = QImage(img.data, w, h, ch * w, QImage.Format_BGR888)
        self.video.setPixmap(QPixmap.fromImage(qimg).scaled(self.video.size(), Qt.KeepAspectRatio))

    def open_camera_settings(self):
        """Open the camera settings window"""
        try:
            from camera.camera_setting import MainWindow as CameraSettingWindow

            self.camera_settings_window = CameraSettingWindow()
            self.camera_settings_window.setWindowModality(Qt.ApplicationModal)
            self.camera_settings_window.setWindowTitle("Camera Settings")
            self.camera_settings_window.destroyed.connect(self.on_camera_settings_closed)
            self.camera_settings_window.show()

            print("✅ Camera settings window opened")

        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Failed to open camera settings: {str(e)}")

    def on_camera_settings_closed(self):
        """Handle camera settings window closing"""
        self.camera_settings_window = None
        print("Camera settings window closed")

    def open_laser_calibration(self):
        """Open the laser camera calibration tool"""
        try:
            if self.calibration_window is not None:
                self.calibration_window.raise_()
                self.calibration_window.activateWindow()
                return

            self.calibration_window = CalibrationWindow()
            self.calibration_window.setWindowTitle("Laser Camera Calibration")
            self.calibration_window.destroyed.connect(self.on_calibration_closed)
            self.calibration_window.show()

            print("✅ Laser calibration window opened")

        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Failed to open laser calibration: {str(e)}")
            import traceback
            traceback.print_exc()

    def on_calibration_closed(self):
        """Handle laser calibration window closing"""
        self.calibration_window = None
        print("Laser calibration window closed")

    def _ensure_orbbec_thread(self):
        """Create/start Orbbec thread if needed"""
        if not ORBBEC_THREAD_AVAILABLE:
            return False

        try:
            if self.orbbec_thread is not None and self.orbbec_thread.isRunning():
                return True

            self.orbbec_thread = OrbbecCameraThread()
            self.orbbec_thread.start()
            print("✅ Orbbec thread started for calibration")
            return True

        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Failed to start Orbbec thread: {str(e)}")
            import traceback
            traceback.print_exc()
            self.orbbec_thread = None
            return False

    def open_orbbec_calibration(self):
        """Open the Orbbec calibration page"""
        try:
            if self.orbbec_calibration_window is not None:
                self.orbbec_calibration_window.raise_()
                self.orbbec_calibration_window.activateWindow()
                return

            current_recipe = config_manager.current_recipe
            if not current_recipe:
                QMessageBox.warning(
                    self,
                    "⚠️ No Recipe Selected",
                    "Please select a recipe first."
                )
                return

            if not self._ensure_orbbec_thread():
                QMessageBox.warning(
                    self,
                    "⚠️ Orbbec Unavailable",
                    "Orbbec thread could not be started.\nCalibration page will not open."
                )
                return

            self.orbbec_calibration_window = Calibration(
                source_image_path="",   # left side will auto-capture from source camera
                recipe_name=current_recipe,
                orbbec_thread=self.orbbec_thread,
                parent=self
            )

            self.orbbec_calibration_window.setWindowTitle("Orbbec Calibration")
            self.orbbec_calibration_window.destroyed.connect(self.on_orbbec_calibration_closed)
            self.orbbec_calibration_window.show()

            print("✅ Orbbec calibration page opened")

        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Failed to open Orbbec calibration: {str(e)}")
            import traceback
            traceback.print_exc()

    def on_orbbec_calibration_closed(self):
        """Handle Orbbec calibration window closing"""
        self.orbbec_calibration_window = None
        print("Orbbec calibration window closed")

    def go_to_deep_learning(self):
        """Go to Deep Learning page after selecting recipe"""
        recipes = config_manager.get_available_recipes()

        if not recipes:
            QMessageBox.warning(
                self,
                "⚠️ No Recipes",
                "No recipes found! Please create a recipe first."
            )
            self.main.go_to(self.main.recipe_menu_page)
            return

        recipe, ok = QInputDialog.getItem(
            self,
            "🔍 Select Recipe for Deep Learning",
            "Choose a recipe to train:",
            recipes,
            0,
            False
        )

        if ok and recipe:
            config_manager.set_current_recipe(recipe)
            print(f"✅ Selected recipe for Deep Learning: {recipe}")
            self.main.go_to(self.main.deep_learning_page)

    def closeEvent(self, event):
        """Cleanup threads/windows when page is closed"""
        try:
            if self.cam:
                self.cam.stop()
                self.cam = None
        except Exception:
            pass

        try:
            if self.orbbec_thread is not None:
                try:
                    self.orbbec_thread.stop()
                except Exception:
                    pass
                self.orbbec_thread = None
        except Exception:
            pass

        super().closeEvent(event)