import sys
import threading
import time
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# Import modules
import Scanner
import sudong_backend_clean


def start_tcp_server():
    """Start Scanner's TCP server."""
    try:
        server = Scanner.TCPServer()
        server.start()
        print("[MAIN] Scanner TCPServer started")
    except Exception as e:
        print(f"[MAIN] Error starting TCPServer: {e}")


def start_sudong_backend():
    """Start Sudong backend safely."""
    try:
        print("[MAIN] Starting Sudong backend...")

        if hasattr(sudong_backend_clean, "main"):
            sudong_backend_clean.main()
            print("[MAIN] Sudong backend main() started")
        else:
            print("[MAIN] sudong_backend_clean.main() not found")

    except Exception as e:
        print(f"[MAIN] Error starting Sudong backend: {e}")


def cleanup():
    """Cleanup backend workers on app exit."""
    print("[MAIN] Cleaning up...")

    if hasattr(sudong_backend_clean, "live_worker"):
        try:
            sudong_backend_clean.live_worker.stop()
            print("[MAIN] live_worker stopped")
        except Exception as e:
            print(f"[MAIN] Error stopping live_worker: {e}")

    if hasattr(sudong_backend_clean, "selector_worker"):
        try:
            sudong_backend_clean.selector_worker.stop()
            print("[MAIN] selector_worker stopped")
        except Exception as e:
            print(f"[MAIN] Error stopping selector_worker: {e}")

    print("[MAIN] Cleanup complete")


def main():
    # Create Qt application first
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f9fafb;
        }
        QLabel {
            color: #4b5563;
        }
        QLineEdit {
            border: 2px solid #d1d5db;
            border-radius: 6px;
            padding: 8px;
            font-size: 14px;
        }
        QLineEdit:focus {
            border-color: #3b82f6;
        }
        QMessageBox {
            background-color: white;
        }
    """)

    # Start Scanner TCPServer in background thread
    scanner_thread = threading.Thread(
        target=start_tcp_server,
        daemon=True
    )
    scanner_thread.start()

    # Start Sudong backend in background thread
    sudong_thread = threading.Thread(
        target=start_sudong_backend,
        daemon=True
    )
    sudong_thread.start()

    # Give threads a moment to initialize
    time.sleep(0.5)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Cleanup on exit
    app.aboutToQuit.connect(cleanup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()