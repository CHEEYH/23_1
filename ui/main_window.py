# ui/main_window.py
from PySide6.QtWidgets import QMainWindow, QStackedWidget
from PySide6.QtCore import Qt
import time
import socket
from socket import SHUT_RDWR

from .components import AssemblyDialog
from .components.heartbeat_manager import HeartbeatManager
from .pages import (
    MainPage, TechnicianLoginPage, TechnicianPage,
    RecipeMenuPage, CreateRecipePage, EditFlowPage, DeepLearningPage
)

# ========== ADD THIS IMPORT ==========
from camera.orbbec_camera_thread import OrbbecCameraThread


# =====================================


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Assembly System")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.showFullScreen()
        self.current_recipe_folder = None

        self.history = []
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # 创建页面实例
        self.main_page = MainPage(self)
        self.login_page = TechnicianLoginPage(self)
        self.tech_page = TechnicianPage(self)
        self.recipe_menu_page = RecipeMenuPage(self)
        self.create_recipe_page = CreateRecipePage(self)
        self.edit_flow_page = EditFlowPage(self)
        self.deep_learning_page = DeepLearningPage(self)

        # 添加到堆栈
        pages = [
            self.main_page,
            self.login_page,
            self.tech_page,
            self.recipe_menu_page,
            self.create_recipe_page,
            self.edit_flow_page,
            self.deep_learning_page
        ]

        for page in pages:
            self.stack.addWidget(page)

        # ========== ADD ORBBEC THREAD SETUP ==========
        self.orbbec_thread = None
        self._setup_orbbec_thread()
        # ============================================

        # 显示主页面
        self.stack.setCurrentWidget(self.main_page)

    # ========== ADD THIS NEW METHOD ==========
    def _setup_orbbec_thread(self):
        """Setup and start Orbbec camera thread for hand gesture detection"""
        print("\n" + "=" * 60)
        print("🔧 Setting up Orbbec Camera Thread")
        print("=" * 60)

        try:
            # Create Orbbec thread
            self.orbbec_thread = OrbbecCameraThread()

            # Connect to main page for pipeline trigger
            if hasattr(self, 'main_page') and self.main_page:
                self.main_page.connect_orbbec_trigger(self.orbbec_thread)
                print("✅ Connected Orbbec thread to MainPage")
            else:
                print("⚠️ MainPage not ready yet")

            # Connect status signals for debugging
            self.orbbec_thread.status_signal.connect(self._on_orbbec_status)
            self.orbbec_thread.error_signal.connect(self._on_orbbec_error)
            self.orbbec_thread.frame_signal.connect(self._on_orbbec_frame)

            # Start the thread
            self.orbbec_thread.start()
            print("✅ Orbbec thread started successfully")

        except Exception as e:
            print(f"❌ Failed to setup Orbbec thread: {e}")
            import traceback
            traceback.print_exc()
            self.orbbec_thread = None

    def _on_orbbec_status(self, message):
        """Handle Orbbec status messages"""
        print(f"[Orbbec] {message}")

    def _on_orbbec_error(self, error):
        """Handle Orbbec error messages"""
        print(f"[Orbbec ERROR] {error}")

    def _on_orbbec_frame(self, frame):
        """Handle Orbbec frame (optional - for debugging)"""
        # You can add frame display logic here if needed
        pass

    # =========================================

    def go_to(self, w):
        """跳转到指定页面"""
        print(f"Navigating to: {w}")
        self.history.append(self.stack.currentWidget())

        # If going to deep learning page, refresh its recipe info
        if w == self.deep_learning_page:
            print("Target is deep learning page - scheduling refresh")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.deep_learning_page.refresh_recipe_info)

        self.stack.setCurrentWidget(w)

    def go_back(self):
        """Go back to previous page - with proper TCP disconnect"""
        print("\n" + "=" * 80)
        print("🔍 DEBUG: MainWindow.go_back() called - Cleaning up ALL TCP connections")
        print("=" * 80)

        # ===== CLEANUP METHOD 1: Clean up Heartbeat Manager =====
        print("\n📡 Checking Heartbeat Manager...")
        if hasattr(AssemblyDialog, '_heartbeat_manager') and AssemblyDialog._heartbeat_manager:
            print("  Found Heartbeat Manager - disconnecting...")

            # Disconnect all signals first to prevent callbacks
            try:
                AssemblyDialog._heartbeat_manager.connection_status_changed.disconnect()
                print("  ✅ Heartbeat signals disconnected")
            except:
                print("  ⚠️ No heartbeat signals to disconnect")
                pass

            # Force disconnect
            AssemblyDialog._heartbeat_manager.disconnect()

            # Set to None
            AssemblyDialog._heartbeat_manager = None
            print("  ✅ Heartbeat Manager cleared")
        else:
            print("  ℹ️ No Heartbeat Manager active")

        # Reset reference count
        AssemblyDialog._heartbeat_reference_count = 0
        print(f"  ✅ Heartbeat reference count reset to {AssemblyDialog._heartbeat_reference_count}")

        # ===== CLEANUP METHOD 2: Clean up Global Socket =====
        print("\n📡 Checking Global Socket...")
        if hasattr(AssemblyDialog, '_global_tcp_socket') and AssemblyDialog._global_tcp_socket:
            try:
                sock = AssemblyDialog._global_tcp_socket
                print(f"  Found global socket: {sock}")

                # Send disconnect message
                try:
                    sock.send(b"DISCONNECT|main_window_close\n")
                    print("  📤 Sent DISCONNECT message to server")
                    time.sleep(0.1)
                except Exception as e:
                    print(f"  ⚠️ Could not send disconnect message: {e}")

                # Shutdown and close
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                    print("  ✅ shutdown() successful")
                except Exception as e:
                    print(f"  ⚠️ shutdown() failed: {e}")

                try:
                    sock.close()
                    print("  ✅ close() successful")
                except Exception as e:
                    print(f"  ⚠️ close() failed: {e}")

            except Exception as e:
                print(f"  ⚠️ Error during socket cleanup: {e}")
            finally:
                AssemblyDialog._global_tcp_socket = None
                print("  ✅ Global socket reference cleared")
        else:
            print("  ℹ️ No global socket active")

        # ===== CLEANUP METHOD 3: Check for any lingering sockets =====
        print("\n🔍 Checking for any lingering socket connections...")

        # Try to connect to the same port to see if it's still in use
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(1)
            # Try to connect - if it succeeds immediately, port might still be in use
            result = test_sock.connect_ex(('127.0.0.1', 8888))
            if result == 0:
                print("  ⚠️ WARNING: Port 8888 is still accepting connections!")
                test_sock.close()
            else:
                print("  ✅ Port 8888 is free (connection refused)")
                test_sock.close()
        except Exception as e:
            print(f"  ℹ️ Port check result: {e}")

        print("\n" + "=" * 80)
        print("✅ TCP CLEANUP COMPLETE - Ready to navigate back")
        print("=" * 80 + "\n")

        # ===== NAVIGATION =====
        if self.history:
            previous_page = self.history.pop()
            self.stack.setCurrentWidget(previous_page)

            # If we're going back to EditFlowPage, update its TCP status
            if isinstance(previous_page, EditFlowPage):
                previous_page._update_tcp_status_from_heartbeat()
        else:
            self.stack.setCurrentWidget(self.main_page)

    # ========== ADD CLEANUP ON CLOSE ==========
    def closeEvent(self, event):
        """Clean up Orbbec thread when window closes"""
        print("\n🔧 Closing MainWindow - cleaning up Orbbec thread...")

        if self.orbbec_thread is not None:
            try:
                self.orbbec_thread.stop()
                self.orbbec_thread.wait(2000)
                print("✅ Orbbec thread stopped")
            except Exception as e:
                print(f"⚠️ Error stopping Orbbec thread: {e}")

        super().closeEvent(event)
    # =========================================