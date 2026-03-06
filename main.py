# main.py
import sys
import threading
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# Import Scanner as a module
import Scanner


def start_tcp_server():
    try:
        # Start the TCP server
        server = Scanner.TCPServer()
        server.start()
    except Exception as e:
        print(f"Error starting TCPServer: {e}")


def main():

    app = QApplication(sys.argv)

    # 设置应用样式
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

    # Start TCPServer in a background thread
    server_thread = threading.Thread(target=start_tcp_server, daemon=True)
    server_thread.start()

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()