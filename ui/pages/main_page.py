# ui/pages/main_page.py
import json
import socket
import os
from datetime import datetime
from typing import Dict, List, Optional

import requests
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QFrame, QGridLayout, QScrollArea,
    QSizePolicy, QApplication, QDialog, QTextEdit
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor

from config_manager import config_manager
from ui.components.pipeline_runner import PipelineRunner
from ui.components.mes_client import MESClient


class QRCheckWorker(QThread):
    message_received = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    finished_scan = Signal()

    def __init__(self, host="127.0.0.1", port=1220, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.running = True
        self.sock = None

    def run(self):
        try:
            self.status_changed.emit(f"Connecting to {self.host}:{self.port} ...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))

            self.status_changed.emit("Connected, sending check ...")
            self.sock.sendall(b"check\n")

            self.sock.settimeout(0.2)

            while self.running:
                try:
                    data = self.sock.recv(1024)
                    if not data:
                        break

                    text = data.decode("utf-8", errors="ignore").strip()
                    if text:
                        self.message_received.emit(text)

                except socket.timeout:
                    continue
                except Exception as e:
                    self.error_occurred.emit(f"Socket read failed: {e}")
                    break

        except Exception as e:
            self.error_occurred.emit(f"Connection failed: {e}")

        finally:
            self.cleanup()
            self.finished_scan.emit()

    def stop_scan(self):
        self.running = False
        try:
            if self.sock:
                self.sock.sendall(b"ok\n")
        except:
            pass

    def cleanup(self):
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        self.sock = None


class QRScanDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR Check")
        self.setMinimumSize(520, 320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.title_label = QLabel("Please scan the QR Code")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #0f172a;")
        layout.addWidget(self.title_label)

        self.status_label = QLabel("Waiting to start...")
        self.status_label.setStyleSheet("color: #475569; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setPlaceholderText("Scanner return messages will be shown here...")
        self.result_box.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.result_box)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.confirm_btn = QPushButton("Confirm")
        self.confirm_btn.setFixedHeight(34)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        button_layout.addWidget(self.confirm_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedHeight(34)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)


class MainPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.mes = MESClient()
        self.pending_jobs = []
        self.current_recipe = None
        self.current_job_title = None
        self.current_job_details = None
        self.mes_recipe_override = False
        self.waiting_for_mes = True
        self.last_valid_mes_time = None
        self.mes_outage_start = None
        self.pipeline_running = False
        self.pending_run_after_qr = False

        self.has_active_mes_job = False

        self.qr_worker = None
        self.qr_dialog = None
        self.last_qr_job_id = None
        self.qr_check_passed = False
        self.qr_result_ok = False

        self.time_timer = QTimer()
        self.mes_recipe_timer = QTimer()
        self.spinner_timer = QTimer()

        self.init_ui()
        self.init_timers()
        self.start_spinner()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        header_container = QFrame()
        header_container.setFixedHeight(70)
        header_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:1 #7c3aed);
                border-radius: 12px;
                padding: 2px;
            }
        """)
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("🏭 ASSEMBLY SYSTEM DASHBOARD")
        header.setFont(QFont("Inter", 20, QFont.Bold))
        header.setStyleSheet("""
            QLabel {
                color: white;
                padding: 8px;
                background: transparent;
                border-radius: 10px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(header)
        layout.addWidget(header_container)

        status_frame = QFrame()
        status_frame.setFixedHeight(45)
        status_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 10px;
                padding: 4px 12px;
                border: 1px solid #e2e8f0;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 4, 12, 4)
        status_layout.setSpacing(8)

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #f59e0b; font-size: 16px;")

        self.machine_status = QLabel("WAITING FOR MES...")
        self.machine_status.setFont(QFont("Inter", 11, QFont.Bold))
        self.machine_status.setStyleSheet("color: #b45309;")

        status_layout.addWidget(self.status_indicator)
        status_layout.addWidget(self.machine_status)
        status_layout.addStretch()

        self.mes_status_label = QLabel("🔌 MES: Waiting for recipe...")
        self.mes_status_label.setFont(QFont("Inter", 10))
        self.mes_status_label.setStyleSheet("""
            QLabel {
                color: #f59e0b;
                padding: 4px 8px;
                background-color: #fffbeb;
                border-radius: 12px;
                border: 1px solid #fcd34d;
            }
        """)
        status_layout.addWidget(self.mes_status_label)

        clock_icon = QLabel("🕐")
        clock_icon.setStyleSheet("font-size: 14px; color: #64748b;")

        self.time_label = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.time_label.setFont(QFont("Inter", 10))
        self.time_label.setStyleSheet("color: #475569;")

        status_layout.addWidget(clock_icon)
        status_layout.addWidget(self.time_label)

        layout.addWidget(status_frame)

        self.waiting_card = QFrame()
        self.waiting_card.setFixedHeight(250)
        self.waiting_card.setStyleSheet("""
            QFrame {
                background-color: #fffbeb;
                border-radius: 12px;
                padding: 20px;
                border: 2px solid #fbbf24;
            }
        """)
        waiting_layout = QVBoxLayout(self.waiting_card)
        waiting_layout.setSpacing(15)
        waiting_layout.setAlignment(Qt.AlignCenter)

        self.waiting_title = QLabel("Waiting for MES Recipe")
        self.waiting_title.setFont(QFont("Inter", 16, QFont.Bold))
        self.waiting_title.setStyleSheet("color: #92400e;")
        self.waiting_title.setAlignment(Qt.AlignCenter)
        waiting_layout.addWidget(self.waiting_title)

        self.spinner_label = QLabel("● ○ ○")
        self.spinner_label.setFont(QFont("Inter", 14))
        self.spinner_label.setStyleSheet("color: #f59e0b;")
        self.spinner_label.setAlignment(Qt.AlignCenter)
        waiting_layout.addWidget(self.spinner_label)

        layout.addWidget(self.waiting_card)

        self.recipe_card = QFrame()
        self.recipe_card.setFixedHeight(200)
        self.recipe_card.setVisible(False)
        self.recipe_card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                padding: 12px;
                border: 1px solid #e2e8f0;
            }
        """)

        recipe_layout = QVBoxLayout(self.recipe_card)
        recipe_layout.setSpacing(8)
        recipe_layout.setContentsMargins(12, 12, 12, 12)

        recipe_header_layout = QHBoxLayout()
        recipe_header_layout.setSpacing(4)

        recipe_icon = QLabel("📋")
        recipe_icon.setStyleSheet("font-size: 18px;")

        recipe_header = QLabel("Recipe Selection")
        recipe_header.setFont(QFont("Inter", 14, QFont.Bold))
        recipe_header.setStyleSheet("color: #0f172a;")

        recipe_header_layout.addWidget(recipe_icon)
        recipe_header_layout.addWidget(recipe_header)
        recipe_header_layout.addStretch()
        recipe_layout.addLayout(recipe_header_layout)

        selection_layout = QHBoxLayout()
        selection_layout.setSpacing(8)

        self.recipe_combo = QComboBox()
        self.recipe_combo.setFixedHeight(36)
        self.recipe_combo.setEnabled(False)
        self.recipe_combo.setStyleSheet("""
            QComboBox {
                font-size: 12px;
                padding: 6px 12px;
                padding-right: 28px;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                background-color: #f8fafc;
                min-width: 250px;
                color: #0f172a;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #94a3b8;
                background-color: #f1f5f9;
            }
            QComboBox:focus {
                border-color: #3b82f6;
                background-color: white;
            }
            QComboBox:disabled {
                background-color: #e2e8f0;
                border-color: #cbd5e1;
                color: #64748b;
            }
            QComboBox::drop-down {
                width: 24px;
                border: none;
            }
            QComboBox:disabled::drop-down {
                image: none;
            }
            QComboBox::down-arrow {
                width: 10px;
                height: 10px;
            }
            QComboBox QListView {
                font-size: 12px;
                background-color: white;
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 4px;
            }
            QComboBox QListView::item {
                height: 28px;
                padding: 4px 8px;
                border-radius: 4px;
                color: #0f172a;
            }
        """)
        self.recipe_combo.currentTextChanged.connect(self.on_recipe_changed)
        selection_layout.addWidget(self.recipe_combo)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(36, 36)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                font-weight: bold;
                border-radius: 8px;
                font-size: 16px;
                border: 2px solid #e2e8f0;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                color: #0f172a;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background-color: #cbd5e1;
            }
            QPushButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
                border-color: #e2e8f0;
            }
        """)
        self.refresh_btn.setToolTip("Refresh recipe list")
        self.refresh_btn.clicked.connect(self.refresh_recipes)
        selection_layout.addWidget(self.refresh_btn)

        selection_layout.addStretch()
        recipe_layout.addLayout(selection_layout)

        self.pipeline_info_label = QLabel("Waiting for MES recipe...")
        self.pipeline_info_label.setFont(QFont("Inter", 11))
        self.pipeline_info_label.setStyleSheet("""
            QLabel {
                color: #64748b;
                background: #f8fafc;
                padding: 8px;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
                line-height: 1.4;
            }
        """)
        self.pipeline_info_label.setWordWrap(True)
        recipe_layout.addWidget(self.pipeline_info_label)

        layout.addWidget(self.recipe_card)

        pending_card = QFrame()
        pending_card.setFixedHeight(350)
        pending_card.setStyleSheet("""
            QFrame {
                background-color: #fffbeb;
                border-radius: 12px;
                padding: 12px;
                border: 2px solid #fbbf24;
            }
        """)
        pending_layout = QVBoxLayout(pending_card)
        pending_layout.setSpacing(4)
        pending_layout.setContentsMargins(8, 8, 8, 4)

        pending_header = QHBoxLayout()
        pending_header.setSpacing(5)

        pending_icon = QLabel("⏳")
        pending_icon.setStyleSheet("font-size: 16px;")

        pending_title = QLabel("Pending Jobs")
        pending_title.setFont(QFont("Inter", 12, QFont.Bold))
        pending_title.setStyleSheet("color: #92400e;")

        self.pending_count = QLabel("0")
        self.pending_count.setFont(QFont("Inter", 9, QFont.Bold))
        self.pending_count.setStyleSheet("""
            color: white;
            background-color: #ef4444;
            padding: 4px 12px;
            border-radius: 16px;
            font-weight: bold;
        """)
        self.pending_count.setAlignment(Qt.AlignCenter)

        pending_header.addWidget(pending_icon)
        pending_header.addWidget(pending_title)
        pending_header.addStretch()
        pending_header.addWidget(self.pending_count)

        pending_layout.addLayout(pending_header)

        scroll_container = QFrame()
        scroll_container.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #fcd34d;
            }
        """)
        scroll_layout = QVBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        self.pending_widget = QWidget()
        self.pending_widget.setStyleSheet("background-color: transparent;")
        self.pending_layout = QVBoxLayout(self.pending_widget)
        self.pending_layout.setSpacing(4)
        self.pending_layout.setContentsMargins(2, 2, 2, 2)
        self.pending_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.pending_widget)
        scroll.setMinimumHeight(100)
        scroll.setMaximumHeight(200)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #f1f5f9;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #94a3b8;
                border-radius: 3px;
                min-height: 20px;
            }
        """)

        scroll_layout.addWidget(scroll)
        pending_layout.addWidget(scroll_container)

        layout.addWidget(pending_card)

        actions_label = QLabel("Quick Actions")
        actions_label.setFont(QFont("Inter", 14, QFont.Bold))
        actions_label.setStyleSheet("color: #0f172a; margin-top: 4px;")
        layout.addWidget(actions_label)

        actions_grid = QGridLayout()
        actions_grid.setSpacing(10)

        action_buttons = [
            ("👨‍🔧 Technician Login", "#f97316", self.open_technician, "Access technician panel"),
            ("▶ Start", "#10b981", self.run_pipeline, "Execute selected recipe"),
        ]

        for i, (text, color, callback, tooltip) in enumerate(action_buttons):
            btn = QPushButton(text)
            btn.setFixedHeight(100)
            btn.setFont(QFont("Inter", 12, QFont.Bold))
            btn.setToolTip(tooltip)

            if text == "▶ Run Pipeline":
                self.run_button = btn
                btn.setEnabled(False)

            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border-radius: 8px;
                    padding: 8px 16px;
                    border: none;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {self.darken_color(color)};
                }}
                QPushButton:pressed {{
                    background-color: {self.darken_color(color, 0.8)};
                }}
                QPushButton:disabled {{
                    background-color: #cbd5e1;
                    color: #94a3b8;
                }}
            """)
            btn.clicked.connect(callback)
            actions_grid.addWidget(btn, 0, i)

        layout.addLayout(actions_grid)
        layout.addStretch()

        self.refresh_recipes()
        self.load_pending_jobs()

    def init_timers(self):
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(300)

        self.spinner_timer.timeout.connect(self.animate_spinner)
        self.spinner_timer.start(500)

        self.mes_recipe_timer.timeout.connect(self.try_fetch_mes_recipe)
        self.mes_recipe_timer.start(5000)

    def animate_spinner(self):
        if not self.waiting_for_mes:
            return

        frames = ["● ○ ○", "○ ● ○", "○ ○ ●", "○ ● ○"]
        current = getattr(self, '_spinner_frame', 0)
        self.spinner_label.setText(frames[current])
        self._spinner_frame = (current + 1) % len(frames)

    def start_spinner(self):
        self._spinner_frame = 0
        self.waiting_for_mes = True

    def fetch_mes_recipe_once(self, force=False):
        try:
            job_details = self.mes.get_job_details()
            print(f"DEBUG job_details from MES: {job_details}")

            mes_recipe = ""
            if job_details:
                mes_recipe = (job_details.get('recipe') or job_details.get('recipeName') or "").strip()

            if job_details and mes_recipe:
                available_recipes = config_manager.get_available_recipes()
                print(f"DEBUG MES recipe received: [{mes_recipe}]")
                print(f"DEBUG Available recipes: {available_recipes}")

                if mes_recipe in available_recipes:
                    new_job_title = job_details.get('title') or job_details.get('workOrder') or 'Unknown'
                    print(f"🔄 Refreshing MES job: Recipe={mes_recipe}, Job={new_job_title}")

                    self.force_ui_update(mes_recipe, job_details)
                    self.has_active_mes_job = True
                else:
                    print(f"⚠️ Recipe '{mes_recipe}' not found in local recipes")
            else:
                print("⚠️ MES did not return a valid job/recipe")
                self.has_active_mes_job = False

        except Exception as e:
            print(f"❌ MES error: {e}")
            import traceback
            traceback.print_exc()

    def try_fetch_mes_recipe(self):
        if self.pipeline_running:
            print("⏭️ Pipeline is running, skip MES refresh")
            return

        self.fetch_mes_recipe_once()

    def force_ui_update(self, recipe_name, job_details):
        job_title = job_details.get('title') or job_details.get('workOrder') or 'Unknown'
        print(f"🔄 FORCE UI UPDATE: Recipe={recipe_name}, Job={job_title}")

        self.current_recipe = recipe_name
        if config_manager.current_recipe != recipe_name:
            config_manager.set_current_recipe(recipe_name)

        self.current_job_details = job_details
        self.current_job_title = job_title
        self.waiting_for_mes = False
        self.mes_recipe_override = True
        self.has_active_mes_job = True

        self.waiting_card.setVisible(False)
        self.recipe_card.setVisible(True)

        self.refresh_recipes()

        prefixed_recipe = f"📦 {recipe_name}"
        index = self.recipe_combo.findText(prefixed_recipe)

        if index >= 0:
            self.recipe_combo.blockSignals(True)
            self.recipe_combo.setCurrentIndex(index)
            self.recipe_combo.blockSignals(False)

        new_status = f"READY - Recipe: {recipe_name} | Job: {job_title}"
        print(f"📝 Setting status to: {new_status}")

        self.machine_status.setText(new_status)
        self.machine_status.setStyleSheet("color: #059669;")

        self.mes_status_label.setText(
            f"🔌 MES: Job {job_title} | Recipe: {recipe_name}"
        )
        self.mes_status_label.setStyleSheet("""
            QLabel {
                color: #059669;
                padding: 4px 8px;
                background-color: #d1fae5;
                border-radius: 12px;
                border: 1px solid #a7f3d0;
            }
        """)

        self.status_indicator.setStyleSheet("color: #10b981; font-size: 16px;")

        if hasattr(self, 'run_button'):
            self.run_button.setEnabled(False)

        self.update_pipeline_info()
        self.load_pending_jobs()

        job_id = job_details.get('title') or job_details.get('workOrder') or 'Unknown'

        if self.last_qr_job_id != job_id:
            self.last_qr_job_id = job_id
            self.qr_check_passed = False
            self.qr_result_ok = False

        if hasattr(self, 'run_button'):
            self.run_button.setEnabled(True)

        self.machine_status.repaint()
        self.mes_status_label.repaint()
        self.status_indicator.repaint()
        self.recipe_combo.repaint()
        self.repaint()

        QApplication.processEvents()

        print(f"✅ UI Updated - Current status text: {self.machine_status.text()}")
        print(f"✅ Config current recipe: {config_manager.current_recipe}")

    def show_qr_check_popup(self):
        """Show QR check dialog and start TCP check"""
        if self.qr_dialog and self.qr_dialog.isVisible():
            return

        self.qr_result_ok = False

        self.qr_dialog = QRScanDialog(self)
        self.qr_dialog.status_label.setText("Waiting for QR scan...")
        self.qr_dialog.confirm_btn.setEnabled(False)

        self.qr_dialog.confirm_btn.clicked.connect(self.confirm_qr_scan)
        self.qr_dialog.cancel_btn.clicked.connect(self.cancel_qr_scan)

        self.qr_worker = QRCheckWorker(host="127.0.0.1", port=1220, parent=self)
        self.qr_worker.status_changed.connect(self.on_qr_status_changed)
        self.qr_worker.message_received.connect(self.on_qr_message_received)
        self.qr_worker.error_occurred.connect(self.on_qr_error)
        self.qr_worker.finished_scan.connect(self.on_qr_finished)
        self.qr_worker.start()

        self.qr_dialog.exec()

    def on_qr_status_changed(self, text):
        if self.qr_dialog:
            self.qr_dialog.status_label.setText(text)

    def on_qr_message_received(self, text):
        if self.qr_dialog:
            clean_text = text.strip()
            if not clean_text:
                return

            # Any scanned content is accepted
            self.qr_result_ok = True

            self.qr_dialog.status_label.setText("QR data received")
            self.qr_dialog.status_label.setStyleSheet(
                "color: #059669; font-weight: bold; font-size: 12px;"
            )
            self.qr_dialog.confirm_btn.setEnabled(True)

            self.qr_dialog.result_box.append(clean_text)

    def on_qr_error(self, text):
        if self.qr_dialog:
            self.qr_dialog.status_label.setText("An error occurred")
            self.qr_dialog.status_label.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 12px;")
            self.qr_dialog.result_box.append(f"[ERROR] {text}")

    def on_qr_finished(self):
        if self.qr_dialog:
            current = self.qr_dialog.status_label.text()
            if current not in ["QR data received", "An error occurred"]:
                self.qr_dialog.status_label.setText("Scan stopped")

    def confirm_qr_scan(self):
        """User confirms QR result"""
        if not self.qr_result_ok:
            QMessageBox.warning(
                self,
                "No QR Data",
                "No QR data received yet. Please scan first.",
                QMessageBox.Ok
            )
            return

        self.qr_check_passed = True

        if self.qr_dialog:
            self.qr_dialog.accept()
            self.qr_dialog.deleteLater()
            self.qr_dialog = None

        if hasattr(self, 'run_button'):
            self.run_button.setEnabled(True)

        if self.current_recipe and self.current_job_title:
            self.machine_status.setText(
                f"READY - Recipe: {self.current_recipe} | Job: {self.current_job_title}"
            )
        else:
            self.machine_status.setText("READY")

        QApplication.processEvents()

        if self.qr_worker:
            self.qr_worker.stop_scan()
            self.qr_worker.wait(300)
            self.qr_worker.deleteLater()
            self.qr_worker = None

        if self.pending_run_after_qr:
            self.pending_run_after_qr = False
            QTimer.singleShot(0, self.run_pipeline)

    def cancel_qr_scan(self):
        self.qr_check_passed = False
        self.qr_result_ok = False
        self.pending_run_after_qr = False

        if self.qr_dialog:
            self.qr_dialog.reject()
            self.qr_dialog.deleteLater()
            self.qr_dialog = None

        if hasattr(self, 'run_button'):
            self.run_button.setEnabled(True)

        if self.qr_worker:
            self.qr_worker.stop_scan()
            self.qr_worker.wait(500)
            self.qr_worker.deleteLater()
            self.qr_worker = None

        QApplication.processEvents()

    def enable_mes_recipe_mode(self, recipe_name, job_details=None):
        self.force_ui_update(recipe_name, job_details)

        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.debug_status)
        self.debug_timer.start(2000)

    def debug_status(self):
        if hasattr(self, 'machine_status'):
            current_text = self.machine_status.text()
            current_job = getattr(self, 'current_job_title', 'None')
            current_recipe = self.current_recipe

            print(f"🔍 DEBUG - UI shows: '{current_text}'")
            print(f"🔍 DEBUG - Internal: Recipe={current_recipe}, Job={current_job}")

            expected = f"READY - Recipe: {current_recipe} | Job: {current_job}"
            if current_text != expected and not current_text.startswith("RECIPE NOT FOUND"):
                print(f"⚠️ UI MISMATCH! Expected: '{expected}'")

    def handle_mes_disconnect(self):
        if self.current_recipe and not self.waiting_for_mes:
            print(f"✅ Already have recipe {self.current_recipe}, ignoring MES disconnect")
            return

        self.waiting_for_mes = True
        self.mes_recipe_override = False
        self.current_recipe = None
        config_manager.current_recipe = None

        self.waiting_card.setVisible(True)
        self.recipe_card.setVisible(False)
        self.current_job_title = None
        self.current_job_details = None
        self.qr_check_passed = False
        self.qr_result_ok = False
        self.last_qr_job_id = None
        self.has_active_mes_job = False

        self.waiting_title.setText("Waiting for MES Recipe")

        if hasattr(self, 'run_button'):
            self.run_button.setEnabled(False)

        self.machine_status.setText("WAITING FOR MES...")
        self.machine_status.setStyleSheet("color: #b45309;")
        self.status_indicator.setStyleSheet("color: #f59e0b; font-size: 16px;")

        QApplication.processEvents()

    def update_time(self):
        self.time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def darken_color(self, color, factor=0.7):
        colors = {
            "#10b981": "#059669",
            "#f97316": "#ea580c",
            "#2563eb": "#1d4ed8",
            "#7c3aed": "#6d28d9",
        }
        return colors.get(color, color)

    def refresh_recipes(self):
        if not self.mes_recipe_override:
            return

        recipes = config_manager.get_available_recipes()
        current_text = self.recipe_combo.currentText()

        self.recipe_combo.blockSignals(True)
        self.recipe_combo.clear()
        self.recipe_combo.addItem("✨ Select a Recipe")

        for recipe in recipes:
            self.recipe_combo.addItem(f"📦 {recipe}")

        if current_text in [f"📦 {r}" for r in recipes]:
            self.recipe_combo.setCurrentText(current_text)
        elif config_manager.current_recipe:
            recipe_with_prefix = f"📦 {config_manager.current_recipe}"
            if recipe_with_prefix in [self.recipe_combo.itemText(i) for i in range(self.recipe_combo.count())]:
                self.recipe_combo.setCurrentText(recipe_with_prefix)

        self.recipe_combo.blockSignals(False)
        self.update_pipeline_info()

    def on_recipe_changed(self, recipe_name):
        if not self.mes_recipe_override:
            return

        if recipe_name and recipe_name != "✨ Select a Recipe":
            clean_name = recipe_name.replace("📦 ", "")
            config_manager.set_current_recipe(clean_name)
            self.current_recipe = clean_name
            self.update_pipeline_info()
            self.load_pending_jobs()
            self.machine_status.setText("READY (MES Auto)")
        else:
            self.current_recipe = None
            config_manager.current_recipe = None
            self.pipeline_info_label.setText("No recipe selected")
            self.pending_jobs = []
            self.update_pending_display()
            self.machine_status.setText("READY (MES Auto - No Recipe)")

    def update_pipeline_info(self):
        if self.waiting_for_mes:
            self.pipeline_info_label.setText("Waiting for MES recipe...")
            return

        recipe_name = self.recipe_combo.currentText()

        if recipe_name == "✨ Select a Recipe" or not recipe_name:
            self.pipeline_info_label.setText("✨ Select a recipe to view details")
            return

        clean_name = recipe_name.replace("📦 ", "")
        summary = PipelineRunner.get_pipeline_summary(clean_name)

        if "error" in summary:
            info_text = f"⚠️ {summary['error']}"
        else:
            info_text = f"""
            <div style='font-size: 12px;'>
                <span style='font-size: 13px; font-weight: bold; color: #0f172a;'>{summary['recipe']}</span><br>
                <span style='color: #475569;'>Steps: {summary['total_blocks']} • {len(summary['execution_order'])} executable</span>
            </div>
            """

        self.pipeline_info_label.setText(info_text)

    def load_pending_jobs(self):
        if not self.current_recipe or self.waiting_for_mes:
            self.pending_jobs = []
            self.update_pending_display()
            return

        self.pending_jobs = PipelineRunner.get_pending_jobs(self.current_recipe)
        self.update_pending_display()

    def update_pending_display(self):
        while self.pending_layout.count() > 1:
            child = self.pending_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.pending_jobs:
            empty_container = QFrame()
            empty_container.setStyleSheet("background-color: transparent;")
            empty_layout = QVBoxLayout(empty_container)
            empty_layout.setContentsMargins(4, 4, 4, 4)

            empty_icon = QLabel("📭")
            empty_icon.setStyleSheet("font-size: 24px; color: #d1d5db;")
            empty_icon.setAlignment(Qt.AlignCenter)

            empty_label = QLabel("No pending jobs")
            empty_label.setFont(QFont("Inter", 11))
            empty_label.setStyleSheet("color: #9ca3af;")
            empty_label.setAlignment(Qt.AlignCenter)

            empty_layout.addWidget(empty_icon)
            empty_layout.addWidget(empty_label)

            self.pending_layout.insertWidget(0, empty_container)
            self.pending_count.setText("0")
            return

        for job in self.pending_jobs:
            self.pending_layout.insertWidget(self.pending_layout.count() - 1, self.create_job_widget(job))

        self.pending_count.setText(str(len(self.pending_jobs)))

    def create_job_widget(self, job):
        widget = QFrame()
        widget.setFixedHeight(48)
        widget.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #fcd34d;
                border-radius: 6px;
                padding: 4px;
            }
            QFrame:hover {
                background-color: #fef9c3;
            }
        """)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 4, 4)
        layout.setSpacing(4)

        job_id = job.get('job_id', 'Unknown')
        mes_details = job.get('mes_job_details', {})
        title = mes_details.get('title', job_id)

        if mes_details:
            job_icon = QLabel("🏭")
            job_icon.setToolTip(f"MES Job: {title}")
        else:
            job_icon = QLabel("📋")

        job_icon.setStyleSheet("font-size: 14px;")
        layout.addWidget(job_icon)

        display_id = title[:10] if len(title) > 10 else title

        completed = len(job.get('completed_steps', []))
        total = job.get('total_steps', 0)
        skipped = len(job.get('skipped_steps', []))

        info_text = f"<b>{display_id}</b> • {completed}/{total}"
        if skipped:
            info_text += f" ⏸{skipped}"

        if mes_details.get('product_code'):
            info_text += f" <span style='color:#6b7280;'>({mes_details['product_code']})</span>"

        info_label = QLabel(info_text)
        info_label.setFont(QFont("Inter", 10))
        info_label.setStyleSheet("color: #1e293b;")
        layout.addWidget(info_label)

        layout.addStretch()
        return widget

    def continue_job(self, job):
        if self.waiting_for_mes:
            QMessageBox.warning(
                self,
                "Cannot Continue Job",
                "System is waiting for MES recipe. Cannot continue jobs until a valid recipe is received.",
                QMessageBox.Ok
            )
            return

        skipped_steps = []
        for s in job.get('skipped_steps', []):
            if isinstance(s, dict):
                skipped_steps.append(s.get('step'))

        if not skipped_steps:
            print(f"✅ Job {job.get('job_id', '')} has no skipped steps - removing from pending")
            self.remove_from_pending(job)
            return

        self.pipeline_running = True

        print(f"🔄 Auto-continuing job {job.get('job_id', '')} with {len(skipped_steps)} skipped steps")

        self.machine_status.setText(f"▶ Continuing Job {job.get('job_id', '')[:8]}...")
        self.machine_status.repaint()
        QApplication.processEvents()

        try:
            success = PipelineRunner.continue_skipped_steps(
                self.current_recipe,
                job,
                self,
                pending_callback=lambda j: self.save_pending(self.current_recipe, j)
            )
        finally:
            self.pipeline_running = False

        if success:
            self.machine_status.setText("READY (MES Auto)")
            print(f"✅ Job continuation completed successfully")
            self.has_active_mes_job = False
            self.qr_check_passed = False
            self.qr_result_ok = False
            self.last_qr_job_id = None
            self.try_fetch_mes_recipe()
        else:
            self.machine_status.setText("PAUSED")
            print(f"⚠️ Job continuation paused")

        self.load_pending_jobs()

    def remove_from_pending(self, job):
        job_id = job.get('job_id')
        self.pending_jobs = [j for j in self.pending_jobs if j.get('job_id') != job_id]

        PipelineRunner.remove_pending_job(self.current_recipe, job_id)
        self.update_pending_display()

    def get_inventory(self) -> Dict[str, int]:
        try:
            if hasattr(PipelineRunner, '_api_client') and PipelineRunner._api_client:
                inventory = PipelineRunner._api_client.get_all_inventory()
                return inventory
            else:
                return {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0, 'G': 0, 'H': 0}
        except Exception as e:
            print(f"Inventory fetch error: {e}")
            return {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0, 'G': 0, 'H': 0}

    def save_pending(self, recipe: str, job: Dict):
        PipelineRunner.save_pending_job(recipe, job)

    def run_pipeline(self):

        if self.waiting_for_mes:
            QMessageBox.warning(
                self,
                "⚠️ System Waiting",
                "System is waiting for a recipe from MES.\n\nPlease wait until a valid recipe is received.",
                QMessageBox.Ok
            )
            return

        if not self.current_recipe:
            QMessageBox.warning(
                self,
                "⚠️ No Recipe Selected",
                "No recipe is currently selected from MES.\n\nPlease ensure MES is sending a valid recipe.",
                QMessageBox.Ok
            )
            return

        if not self.qr_check_passed:
            self.pending_run_after_qr = True
            self.show_qr_check_popup()
            return

        if hasattr(self, 'current_job_details') and self.current_job_details:
            current_job_id = (
                    self.current_job_details.get('title')
                    or self.current_job_details.get('workOrder')
                    or 'Unknown'
            )

            print(f"\n{'=' * 60}")
            print(f"📋 Getting all pending parts from MES")
            pending_parts = self.mes.get_all_pending_parts()

            if pending_parts:
                print(f"✅ Found {len(pending_parts)} pending parts:")
                for part in pending_parts:
                    print(f"   Part {part.get('partNumber')}: UID = {part.get('uid')}")

                print(f"\n📤 Posting all UIDs to MES immediately...")

                assembled_parts = []
                for part in pending_parts:
                    part_number = part.get('partNumber')
                    uid = part.get('uid')
                    if part_number and uid:
                        assembled_parts.append({
                            "partNumber": part_number,
                            "uid": uid
                        })

                print(f"DEBUG assembled_parts payload: {assembled_parts}")

                if assembled_parts:
                    success = self.mes.post_batch_assembly_results(assembled_parts)

                    if success:
                        print(f"✅ Successfully posted {len(assembled_parts)} UIDs to MES")
                    else:
                        print(f"❌ Failed to post UIDs to MES")
                        QMessageBox.warning(
                            self,
                            "⚠️ MES Update Failed",
                            "Failed to post UIDs to MES. Check connection and try again."
                        )
                        return
            else:
                print(f"⚠️ No pending parts found in MES")
                reply = QMessageBox.question(
                    self,
                    "No Pending Parts",
                    "No pending parts found in MES. Continue with pipeline anyway?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

            print(f"{'=' * 60}\n")
        else:
            current_job_id = None
            print(f"⚠️ No job details available from MES")

        existing_job = None
        for job in self.pending_jobs:
            if job.get('job_id') == current_job_id:
                existing_job = job
                break

        self.machine_status.setText(
            f"▶ {'Continuing' if existing_job else 'Starting'} Job {current_job_id[:8] if current_job_id else 'NEW'}..."
        )
        self.machine_status.repaint()
        QApplication.processEvents()

        if existing_job:
            print(f"✅ Auto-continuing existing job: {current_job_id}")
            self.continue_job(existing_job)
        else:
            print(f"✅ Auto-starting new job: {current_job_id}")
            self.pipeline_running = True
            try:
                success = PipelineRunner.run_pipeline_operator_mode(
                    self.current_recipe,
                    self,
                    pending_callback=lambda j: self.save_pending(self.current_recipe, j)
                )
            finally:
                self.pipeline_running = False

            if success:
                self.machine_status.setText("READY (MES Auto)")
                self.has_active_mes_job = False
                self.qr_check_passed = False
                self.qr_result_ok = False
                self.last_qr_job_id = None
                self.try_fetch_mes_recipe()
            else:
                self.machine_status.setText("PAUSED")

            self.load_pending_jobs()

    def start_new_pipeline(self):
        job_info = ""
        if hasattr(self, 'current_job_details') and self.current_job_details:
            job_id = self.current_job_details.get('title', 'Unknown')
            job_info = f"\n\nJob ID: {job_id}"

        reply = QMessageBox.question(
            self,
            "Start New Pipeline",
            f"Start new pipeline for <b>{self.current_recipe}</b>?{job_info}\n\n"
            f"This will execute all assembly steps from the beginning.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        self.machine_status.setText("RUNNING")
        self.pipeline_running = True
        try:
            success = PipelineRunner.run_pipeline_operator_mode(
                self.current_recipe,
                self,
                pending_callback=lambda j: self.save_pending(self.current_recipe, j)
            )
        finally:
            self.pipeline_running = False

        if success:
            self.machine_status.setText("READY (MES Auto)")
            self.has_active_mes_job = False
            self.qr_check_passed = False
            self.qr_result_ok = False
            self.last_qr_job_id = None
            self.try_fetch_mes_recipe()
        else:
            self.machine_status.setText("PAUSED")

        self.load_pending_jobs()

    def show_pending_selection_dialog(self):
        if not self.pending_jobs:
            QMessageBox.information(
                self,
                "No Pending Jobs",
                "No pending jobs found. Starting a new job instead.",
                QMessageBox.Ok
            )
            self.start_new_pipeline()
            return

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("Select Pending Job")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        label = QLabel("Select a pending job to continue:")
        label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        layout.addWidget(label)

        job_list = QListWidget()
        job_list.setStyleSheet("""
            QListWidget {
                font-size: 13px;
                border: 2px solid #e2e8f0;
                border-radius: 6px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #e2e8f0;
            }
            QListWidget::item:selected {
                background-color: #e2e8f0;
                color: black;
            }
        """)

        for job in self.pending_jobs:
            job_id = job.get('job_id', 'Unknown')
            completed = len(job.get('completed_steps', []))
            total = job.get('total_steps', 0)
            skipped = len(job.get('skipped_steps', []))

            mes_details = job.get('mes_job_details', {})
            is_mes_job = '🏭' if mes_details else '📋'

            display_text = f"{is_mes_job} {job_id} - {completed}/{total} steps"
            if skipped:
                display_text += f" (⏸ {skipped} skipped)"

            job_list.addItem(display_text)
            job_list.item(job_list.count() - 1).setData(Qt.UserRole, job)

        layout.addWidget(job_list)

        button_layout = QHBoxLayout()

        continue_btn = QPushButton("Continue Selected")
        continue_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)

        new_btn = QPushButton("Start New Instead")
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)

        button_layout.addWidget(continue_btn)
        button_layout.addWidget(new_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        continue_btn.clicked.connect(lambda: self.continue_selected_job(job_list, dialog))
        new_btn.clicked.connect(lambda: [dialog.accept(), self.start_new_pipeline()])
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def continue_selected_job(self, job_list, dialog):
        current_item = job_list.currentItem()
        if not current_item:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a job to continue.",
                QMessageBox.Ok
            )
            return

        job = current_item.data(Qt.UserRole)
        dialog.accept()
        self.continue_job(job)

    def show_continue_job_dialog(self, job):
        job_id = job.get('job_id', 'Unknown')
        completed = len(job.get('completed_steps', []))
        total = job.get('total_steps', 0)
        skipped = len(job.get('skipped_steps', []))

        mes_details = job.get('mes_job_details', {})
        pending_parts = mes_details.get('pending', [])

        message = f"Job <b>{job_id}</b> already exists with:\n\n"
        message += f"• Completed: {completed}/{total} steps\n"
        message += f"• Skipped: {skipped} steps\n"

        if pending_parts:
            parts_list = [p.get('partNumber') for p in pending_parts if p.get('partNumber')]
            message += f"• MES Pending: {', '.join(parts_list)}\n"

        message += f"\nWhat would you like to do?"

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Job Already Exists")
        dialog.setIcon(QMessageBox.Question)
        dialog.setText(message)
        dialog.setInformativeText("Select an option:")
        dialog.setStandardButtons(QMessageBox.NoButton)

        continue_btn = dialog.addButton("▶ Continue Existing Job", QMessageBox.ActionRole)
        new_btn = dialog.addButton("🔄 Start Fresh (Archive Old)", QMessageBox.ActionRole)
        cancel_btn = dialog.addButton("Cancel", QMessageBox.RejectRole)

        continue_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)

        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)

        dialog.exec()

        if dialog.clickedButton() == continue_btn:
            self.continue_job(job)
        elif dialog.clickedButton() == new_btn:
            self.archive_and_start_new(job)

    def archive_and_start_new(self, old_job):
        reply = QMessageBox.question(
            self,
            "Archive Old Job",
            "This will mark the existing job as 'archived' and start a fresh one.\n\n"
            "Old job data will be preserved for history.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        old_job['status'] = 'archived'
        old_job['archived_time'] = datetime.now().isoformat()

        self.save_archived_job(old_job)

        self.pending_jobs = [j for j in self.pending_jobs
                             if j.get('job_id') != old_job.get('job_id')]

        PipelineRunner.save_pending_job(self.current_recipe, None)
        self.start_new_pipeline()

    def save_archived_job(self, job):
        recipe_folder = config_manager.get_recipe_folder(self.current_recipe)
        if not recipe_folder:
            return

        archive_file = os.path.join(recipe_folder, 'archived_jobs.json')

        archives = []
        if os.path.exists(archive_file):
            try:
                with open(archive_file, 'r', encoding='utf-8') as f:
                    archives = json.load(f)
            except:
                archives = []

        archives.append(job)

        if len(archives) > 100:
            archives = archives[-100:]

        try:
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump(archives, f, indent=2, ensure_ascii=False)
            print(f"✅ Archived job: {job.get('job_id')}")
        except Exception as e:
            print(f"❌ Error archiving job: {e}")

    def show_pending_dialog(self):
        if self.waiting_for_mes:
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Pending Jobs Found")
        dialog.setIcon(QMessageBox.Question)
        dialog.setText(f"You have {len(self.pending_jobs)} incomplete job(s)")
        dialog.setInformativeText("What would you like to do?")
        dialog.setStandardButtons(QMessageBox.NoButton)

        continue_btn = dialog.addButton("Continue Pending", QMessageBox.ActionRole)
        new_btn = dialog.addButton("Start New", QMessageBox.ActionRole)
        cancel_btn = dialog.addButton("Cancel", QMessageBox.RejectRole)

        dialog.exec()

        if dialog.clickedButton() == continue_btn:
            if self.pending_jobs:
                self.continue_job(self.pending_jobs[0])
        elif dialog.clickedButton() == new_btn:
            self.force_new_job()

    def force_new_job(self):
        if self.waiting_for_mes:
            return

        reply = QMessageBox.question(
            self,
            "Start New Job",
            "Starting a new job will keep pending jobs for later.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.machine_status.setText("RUNNING")

            self.pipeline_running = True
            try:
                success = PipelineRunner.run_pipeline_operator_mode(
                    self.current_recipe,
                    self,
                    pending_callback=lambda j: self.save_pending(self.current_recipe, j)
                )
            finally:
                self.pipeline_running = False

            if success:
                self.machine_status.setText("READY (MES Auto)")
                self.has_active_mes_job = False
                self.qr_check_passed = False
                self.qr_result_ok = False
                self.last_qr_job_id = None
                self.try_fetch_mes_recipe()
            else:
                self.machine_status.setText("PAUSED")

            self.load_pending_jobs()

    def open_technician(self):
        self.stop_background_tasks()
        self.main.go_to(self.main.login_page)

    def showEvent(self, event):
        super().showEvent(event)

        if not self.spinner_timer.isActive():
            self.spinner_timer.start(500)

        if not self.mes_recipe_timer.isActive():
            self.mes_recipe_timer.start(5000)

        self.try_fetch_mes_recipe()

        if not self.waiting_for_mes:
            self.refresh_recipes()
            self.load_pending_jobs()

    def closeEvent(self, event):
        self.time_timer.stop()
        self.mes_recipe_timer.stop()
        self.spinner_timer.stop()

        if self.qr_worker:
            self.qr_worker.stop_scan()
            self.qr_worker.wait(1000)
            self.qr_worker = None

        super().closeEvent(event)

    def stop_background_tasks(self):
        if self.mes_recipe_timer.isActive():
            self.mes_recipe_timer.stop()

        if self.spinner_timer.isActive():
            self.spinner_timer.stop()

        if self.qr_dialog:
            self.qr_dialog.reject()
            self.qr_dialog.deleteLater()
            self.qr_dialog = None

        if self.qr_worker:
            self.qr_worker.stop_scan()
            self.qr_worker.wait(500)
            self.qr_worker.deleteLater()
            self.qr_worker = None