# ui/pages/technician_page.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from ..components.buttons import create_button, SPACING, TITLE_FONT
from camera import CameraThread
from config_manager import config_manager
from camera.camera_setting import MainWindow as CameraSettingWindow

# Import the laser calibration tool
import sys
import os

# Add the project root to path to find laser_camera_calibrate.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from laser_camera_calibrate import MainWindow as CalibrationWindow

    LASER_CALIBRATION_AVAILABLE = True
except ImportError:
    LASER_CALIBRATION_AVAILABLE = False
    print("Warning: laser_camera_calibrate.py not found. Laser calibration button will be disabled.")


class TechnicianPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.cam = None
        self.camera_settings_window = None
        self.calibration_window = None  # Add reference for calibration window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(SPACING)
        layout.addSpacing(30)

        title = QLabel("👨‍🔧 TECHNICIAN")
        title.setStyleSheet(f"font-size:{TITLE_FONT}px;font-weight:600;color:#4b5563;")
        layout.addWidget(title)

        # # Video display area
        # self.video = QLabel()
        # self.video.setFixedSize(560, 420)
        # self.video.setStyleSheet("background:black;border:2px solid #ccc;border-radius:8px;")
        # self.video.setAlignment(Qt.AlignCenter)
        # self.video.setText("Camera Off")
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
        # layout.addWidget(self.video)
        layout.addSpacing(150)
        # Buttons - ADD THE LASER CALIBRATION BUTTON HERE
        buttons = [
            # ("📷 Camera ON / OFF", "#33CCFF", self.toggle_camera),
            ("⚙️ Camera Settings", "#666666", self.open_camera_settings),
        ]

        # Only add laser calibration button if available
        if LASER_CALIBRATION_AVAILABLE:
            buttons.append(("🎯 Laser Calibration", "#FF9900", self.open_laser_calibration))

        # Add remaining buttons
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

            # Create new camera settings window (will create its own connection)
            self.camera_settings_window = CameraSettingWindow()

            # Set window modality to prevent interaction with main window
            self.camera_settings_window.setWindowModality(Qt.ApplicationModal)

            # Set window title
            self.camera_settings_window.setWindowTitle("Camera Settings")

            # Connect close event to cleanup
            self.camera_settings_window.destroyed.connect(self.on_camera_settings_closed)

            # Show the window
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
            # Check if calibration window already exists
            if self.calibration_window is not None:
                # If it exists, just bring it to front
                self.calibration_window.raise_()
                self.calibration_window.activateWindow()
                return

            # Create new calibration window
            self.calibration_window = CalibrationWindow()

            # Set window modality (optional - remove if you want to interact with both windows)
            # self.calibration_window.setWindowModality(Qt.ApplicationModal)

            # Set window title
            self.calibration_window.setWindowTitle("Laser Camera Calibration")

            # Connect close event to cleanup
            self.calibration_window.destroyed.connect(self.on_calibration_closed)

            # Show the window
            self.calibration_window.show()

            print("✅ Laser calibration window opened")

        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Failed to open laser calibration: {str(e)}")
            import traceback
            traceback.print_exc()

    def on_calibration_closed(self):
        """Handle calibration window closing"""
        self.calibration_window = None
        print("Laser calibration window closed")

    def go_to_deep_learning(self):
        """Go to Deep Learning page after selecting recipe"""
        recipes = config_manager.get_available_recipes()

        if not recipes:
            QMessageBox.warning(self, "⚠️ No Recipes",
                                "No recipes found! Please create a recipe first.")
            # Automatically go to Recipe Menu page
            self.main.go_to(self.main.recipe_menu_page)
            return

        # Let user select recipe to train
        recipe, ok = QInputDialog.getItem(
            self,
            "🔍 Select Recipe for Deep Learning",
            "Choose a recipe to train:",
            recipes,
            0,
            False
        )

        if ok and recipe:
            # Set current recipe
            config_manager.set_current_recipe(recipe)
            print(f"✅ Selected recipe for Deep Learning: {recipe}")

            # Go to Deep Learning page
            self.main.go_to(self.main.deep_learning_page)