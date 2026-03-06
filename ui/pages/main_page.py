# ui/pages/main_page.py
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import requests
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QFrame, QGridLayout, QScrollArea,
    QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QPalette, QColor

from config_manager import config_manager
from ui.components.pipeline_runner import PipelineRunner
from ui.components.mes_client import MESClient


class MainPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.mes = MESClient()
        self.pending_jobs = []
        self.current_recipe = None
        self.current_job_title = None  # Add this
        self.current_job_details = None  # Add this
        self.mes_recipe_override = False  # Track if MES is controlling recipe
        self.waiting_for_mes = True  # Start in waiting mode
        self.last_valid_mes_time = None
        self.mes_outage_start = None

        # Initialize timers first
        self.time_timer = QTimer()
        # self.inventory_timer = QTimer()
        self.mes_recipe_timer = QTimer()
        self.spinner_timer = QTimer()

        self.init_ui()
        self.init_timers()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ================== Header with Gradient ==================
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

        # ================== Status Bar ==================
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

        # Machine status with indicator
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #f59e0b; font-size: 16px;")  # Default yellow

        self.machine_status = QLabel("WAITING FOR MES...")
        self.machine_status.setFont(QFont("Inter", 11, QFont.Bold))
        self.machine_status.setStyleSheet("color: #b45309;")

        status_layout.addWidget(self.status_indicator)
        status_layout.addWidget(self.machine_status)
        status_layout.addStretch()

        # MES Connection Status
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

        # Time display
        clock_icon = QLabel("🕐")
        clock_icon.setStyleSheet("font-size: 14px; color: #64748b;")

        self.time_label = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.time_label.setFont(QFont("Inter", 10))
        self.time_label.setStyleSheet("color: #475569;")

        status_layout.addWidget(clock_icon)
        status_layout.addWidget(self.time_label)

        layout.addWidget(status_frame)

        # ================== MES Waiting Indicator ==================
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

        # # Waiting icon
        # waiting_icon = QLabel("⏳")
        # waiting_icon.setStyleSheet("font-size: 48px; color: #f59e0b;")
        # waiting_icon.setAlignment(Qt.AlignCenter)
        # waiting_layout.addWidget(waiting_icon)

        # Waiting message
        self.waiting_title = QLabel("Waiting for MES Recipe")
        self.waiting_title.setFont(QFont("Inter", 16, QFont.Bold))
        self.waiting_title.setStyleSheet("color: #92400e;")
        self.waiting_title.setAlignment(Qt.AlignCenter)
        waiting_layout.addWidget(self.waiting_title)

        # self.waiting_message = QLabel(
        #     "System is waiting for recipe from MES.\n"
        #     "Manual recipe selection is disabled.\n\n"
        #     "The system will automatically enable when a valid recipe is received."
        # )
        # self.waiting_message.setFont(QFont("Inter", 12))
        # self.waiting_message.setStyleSheet("color: #b45309; line-height: 1.6;")
        # self.waiting_message.setAlignment(Qt.AlignCenter)
        # self.waiting_message.setWordWrap(True)
        # waiting_layout.addWidget(self.waiting_message)

        # Spinner animation placeholder
        self.spinner_label = QLabel("● ○ ○")
        self.spinner_label.setFont(QFont("Inter", 14))
        self.spinner_label.setStyleSheet("color: #f59e0b;")
        self.spinner_label.setAlignment(Qt.AlignCenter)
        waiting_layout.addWidget(self.spinner_label)

        layout.addWidget(self.waiting_card)

        # ================== Recipe Selection Card (Hidden initially) ==================
        self.recipe_card = QFrame()
        self.recipe_card.setFixedHeight(200)
        self.recipe_card.setVisible(False)  # Hidden until MES recipe is received
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

        # Recipe header with MES indicator
        recipe_header_layout = QHBoxLayout()
        recipe_header_layout.setSpacing(4)

        recipe_icon = QLabel("📋")
        recipe_icon.setStyleSheet("font-size: 18px;")

        recipe_header = QLabel("Recipe Selection")
        recipe_header.setFont(QFont("Inter", 14, QFont.Bold))
        recipe_header.setStyleSheet("color: #0f172a;")

        recipe_header_layout.addWidget(recipe_icon)
        recipe_header_layout.addWidget(recipe_header)

        # # MES Auto Mode Indicator
        # self.mes_mode_indicator = QLabel("⚡ MES Auto")
        # self.mes_mode_indicator.setStyleSheet("""
        #     QLabel {
        #         color: #059669;
        #         background-color: #d1fae5;
        #         padding: 4px 10px;
        #         border-radius: 12px;
        #         font-size: 11px;
        #         font-weight: bold;
        #         margin-left: 10px;
        #     }
        # """)
        # recipe_header_layout.addWidget(self.mes_mode_indicator)

        recipe_header_layout.addStretch()
        recipe_layout.addLayout(recipe_header_layout)

        # Recipe selection row
        selection_layout = QHBoxLayout()
        selection_layout.setSpacing(8)

        self.recipe_combo = QComboBox()
        self.recipe_combo.setFixedHeight(36)
        self.recipe_combo.setEnabled(False)  # Disabled by default (MES controlled)
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
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM0NzU1NjkiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cG9seWxpbmUgcG9pbnRzPSI2IDkgMTIgMTUgMTggOSI+PC9wb2x5bGluZT48L3N2Zz4=);
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
            # QComboBox QListView::item:selected {
            #     background-color: #3b82f6;
            #     color: white;
            # }
        """)
        self.recipe_combo.currentTextChanged.connect(self.on_recipe_changed)
        selection_layout.addWidget(self.recipe_combo)

        # Refresh button (hidden when in MES auto mode)
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(36, 36)
        self.refresh_btn.setEnabled(False)  # Disabled by default
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

        # # MES Recipe Override Info (shows when MES is controlling)
        # self.mes_recipe_info = QLabel("")
        # self.mes_recipe_info.setFont(QFont("Inter", 10))
        # self.mes_recipe_info.setStyleSheet("""
        #     QLabel {
        #         color: #047857;
        #         background: #ecfdf5;
        #         padding: 6px;
        #         border-radius: 6px;
        #         border: 1px solid #a7f3d0;
        #         margin-top: 4px;
        #     }
        # """)
        # self.mes_recipe_info.setWordWrap(True)
        # recipe_layout.addWidget(self.mes_recipe_info)

        # Pipeline info (smaller)
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

        # ================== Pending Jobs Panel (Smaller) ==================
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

        # Pending header
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

        # Pending jobs list with scroll (smaller)
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

        # ================== Quick Actions (Smaller buttons) ==================
        actions_label = QLabel("Quick Actions")
        actions_label.setFont(QFont("Inter", 14, QFont.Bold))
        actions_label.setStyleSheet("color: #0f172a; margin-top: 4px;")
        layout.addWidget(actions_label)

        # Action buttons grid
        actions_grid = QGridLayout()
        actions_grid.setSpacing(10)

        action_buttons = [
            ("👨‍🔧 Technician Login", "#f97316", self.open_technician, "Access technician panel"),
            ("▶ Run Pipeline", "#10b981", self.run_pipeline, "Execute selected recipe"),
        ]

        for i, (text, color, callback, tooltip) in enumerate(action_buttons):
            btn = QPushButton(text)
            btn.setFixedHeight(100)
            btn.setFont(QFont("Inter", 12, QFont.Bold))
            btn.setToolTip(tooltip)

            # Disable run button initially
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

        # Initial refresh (will be in waiting mode)
        self.refresh_recipes()
        self.load_pending_jobs()

        # Start timers and polling
        self.init_timers()
        self.start_mes_recipe_polling()
        self.start_spinner()

    def init_timers(self):
        """Initialize timers for updates"""
        # Time update timer
        self.spinner_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(300)

        # Inventory check timer
        # self.inventory_timer.timeout.connect(self.check_inventory)
        # self.inventory_timer.start(30000)

        # MES recipe polling timer
        self.mes_recipe_timer.timeout.connect(self.poll_mes_recipe)
        self.mes_recipe_timer.start(5000)  # Poll every 5 seconds

        # Spinner animation timer
        self.spinner_timer.timeout.connect(self.animate_spinner)
        self.spinner_timer.start(500)

    def animate_spinner(self):
        """Animate the waiting spinner"""
        if not self.waiting_for_mes:
            return

        frames = ["● ○ ○", "○ ● ○", "○ ○ ●", "○ ● ○"]
        current = getattr(self, '_spinner_frame', 0)
        self.spinner_label.setText(frames[current])
        self._spinner_frame = (current + 1) % len(frames)

    def start_spinner(self):
        """Start spinner animation"""
        self._spinner_frame = 0
        self.waiting_for_mes = True
        # Timer already started in init_timers

    def poll_mes_recipe(self):
        """Poll MES API with cooldown to prevent flickering"""
        try:
            had_valid_recipe = not self.waiting_for_mes and self.current_recipe is not None

            job_details = self.mes.get_job_details()
            print(f"DEBUG job_details from MES: {job_details}")

            mes_recipe = ""
            if job_details:
                mes_recipe = (job_details.get('recipe') or job_details.get('recipeName') or "").strip()

            if job_details and mes_recipe:
                self.last_valid_mes_time = datetime.now()
                self.mes_outage_start = None

                available_recipes = config_manager.get_available_recipes()
                print(f"DEBUG MES recipe received: [{mes_recipe}]")
                print(f"DEBUG Available recipes: {available_recipes}")

                if mes_recipe in available_recipes:
                    self.force_ui_update(mes_recipe, job_details)
                else:
                    print(f"⚠️ Recipe '{mes_recipe}' not found in local recipes")
            else:
                if self.last_valid_mes_time:
                    outage_duration = (datetime.now() - self.last_valid_mes_time).total_seconds()

                    if outage_duration > 30 and not had_valid_recipe:
                        print(f"⚠️ MES outage for {outage_duration:.0f}s - going to waiting")
                        self.handle_mes_disconnect()
                    else:
                        print(f"⏳ MES temporary outage ({outage_duration:.0f}s) - keeping current state")
                elif not had_valid_recipe:
                    self.handle_mes_disconnect()

        except Exception as e:
            print(f"❌ MES error: {e}")
            import traceback
            traceback.print_exc()

    def force_ui_update(self, recipe_name, job_details):
        """Force UI to update with new recipe and job details"""

        job_title = job_details.get('title') or job_details.get('workOrder') or 'Unknown'
        print(f"🔄 FORCE UI UPDATE: Recipe={recipe_name}, Job={job_title}")

        self.current_recipe = recipe_name
        config_manager.set_current_recipe(recipe_name)

        self.current_job_details = job_details
        self.current_job_title = job_title
        self.waiting_for_mes = False
        self.mes_recipe_override = True

        self.waiting_card.setVisible(False)
        self.recipe_card.setVisible(True)

        self.refresh_recipes()

        prefixed_recipe = f"📦 {recipe_name}"
        index = self.recipe_combo.findText(prefixed_recipe)

        if index >= 0:
            self.recipe_combo.blockSignals(True)
            self.recipe_combo.setCurrentIndex(index)
            self.recipe_combo.blockSignals(False)

        pending_count = len(job_details.get('pending', []))

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
            self.run_button.setEnabled(True)

        self.update_pipeline_info()
        self.load_pending_jobs()

        self.machine_status.repaint()
        self.mes_status_label.repaint()
        self.status_indicator.repaint()
        self.recipe_combo.repaint()
        self.repaint()

        QApplication.processEvents()

        print(f"✅ UI Updated - Current status text: {self.machine_status.text()}")
        print(f"✅ Config current recipe: {config_manager.current_recipe}")

    # def get_job_details(self) -> Dict:
    #     """
    #     Get currently running job details from MES API.
    #     Endpoint: /api/GetPartNumberDetail/running
    #
    #     Returns dict with job details including:
    #     - title: Job ID/Title
    #     - recipeName: Recipe to use
    #     - projectHeaderID: Project identifier
    #     - pending: List of pending parts
    #     - itemID: Item ID
    #     - station: Current station
    #     """
    #     try:
    #         response = requests.get(
    #             f"{self.base_url}/GetPartNumberDetail/running",
    #             timeout=self.timeout
    #         )
    #
    #         if response.status_code == 200:
    #             data = response.json()
    #             print(f"✅ Got running job data: {data}")
    #             return data
    #         else:
    #             print(f"⚠️ Failed to get running job: {response.status_code}")
    #             if response.text:
    #                 print(f"   Response: {response.text}")
    #
    #     except Exception as e:
    #         print(f"❌ Error getting running job: {e}")
    #         import traceback
    #         traceback.print_exc()
    #
    #     return {}

    def enable_mes_recipe_mode(self, recipe_name, job_details=None):
        """Enable MES-controlled recipe selection with job details"""
        self.force_ui_update(recipe_name, job_details)

        # Add debug timer to monitor status changes
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.debug_status)
        self.debug_timer.start(2000)  # Check every 2 seconds

    def debug_status(self):
        """Debug method to monitor status changes"""
        if hasattr(self, 'machine_status'):
            current_text = self.machine_status.text()
            current_job = getattr(self, 'current_job_title', 'None')
            current_recipe = self.current_recipe

            print(f"🔍 DEBUG - UI shows: '{current_text}'")
            print(f"🔍 DEBUG - Internal: Recipe={current_recipe}, Job={current_job}")

            # Check if they match
            expected = f"READY - Recipe: {current_recipe} | Job: {current_job}"
            if current_text != expected and not current_text.startswith("RECIPE NOT FOUND"):
                print(f"⚠️ UI MISMATCH! Expected: '{expected}'")

    def handle_mes_disconnect(self):
        """Handle MES disconnection - only if we never had a valid recipe"""
        # DON'T disconnect if we already have a valid recipe
        if self.current_recipe and not self.waiting_for_mes:
            print(f"✅ Already have recipe {self.current_recipe}, ignoring MES disconnect")
            return

        self.waiting_for_mes = True
        self.mes_recipe_override = False
        self.current_recipe = None
        config_manager.current_recipe = None

        # Hide recipe card, show waiting card
        self.waiting_card.setVisible(True)
        self.recipe_card.setVisible(False)

        # Update messages
        self.waiting_title.setText("Waiting for MES Recipe")

        # Disable run button
        if hasattr(self, 'run_button'):
            self.run_button.setEnabled(False)

        # Reset status
        self.machine_status.setText("WAITING FOR MES...")
        self.machine_status.setStyleSheet("color: #b45309;")
        self.status_indicator.setStyleSheet("color: #f59e0b; font-size: 16px;")

        # Force UI refresh
        QApplication.processEvents()

    def start_mes_recipe_polling(self):
        """Start polling MES for recipe updates"""
        # Initial poll
        self.poll_mes_recipe()

    def update_time(self):
        """Update time display"""
        self.time_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def darken_color(self, color, factor=0.7):
        """Simple color darkening for hover effects"""
        colors = {
            "#10b981": "#059669",
            "#f97316": "#ea580c",
            "#2563eb": "#1d4ed8",
            "#7c3aed": "#6d28d9",
        }
        return colors.get(color, color)

    def refresh_recipes(self):
        """Refresh recipes list."""
        # Only refresh if we have MES control
        if not self.mes_recipe_override:
            return

        recipes = config_manager.get_available_recipes()
        current_text = self.recipe_combo.currentText()

        self.recipe_combo.blockSignals(True)
        self.recipe_combo.clear()
        self.recipe_combo.addItem("✨ Select a Recipe")

        for recipe in recipes:
            self.recipe_combo.addItem(f"📦 {recipe}")

        # Try to restore previous selection
        if current_text in [f"📦 {r}" for r in recipes]:
            self.recipe_combo.setCurrentText(current_text)
        elif config_manager.current_recipe:
            recipe_with_prefix = f"📦 {config_manager.current_recipe}"
            if recipe_with_prefix in [self.recipe_combo.itemText(i) for i in range(self.recipe_combo.count())]:
                self.recipe_combo.setCurrentText(recipe_with_prefix)

        self.recipe_combo.blockSignals(False)
        self.update_pipeline_info()

    def on_recipe_changed(self, recipe_name):
        """Handle recipe selection change."""
        # Ignore if not in MES mode
        if not self.mes_recipe_override:
            return

        if recipe_name and recipe_name != "✨ Select a Recipe":
            # Remove the emoji prefix
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
        """Update pipeline information display."""
        if self.waiting_for_mes:
            self.pipeline_info_label.setText("Waiting for MES recipe...")
            return

        recipe_name = self.recipe_combo.currentText()

        if recipe_name == "✨ Select a Recipe" or not recipe_name:
            self.pipeline_info_label.setText("✨ Select a recipe to view details")
            return

        # Remove emoji prefix for actual recipe name
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
        """Load pending jobs for current recipe"""
        if not self.current_recipe or self.waiting_for_mes:
            self.pending_jobs = []
            self.update_pending_display()
            return

        self.pending_jobs = PipelineRunner.get_pending_jobs(self.current_recipe)
        self.update_pending_display()

    def update_pending_display(self):
        """Update pending jobs list"""
        # Clear existing items (keep stretch at end)
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

        # Add pending jobs
        for job in self.pending_jobs:
            self.pending_layout.insertWidget(self.pending_layout.count() - 1, self.create_job_widget(job))

        self.pending_count.setText(str(len(self.pending_jobs)))

    def create_job_widget(self, job):
        """Create compact widget for pending job"""
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

        # Job icon based on source
        job_id = job.get('job_id', 'Unknown')
        mes_details = job.get('mes_job_details', {})
        title = mes_details.get('title', job_id)

        # Show different icon for MES-sourced jobs
        if mes_details:
            job_icon = QLabel("🏭")  # Factory icon for MES jobs
            job_icon.setToolTip(f"MES Job: {title}")
        else:
            job_icon = QLabel("📋")  # Document icon for local jobs

        job_icon.setStyleSheet("font-size: 14px;")
        layout.addWidget(job_icon)

        # Job info - show title if available
        display_id = title[:10] if len(title) > 10 else title

        completed = len(job.get('completed_steps', []))
        total = job.get('total_steps', 0)
        skipped = len(job.get('skipped_steps', []))

        # Add additional info from MES if available
        info_text = f"<b>{display_id}</b> • {completed}/{total}"
        if skipped:
            info_text += f" ⏸{skipped}"

        # Add product code if available
        if mes_details.get('product_code'):
            info_text += f" <span style='color:#6b7280;'>({mes_details['product_code']})</span>"

        info_label = QLabel(info_text)
        info_label.setFont(QFont("Inter", 10))
        info_label.setStyleSheet("color: #1e293b;")
        layout.addWidget(info_label)

        layout.addStretch()

        # # Continue button
        # continue_btn = QPushButton("▶")
        # continue_btn.setFixedSize(28, 24)
        # continue_btn.setFont(QFont("Inter", 9, QFont.Bold))
        # continue_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color: #f59e0b;
        #         color: white;
        #         border-radius: 4px;
        #         padding: 2px 6px;
        #         border: none;
        #     }
        #     QPushButton:hover {
        #         background-color: #d97706;
        #     }
        # """)
        # continue_btn.setToolTip("Continue this job")
        # continue_btn.clicked.connect(lambda: self.continue_job(job))
        # layout.addWidget(continue_btn)

        return widget

    def continue_job(self, job):
        """Continue a pending job - automatically without asking"""
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
            # No skipped steps - job might be complete, just remove it
            print(f"✅ Job {job.get('job_id', '')} has no skipped steps - removing from pending")
            self.remove_from_pending(job)
            return

        # Auto-continue without asking
        print(f"🔄 Auto-continuing job {job.get('job_id', '')} with {len(skipped_steps)} skipped steps")

        # Update status
        self.machine_status.setText(f"▶ Continuing Job {job.get('job_id', '')[:8]}...")
        self.machine_status.repaint()
        QApplication.processEvents()

        # Execute continuation
        success = PipelineRunner.continue_skipped_steps(
            self.current_recipe,
            job,
            self,
            pending_callback=lambda j: self.save_pending(self.current_recipe, j)
        )

        if success:
            self.machine_status.setText("READY (MES Auto)")
            print(f"✅ Job continuation completed successfully")
        else:
            self.machine_status.setText("PAUSED")
            print(f"⚠️ Job continuation paused")

        # Refresh pending jobs list
        self.load_pending_jobs()

    def remove_from_pending(self, job):
        """Remove a completed job from pending list"""
        job_id = job.get('job_id')
        self.pending_jobs = [j for j in self.pending_jobs if j.get('job_id') != job_id]

        # Update pending jobs file
        PipelineRunner.save_pending_job(self.current_recipe, None)  # This will rewrite with removed job

        # Update display
        self.update_pending_display()

    # def check_inventory(self):
    #     """Check inventory in background (no display)"""
    #     try:
    #         self.mes.get_inventory(['A', 'B', 'C'])
    #     except:
    #         pass

    def get_inventory(self) -> Dict[str, int]:
        """Get current inventory for display purposes only"""
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
        """Save pending job - called from pipeline_runner"""
        PipelineRunner.save_pending_job(recipe, job)

    def run_pipeline(self):
        """Run pipeline from main page - posts UIDs immediately when clicked"""
        # Check if we're in waiting mode
        if self.waiting_for_mes:
            QMessageBox.warning(
                self,
                "⚠️ System Waiting",
                "System is waiting for a recipe from MES.\n\n"
                "Please wait until a valid recipe is received.",
                QMessageBox.Ok
            )
            return

        # Check if we have a recipe selected
        if not self.current_recipe:
            QMessageBox.warning(
                self,
                "⚠️ No Recipe Selected",
                "No recipe is currently selected from MES.\n\n"
                "Please ensure MES is sending a valid recipe.",
                QMessageBox.Ok
            )
            return

        # Get current job details from MES
        if hasattr(self, 'current_job_details') and self.current_job_details:
            current_job_id = self.current_job_details.get('title')

            # 🔥 STEP 1: GET ALL PENDING PARTS WITH THEIR UIDs
            print(f"\n{'=' * 60}")
            print(f"📋 Getting all pending parts from MES")
            pending_parts = self.mes.get_all_pending_parts()

            if pending_parts:
                print(f"✅ Found {len(pending_parts)} pending parts:")
                for part in pending_parts:
                    print(f"   Part {part.get('partNumber')}: UID = {part.get('uid')}")

                # 🔥 STEP 2: POST ALL UIDs IMMEDIATELY (BEFORE PIPELINE STARTS)
                print(f"\n📤 Posting all UIDs to MES immediately...")

                # Prepare the list of assembled parts
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

                        # # Show confirmation to user
                        # QMessageBox.information(
                        #     self,
                        #     "✅ MES Update Complete",
                        #     f"Successfully posted {len(assembled_parts)} UIDs to MES:\n\n" +
                        #     "\n".join([f"• Part {p['part_number']}: {p['uid']}" for p in assembled_parts])
                        # )
                    else:
                        print(f"❌ Failed to post UIDs to MES")
                        QMessageBox.warning(
                            self,
                            "⚠️ MES Update Failed",
                            "Failed to post UIDs to MES. Check connection and try again."
                        )
                        return  # 🛑 Stop pipeline if posting fails
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

        # Check if this job_id already exists in pending jobs
        existing_job = None
        for job in self.pending_jobs:
            if job.get('job_id') == current_job_id:
                existing_job = job
                break

        # Update status
        self.machine_status.setText(
            f"▶ {'Continuing' if existing_job else 'Starting'} Job {current_job_id[:8] if current_job_id else 'NEW'}..."
        )
        self.machine_status.repaint()
        QApplication.processEvents()

        # 🔥 STEP 3: NOW START THE PIPELINE (after UIDs are posted)
        if existing_job:
            # Auto-continue existing job
            print(f"✅ Auto-continuing existing job: {current_job_id}")
            self.continue_job(existing_job)
        else:
            # Auto-start new job
            print(f"✅ Auto-starting new job: {current_job_id}")

            success = PipelineRunner.run_pipeline_operator_mode(
                self.current_recipe,
                self,
                pending_callback=lambda j: self.save_pending(self.current_recipe, j)
            )

            if success:
                self.machine_status.setText("READY (MES Auto)")
            else:
                self.machine_status.setText("PAUSED")

            self.load_pending_jobs()

    def start_new_pipeline(self):
        """Start a new pipeline execution"""
        # Confirm before running
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

        # Update status
        self.machine_status.setText("RUNNING")

        success = PipelineRunner.run_pipeline_operator_mode(
            self.current_recipe,
            self,
            pending_callback=lambda j: self.save_pending(self.current_recipe, j)
        )

        if success:
            self.machine_status.setText("READY (MES Auto)")
        else:
            self.machine_status.setText("PAUSED")

        self.load_pending_jobs()

    def show_pending_selection_dialog(self):
        """Show dialog to select which pending job to continue"""
        if not self.pending_jobs:
            QMessageBox.information(
                self,
                "No Pending Jobs",
                "No pending jobs found. Starting new job instead.",
                QMessageBox.Ok
            )
            self.start_new_pipeline()
            return

        # Create custom dialog for job selection
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("Select Pending Job")
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # Instructions
        label = QLabel("Select a pending job to continue:")
        label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        layout.addWidget(label)

        # Job list
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

            # Get MES details
            mes_details = job.get('mes_job_details', {})
            is_mes_job = '🏭' if mes_details else '📋'

            display_text = f"{is_mes_job} {job_id} - {completed}/{total} steps"
            if skipped:
                display_text += f" (⏸ {skipped} skipped)"

            job_list.addItem(display_text)
            # Store job reference as item data
            job_list.item(job_list.count() - 1).setData(Qt.UserRole, job)

        layout.addWidget(job_list)

        # Buttons
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

        # Connect buttons
        continue_btn.clicked.connect(lambda: self.continue_selected_job(job_list, dialog))
        new_btn.clicked.connect(lambda: [dialog.accept(), self.start_new_pipeline()])
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def continue_selected_job(self, job_list, dialog):
        """Continue the selected job from list"""
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
        """Show dialog to confirm continuing existing job"""
        job_id = job.get('job_id', 'Unknown')
        completed = len(job.get('completed_steps', []))
        total = job.get('total_steps', 0)
        skipped = len(job.get('skipped_steps', []))

        # Get MES details if available
        mes_details = job.get('mes_job_details', {})
        pending_parts = mes_details.get('pending', [])

        # Build message
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

        # Style buttons
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
        """Archive the old job and start a new one with same ID"""
        reply = QMessageBox.question(
            self,
            "Archive Old Job",
            f"This will mark the existing job as 'archived' and start a fresh one.\n\n"
            f"Old job data will be preserved for history.\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        # Mark old job as archived
        old_job['status'] = 'archived'
        old_job['archived_time'] = datetime.now().isoformat()

        # Save archived job to history (separate file)
        self.save_archived_job(old_job)

        # Remove from pending jobs
        self.pending_jobs = [j for j in self.pending_jobs
                             if j.get('job_id') != old_job.get('job_id')]

        # Update pending jobs file
        PipelineRunner.save_pending_job(self.current_recipe, None)  # This will rewrite with removed job

        # Start new pipeline
        self.start_new_pipeline()

    def save_archived_job(self, job):
        """Save archived job to history file"""
        recipe_folder = config_manager.get_recipe_folder(self.current_recipe)
        if not recipe_folder:
            return

        archive_file = os.path.join(recipe_folder, 'archived_jobs.json')

        # Load existing archives
        archives = []
        if os.path.exists(archive_file):
            try:
                with open(archive_file, 'r', encoding='utf-8') as f:
                    archives = json.load(f)
            except:
                archives = []

        # Add new archive
        archives.append(job)

        # Keep only last 100 archives
        if len(archives) > 100:
            archives = archives[-100:]

        # Save
        try:
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump(archives, f, indent=2, ensure_ascii=False)
            print(f"✅ Archived job: {job.get('job_id')}")
        except Exception as e:
            print(f"❌ Error archiving job: {e}")

    def show_pending_dialog(self):
        """Show dialog for pending jobs"""
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
        """Force start new job despite pending"""
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

            success = PipelineRunner.run_pipeline_operator_mode(
                self.current_recipe,
                self,
                pending_callback=lambda j: self.save_pending(self.current_recipe, j)
            )

            if success:
                self.machine_status.setText("READY (MES Auto)")
            else:
                self.machine_status.setText("PAUSED")

            self.load_pending_jobs()

    def stop_background_tasks(self):
        # if self.inventory_timer.isActive():
        #     self.inventory_timer.stop()
        if self.mes_recipe_timer.isActive():
            self.mes_recipe_timer.stop()
        if self.spinner_timer.isActive():
            self.spinner_timer.stop()

    def open_technician(self):
        """Open technician login page."""
        self.stop_background_tasks()
        self.main.go_to(self.main.login_page)

    def showEvent(self, event):
        """Refresh when page is shown"""
        # if not self.inventory_timer.isActive():
        #     self.inventory_timer.start(30000)
        if not self.mes_recipe_timer.isActive():
            self.mes_recipe_timer.start(5000)
        if not self.spinner_timer.isActive():
            self.spinner_timer.start(500)

        if not self.waiting_for_mes:
            self.refresh_recipes()
            self.load_pending_jobs()

        self.poll_mes_recipe()
        super().showEvent(event)

    def closeEvent(self, event):
        """Clean up timers"""
        self.time_timer.stop()
        # self.inventory_timer.stop()
        self.mes_recipe_timer.stop()
        self.spinner_timer.stop()
        super().closeEvent(event)
