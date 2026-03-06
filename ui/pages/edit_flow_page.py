# ui/pages/edit_flow_page.py
import json
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsView, QGraphicsScene, QMessageBox, QGraphicsEllipseItem, QGraphicsRectItem,
    QComboBox, QDialog, QSplitter, QFrame, QGridLayout, QTabWidget, QFileDialog
)
from PySide6.QtCore import Qt, QEvent, QPointF, QPoint
from PySide6.QtGui import (
    QPen, QBrush, QColor, QFont, QTransform, QPainter, QPixmap
)

from ..components import AssemblyDialog
from ..components.pipeline_runner import PipelineRunner
from ..graphics import GraphicsBlock, ConnectionLine
from ..components.block_functions import BLOCKS
from config_manager import config_manager
from ui.components.heartbeat_manager import HeartbeatManager
from ui.components.dialogs import AssemblyDialog

class EditFlowPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.init_ui()
        self.assembly_blocks_map = {}
        self._is_loading = False


    def init_ui(self):
        self.setWindowTitle("Edit Flow")

        # ================== Main Layout ==================
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ================== Top Info Bar ==================
        top_bar = QHBoxLayout()

        # Recipe selection combo box
        recipe_label = QLabel("Recipe:")
        recipe_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #4b5563;")
        top_bar.addWidget(recipe_label)

        self.recipe_combo = QComboBox()
        self.recipe_combo.setFixedWidth(200)
        self.recipe_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 2px solid #d1d5db;
                border-radius: 4px;
                background-color: white;
                font-size: 14px;
            }
            QComboBox:hover {
                border-color: #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.recipe_combo.currentTextChanged.connect(self.on_recipe_changed)
        top_bar.addWidget(self.recipe_combo)

        # Refresh recipes button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Refresh recipes list")
        refresh_btn.setFixedSize(30, 30)
        self.recipe_combo.setStyleSheet("""
                    QComboBox {
                        font-size: 14px;
                        padding: 8px;
                        padding-right: 30px;  /* 给下拉箭头留空间 */
                        border: 2px solid #3498db;
                        border-radius: 5px;
                        background-color: white;
                        min-width: 300px;
                        color: #2c3e50;
                    }
                    QComboBox:hover {
                        border-color: #2980b9;
                    }
                    QComboBox:focus {
                        border-color: #1abc9c;
                    }

                    QComboBox::drop-down {
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 30px;
                        border-left: 1px solid #bdc3c7;
                        border-radius: 0 5px 5px 0;
                    }
                    QComboBox::down-arrow {
                        width: 12px;
                        height: 12px;
                        image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMiAxMiI+PHBhdGggZmlsbD0iIzM0OThkYiIgZD0iTTAgNGwxMiA0TDAgMTJ6Ii8+PC9zdmc+);
                    }
                    QComboBox::down-arrow:on {
                        top: 1px;
                    }

                    QComboBox QListView {
                        font-size: 14px;
                        background-color: white;
                        border: 2px solid #3498db;
                        border-radius: 5px;
                        outline: none;
                        padding: 2px;
                        margin: 0;
                    }

                    QComboBox QListView::item {
                        height: 32px;
                        padding: 5px 10px;
                        margin: 1px;
                        border-radius: 3px;
                        color: #2c3e50;
                    }

                    QComboBox QListView::item:selected {
                        background-color: #3498db;
                        color: white;
                        font-weight: bold;
                    }

                    QComboBox QListView::item:hover {
                        background-color: #f5f5f5;
                        color: #2c3e50;
                        border: 1px solid #dfe6e9;
                    }

                    QComboBox QListView::item:disabled {
                        color: #95a5a6;
                    }

                    QComboBox QScrollBar:vertical {
                        border: none;
                        background: #ecf0f1;
                        width: 10px;
                        border-radius: 5px;
                    }
                    QComboBox QScrollBar::handle:vertical {
                        background: #95a5a6;
                        border-radius: 5px;
                        min-height: 20px;
                    }
                    QComboBox QScrollBar::handle:vertical:hover {
                        background: #7f8c8d;
                    }
                """)
        refresh_btn.clicked.connect(self.refresh_recipes)
        top_bar.addWidget(refresh_btn)

        # Current recipe label
        self.recipe_label = QLabel("Selected: None")
        self.recipe_label.setStyleSheet("font-size: 14px; color: #6b7280; padding-left: 10px;")
        top_bar.addWidget(self.recipe_label)

        top_bar.addStretch()

        # Back button
        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color:#6b7280; color:white; font-weight:bold; 
                font-size:14px; padding:8px 16px; border-radius:4px;
            }
            QPushButton:hover { background-color:#4b5563; }
        """)
        back_btn.setFixedSize(100, 40)
        back_btn.clicked.connect(self.main.go_back)
        top_bar.addWidget(back_btn)

        layout.addLayout(top_bar)

        # ================== Scene and View ==================
        self.scene = QGraphicsScene()
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setSceneRect(0, 0, 1000, 500)
        self.scene.page = self  # Give scene reference to this page
        layout.addWidget(self.view)

        # ================== Panels ==================
        # Left panel
        self.LEFT_X, self.LEFT_Y, self.LEFT_W, self.LEFT_H = 20, 20, 250, 400
        left_panel = self.scene.addRect(self.LEFT_X, self.LEFT_Y, self.LEFT_W, self.LEFT_H,
                                        QPen(QColor("#3b82f6"), 2), QBrush(QColor("#e0f2fe")))
        left_panel.setZValue(-1)

        left_title = self.scene.addText("🛠️ Function Blocks")
        left_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        left_title.setDefaultTextColor(QColor("#1d4ed8"))
        left_title.setPos(self.LEFT_X + 10, self.LEFT_Y - 30)

        # Right panel
        self.RIGHT_X, self.RIGHT_Y, self.RIGHT_W, self.RIGHT_H = 350, 20, 600, 400
        right_panel = self.scene.addRect(self.RIGHT_X, self.RIGHT_Y, self.RIGHT_W, self.RIGHT_H,
                                         QPen(QColor("#10b981"), 2), QBrush(QColor("#f0fdf4")))
        right_panel.setZValue(-1)

        right_title = self.scene.addText("🚀 Execution Flow")
        right_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        right_title.setDefaultTextColor(QColor("#047857"))
        right_title.setPos(self.RIGHT_X + 10, self.RIGHT_Y - 30)

        # ================== Function Blocks ==================
        self.left_blocks = []
        self.pipeline_blocks = []
        self.connections = []  # Store all connections

        # Create left function blocks
        block_y = self.LEFT_Y + 20
        for name, action in BLOCKS:
            block = GraphicsBlock(name, action, self.LEFT_X + 15, block_y, is_left_block=True)
            self.scene.addItem(block)
            self.left_blocks.append(block)
            block_y += 70

        # ================== Drag and Drop ==================
        self.drag_item = None
        self.dragging_connection = False
        self.connection_start_block = None
        self.temp_connection = None

        # Enable mouse tracking and install event filter
        self.view.setMouseTracking(True)
        self.view.viewport().installEventFilter(self)

        # ================== Button Bar ==================
        button_layout = QHBoxLayout()

        # Save button
        self.save_btn = QPushButton("💾 Save Flow")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color:#10b981; color:white; font-weight:bold; 
                font-size:14px; padding:12px 24px; border-radius:6px;
            }
            QPushButton:hover { background-color:#059669; }
            QPushButton:disabled { background-color:#9ca3af; }
        """)
        self.save_btn.setFixedSize(150, 50)
        self.save_btn.clicked.connect(self.save_flow)

        # Load button
        self.load_btn = QPushButton("📂 Load Flow")
        self.load_btn.setStyleSheet("""
            QPushButton {
                background-color:#3b82f6; color:white; font-weight:bold; 
                font-size:14px; padding:12px 24px; border-radius:6px;
            }
            QPushButton:hover { background-color:#2563eb; }
            QPushButton:disabled { background-color:#9ca3af; }
        """)
        self.load_btn.setFixedSize(150, 50)
        self.load_btn.clicked.connect(self.auto_load_flow)

        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.load_btn)

        button_layout.addStretch()

        # # Run button
        # self.run_btn = QPushButton("▶ Run Flow")
        # self.run_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color:#6366f1; color:white; font-weight:bold;
        #         font-size:14px; padding:12px 24px; border-radius:6px;
        #     }
        #     QPushButton:hover { background-color:#4f46e5; }
        # """)
        # self.run_btn.setFixedSize(150, 50)
        # self.run_btn.clicked.connect(self.run_pipeline)

        # Clear button
        clear_btn = QPushButton("🗑️ Clear All")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color:#ef4444; color:white; font-weight:bold; 
                font-size:14px; padding:12px 24px; border-radius:6px;
            }
            QPushButton:hover { background-color:#dc2626; }
        """)
        clear_btn.setFixedSize(150, 50)
        clear_btn.clicked.connect(self.clear_all)

        # Delete selected button
        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color:#f59e0b; color:white; font-weight:bold; 
                font-size:14px; padding:12px 24px; border-radius:6px;
            }
            QPushButton:hover { background-color:#d97706; }
            QPushButton:disabled { background-color:#9ca3af; }
        """)
        self.delete_btn.setFixedSize(150, 50)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.delete_btn.setEnabled(False)  # Initially disabled

        # # Open Assembly Folder button
        # self.assembly_folder_btn = QPushButton("📂 Open Assembly Folder")
        # self.assembly_folder_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color:#8b5cf6; color:white; font-weight:bold;
        #         font-size:14px; padding:12px 24px; border-radius:6px;
        #     }
        #     QPushButton:hover { background-color:#7c3aed; }
        #     QPushButton:disabled { background-color:#9ca3af; }
        # """)
        # self.assembly_folder_btn.setFixedSize(180, 50)
        # self.assembly_folder_btn.clicked.connect(self.open_selected_assembly_folder)
        # self.assembly_folder_btn.setEnabled(False)  # Initially disabled

        button_layout.addWidget(self.run_btn)
        button_layout.addWidget(clear_btn)
        button_layout.addWidget(self.delete_btn)
        #button_layout.addWidget(self.assembly_folder_btn)

        layout.addLayout(button_layout)

        # Update recipes list
        self.refresh_recipes()

        # Update button states - THIS MUST COME AFTER ALL BUTTONS ARE CREATED
        self.update_buttons_state()

    def _setup_heartbeat_monitoring(self):
        """Setup monitoring of heartbeat status"""
        if AssemblyDialog._heartbeat_manager:
            AssemblyDialog._heartbeat_manager.connection_status_changed.connect(
            )

    def _on_heartbeat_status_changed(self, connected, message):
        """Update UI based on heartbeat status"""
        if hasattr(self, 'tcp_status_label'):
            if connected:
                self.tcp_status_label.setText(f"🟢 TCP: Connected (Heartbeat)")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 6px;
                        background-color: #e8f8ef;
                        border-radius: 3px;
                        font-weight: bold;
                    }
                """)
            else:
                self.tcp_status_label.setText(f"🔴 TCP: Disconnected")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e74c3c;
                        padding: 6px;
                        background-color: #ffebee;
                        border-radius: 3px;
                    }
                """)

    def showEvent(self, event):
        """Update information when page is shown"""
        self.refresh_recipes()
        self.update_recipe_display()

        # Add TCP status to UI if not already present
        # self._add_tcp_status_to_ui()

        super().showEvent(event)

    # def _add_tcp_status_to_ui(self):
    #     """Add TCP status indicator to the top bar"""
    #     # Find the top bar (first layout in the main layout)
    #     if self.layout() and self.layout().count() > 0:
    #         top_bar_layout = self.layout().itemAt(0)
    #         if isinstance(top_bar_layout, QHBoxLayout):
    #             # Add TCP status label before the back button
    #             self.tcp_status_label = QLabel("🔴 TCP: Disconnected")
    #             self.tcp_status_label.setStyleSheet("""
    #                 QLabel {
    #                     font-size: 11px;
    #                     color: #e74c3c;
    #                     padding: 6px;
    #                     background-color: #ffebee;
    #                     border-radius: 3px;
    #                     margin-right: 10px;
    #                     min-width: 120px;
    #                 }
    #             """)
    #
    #             # Insert before back button (which is the last item)
    #             top_bar_layout.insertWidget(top_bar_layout.count() - 1, self.tcp_status_label)
    #
    #             # Also add a small disconnect button for manual control
    #             disconnect_btn = QPushButton("🔌 Disconnect")
    #             disconnect_btn.setStyleSheet("""
    #                 QPushButton {
    #                     font-size: 10px;
    #                     padding: 4px 8px;
    #                     background-color: #e74c3c;
    #                     color: white;
    #                     border-radius: 3px;
    #                 }
    #                 QPushButton:hover {
    #                     background-color: #c0392b;
    #                 }
    #             """)
    #             disconnect_btn.setFixedSize(80, 25)
    #             disconnect_btn.clicked.connect(self._manual_disconnect_tcp)
    #             top_bar_layout.insertWidget(top_bar_layout.count() - 1, disconnect_btn)
    #
    #             # Update status based on current connection
    #             self._update_tcp_status_from_heartbeat()

    def _update_tcp_status_from_heartbeat(self):
        """Update TCP status based on heartbeat manager state"""
        if hasattr(self, 'tcp_status_label'):
            if (AssemblyDialog._heartbeat_manager and
                    AssemblyDialog._heartbeat_manager.is_connected()):
                self.tcp_status_label.setText("🟢 TCP: Connected (Heartbeat)")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #27ae60;
                        padding: 6px;
                        background-color: #e8f8ef;
                        border-radius: 3px;
                        font-weight: bold;
                    }
                """)
            else:
                self.tcp_status_label.setText("🔴 TCP: Disconnected")
                self.tcp_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e74c3c;
                        padding: 6px;
                        background-color: #ffebee;
                        border-radius: 3px;
                    }
                """)

    def _manual_disconnect_tcp(self):
        """Manually disconnect TCP"""
        # self.stop_heartbeat_and_disconnect()
        QMessageBox.information(self, "Disconnected", "TCP connection stopped")

    def stop_heartbeat_and_disconnect(self):
        """Stop heartbeat and disconnect from server"""
        print("\n📡 EditFlowPage: Stopping heartbeat...")

        from ui.components.dialogs import AssemblyDialog

        if AssemblyDialog._heartbeat_manager:
            print("  Found heartbeat manager - disconnecting...")
            AssemblyDialog._heartbeat_manager.disconnect()
            AssemblyDialog._heartbeat_manager = None
            AssemblyDialog._heartbeat_reference_count = 0
            print("  ✅ Heartbeat manager cleared")

        # Also clear global socket
        if hasattr(AssemblyDialog, '_global_tcp_socket'):
            AssemblyDialog._global_tcp_socket = None
            print("  ✅ Global socket cleared")

        # self._update_tcp_status_from_heartbeat()
        print("  ✅ TCP status updated")

        # Override the back button click handler

    # ================== Recipe Management ==================
    def refresh_recipes(self):
        """Refresh the recipes list"""
        recipes = config_manager.get_available_recipes()
        current_text = self.recipe_combo.currentText()

        # Block signals temporarily to prevent triggering on_recipe_changed during refresh
        self.recipe_combo.blockSignals(True)

        self.recipe_combo.clear()
        self.recipe_combo.addItem("-- Select Recipe --")

        for recipe in recipes:
            self.recipe_combo.addItem(recipe)

        # Try to restore previous selection
        if current_text in recipes:
            self.recipe_combo.setCurrentText(current_text)
        elif config_manager.current_recipe and config_manager.current_recipe in recipes:
            self.recipe_combo.setCurrentText(config_manager.current_recipe)

        # Re-enable signals
        self.recipe_combo.blockSignals(False)

        self.update_recipe_display()
        self.update_assembly_block_displays()

        # ✅ IMPORTANT: NO AUTO-LOAD HERE
        # Do NOT call load_flow() or any method that might trigger load_flow()

    def on_recipe_changed(self, recipe_name):
        """Handle recipe selection change"""
        if recipe_name and recipe_name != "-- Select Recipe --":
            # This will now work without trying to auto-load
            config_manager.set_current_recipe(recipe_name)

            # Clear current flow to avoid mixing recipes
            self.clear_all(confirm=False)
            self.update_recipe_display()
            self.update_assembly_block_displays()

            # ✅ FIX: DO NOT auto-load - just show message
            QMessageBox.information(self, "✅ Recipe Selected",
                                    f"Now editing: {recipe_name}\n\n"
                                    f"Click 'Load Flow' button to load an existing flow, or drag blocks to create a new one.")

            # ❌ REMOVE ANY CODE THAT MIGHT BE CALLING load_flow() HERE
            # Make sure there's no self.load_flow() or similar call

        else:
            config_manager.current_recipe = None
            self.update_recipe_display()

    def update_recipe_display(self):
        """Update the recipe display label"""
        if config_manager.current_recipe:
            self.recipe_label.setText(f"Selected: {config_manager.current_recipe}")
            self.save_btn.setEnabled(True)
            self.load_btn.setEnabled(True)
            self.run_btn.setEnabled(len(self.pipeline_blocks) > 0)
        else:
            self.recipe_label.setText("No recipe selected")
            self.save_btn.setEnabled(False)
            self.load_btn.setEnabled(False)
            self.run_btn.setEnabled(False)

    def update_buttons_state(self):
        """Update button states"""
        has_blocks = len(self.pipeline_blocks) > 0
        has_recipe = config_manager.current_recipe is not None
        has_selected = len(self.scene.selectedItems()) > 0

        self.run_btn.setEnabled(has_blocks and has_recipe)
        self.save_btn.setEnabled(has_recipe)
        self.load_btn.setEnabled(has_recipe)
        self.delete_btn.setEnabled(has_selected)

    # ================== Selection Changed Handler ==================
    def on_selection_changed(self):
        """Update button states when selection changes"""
        self.update_buttons_state()

        # Enable/disable Assembly folder button
        has_selected_assembly = False
        for item in self.scene.selectedItems():
            if isinstance(item, GraphicsBlock) and item.name == "Assembly":
                has_selected_assembly = True
                break

        # self.assembly_folder_btn.setEnabled(has_selected_assembly)

    # ================== Event Filter ==================
    def eventFilter(self, obj, event):
        # ================== MOUSE BUTTON PRESS ==================
        if event.type() == QEvent.MouseButtonPress:
            pos = self.view.mapToScene(event.pos())
            item = self.scene.itemAt(pos, QTransform())

            # Check if clicked on left panel block
            if isinstance(item, GraphicsBlock) and item.is_left_block:
                # Create new block to drag
                self.drag_item = GraphicsBlock(
                    item.name,
                    item.action,
                    pos.x() - 110,
                    pos.y() - 22
                )
                self.scene.addItem(self.drag_item)
                self.drag_item.setOpacity(0.7)
                return True

            # Check if clicked on port
            elif isinstance(item, QGraphicsEllipseItem):
                parent = item.parentItem()
                if isinstance(parent, GraphicsBlock) and not parent.is_left_block:
                    if hasattr(item, 'port_type') and item.port_type == "output":
                        self.dragging_connection = True
                        self.connection_start_block = parent

                        # Create temporary connection line
                        block_scene_pos = parent.scenePos()
                        start_pos = block_scene_pos + QPointF(parent.block_width,
                                                              parent.block_height / 2)
                        self.temp_connection = ConnectionLine(parent, None, self.scene)
                        self.temp_connection.setLine(start_pos.x(), start_pos.y(),
                                                     pos.x(), pos.y())
                        self.temp_connection.setPen(QPen(QColor("#6366f1"), 2, Qt.DashLine))
                        self.temp_connection.setZValue(0)
                        self.scene.addItem(self.temp_connection)
                        return True

        # ================== MOUSE MOVE ==================
        elif event.type() == QEvent.MouseMove:
            pos = self.view.mapToScene(event.pos())

            if self.drag_item:
                # Update block position
                self.drag_item.setPos(pos - QPointF(110, 22))
                return True

            elif self.dragging_connection and self.temp_connection:
                if self.connection_start_block:
                    block_scene_pos = self.connection_start_block.scenePos()
                    start_pos = block_scene_pos + QPointF(self.connection_start_block.block_width,
                                                          self.connection_start_block.block_height / 2)
                    self.temp_connection.setLine(start_pos.x(), start_pos.y(),
                                                 pos.x(), pos.y())
                return True

        # ================== MOUSE BUTTON RELEASE ==================
        elif event.type() == QEvent.MouseButtonRelease:
            pos = self.view.mapToScene(event.pos())

            if self.drag_item:
                # Check if placed in right panel
                if (self.RIGHT_X <= pos.x() <= self.RIGHT_X + self.RIGHT_W and
                        self.RIGHT_Y <= pos.y() <= self.RIGHT_Y + self.RIGHT_H):

                    # Keep block in pipeline
                    self.drag_item.is_left_block = False
                    self.drag_item.setOpacity(1.0)
                    self.drag_item.setFlag(QGraphicsRectItem.ItemIsMovable, True)
                    self.drag_item.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
                    self.drag_item.setFlag(QGraphicsRectItem.ItemIsSelectable, True)

                    # Initialize connection lists
                    self.drag_item.input_connections = []
                    self.drag_item.output_connections = []

                    # Create ports for block
                    w = self.drag_item.block_width
                    h = self.drag_item.block_height

                    if self.drag_item.name == "End":
                        # End block only has input port
                        self.drag_item.input_port = QGraphicsEllipseItem(-12, h / 2 - 12, 24, 24, self.drag_item)
                        self.drag_item.input_port.setBrush(QBrush(QColor("#3b82f6")))
                        self.drag_item.input_port.setPen(QPen(QColor("#1d4ed8"), 1))
                        self.drag_item.input_port.setZValue(10)
                        self.drag_item.input_port.setAcceptHoverEvents(True)
                        self.drag_item.input_port.port_type = "input"

                    elif self.drag_item.name in ["Assembly", "Screw"]:
                        # Assembly and Screw blocks have both input and output ports
                        self.drag_item.input_port = QGraphicsEllipseItem(-12, h / 2 - 12, 24, 24, self.drag_item)
                        self.drag_item.input_port.setBrush(QBrush(QColor("#3b82f6")))
                        self.drag_item.input_port.setPen(QPen(QColor("#1d4ed8"), 1))
                        self.drag_item.input_port.setZValue(10)
                        self.drag_item.input_port.setAcceptHoverEvents(True)
                        self.drag_item.input_port.port_type = "input"

                        self.drag_item.output_port = QGraphicsEllipseItem(w - 12, h / 2 - 12, 24, 24, self.drag_item)
                        self.drag_item.output_port.setBrush(QBrush(QColor("#22c55e")))
                        self.drag_item.output_port.setPen(QPen(QColor("#15803d"), 1))
                        self.drag_item.output_port.setZValue(10)
                        self.drag_item.output_port.setAcceptHoverEvents(True)
                        self.drag_item.output_port.port_type = "output"

                    else:
                        # Other blocks (like Camera) have output port
                        self.drag_item.output_port = QGraphicsEllipseItem(w - 12, h / 2 - 12, 24, 24, self.drag_item)
                        self.drag_item.output_port.setBrush(QBrush(QColor("#22c55e")))
                        self.drag_item.output_port.setPen(QPen(QColor("#15803d"), 1))
                        self.drag_item.output_port.setZValue(10)
                        self.drag_item.output_port.setAcceptHoverEvents(True)
                        self.drag_item.output_port.port_type = "output"

                    # Update Assembly block display with ID
                    if self.drag_item.name == "Assembly":
                        self.assign_block_id(self.drag_item)
                        self.drag_item.text.setPlainText(f"Assembly (Block {self.drag_item.block_id})")

                    self.pipeline_blocks.append(self.drag_item)
                    self.update_buttons_state()
                else:
                    # If placed outside right panel, remove
                    self.scene.removeItem(self.drag_item)

                self.drag_item = None
                return True

            elif self.dragging_connection and self.temp_connection:
                # Remove temporary connection line
                self.scene.removeItem(self.temp_connection)
                self.temp_connection = None

                # Find all items at mouse position
                items = self.scene.items(pos)
                target_block = None
                target_port = None

                # Look for input port
                for item in items:
                    if isinstance(item, QGraphicsEllipseItem):
                        parent = item.parentItem()
                        if isinstance(parent, GraphicsBlock) and not parent.is_left_block:
                            if hasattr(item, 'port_type') and item.port_type == "input":
                                target_block = parent
                                target_port = item
                                break

                if (target_block and target_port and
                        self.connection_start_block and
                        target_block != self.connection_start_block):

                    # Create permanent connection
                    connection = ConnectionLine(self.connection_start_block, target_block, self.scene)
                    self.scene.addItem(connection)
                    self.connections.append(connection)

                    # Update block connection lists
                    if not hasattr(self.connection_start_block, 'output_connections'):
                        self.connection_start_block.output_connections = []
                    if not hasattr(target_block, 'input_connections'):
                        target_block.input_connections = []

                    self.connection_start_block.output_connections.append(connection)
                    target_block.input_connections.append(connection)

                    connection.from_block = self.connection_start_block
                    connection.to_block = target_block

                    self.update_all_connections()

                self.dragging_connection = False
                self.connection_start_block = None
                return True

        # ================== MOUSE DOUBLE CLICK ==================
        elif event.type() == QEvent.MouseButtonDblClick:
            pos = self.view.mapToScene(event.pos())
            item = self.scene.itemAt(pos, QTransform())

            # Handle double-click on Assembly block - DIRECTLY OPEN CONFIGURATION
            if isinstance(item, GraphicsBlock) and item.name == "Assembly" and not item.is_left_block:
                # Directly open the configuration dialog without showing summary
                self.configure_assembly_block(item)
                return True

        # ================== CONTEXT MENU (RIGHT CLICK) ==================
        elif event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            pos = self.view.mapToScene(event.pos())
            item = self.scene.itemAt(pos, QTransform())

            # Handle right-click on Assembly block
            if isinstance(item, GraphicsBlock) and item.name == "Assembly" and not item.is_left_block:
                # Show context menu
                menu = self.create_context_menu(item)
                menu.exec(self.view.mapToGlobal(event.pos()))
                return True

        return super().eventFilter(obj, event)

    # ================== Update All Connections ==================
    def update_all_connections(self):
        for conn in self.connections:
            if conn in self.scene.items():
                conn.update_position()

    # ================== Remove Connection ==================
    def remove_connection(self, connection):
        if connection in self.connections:
            self.connections.remove(connection)

        # Remove from block's connection lists
        if hasattr(connection, 'from_block'):
            if connection in connection.from_block.output_connections:
                connection.from_block.output_connections.remove(connection)

        if hasattr(connection, 'to_block'):
            if connection in connection.to_block.input_connections:
                connection.to_block.input_connections.remove(connection)

        # Remove from scene
        if connection in self.scene.items():
            self.scene.removeItem(connection)

    # ================== Remove Block ==================
    def remove_block(self, block):
        if block in self.pipeline_blocks:
            self.pipeline_blocks.remove(block)
            self.update_buttons_state()

    # ================== Get Execution Order ==================
    def get_execution_order(self):
        """Get block execution order based on connections ONLY"""
        if not self.pipeline_blocks:
            return []

        # Find start blocks (blocks without input connections)
        start_blocks = [block for block in self.pipeline_blocks
                        if not getattr(block, 'input_connections', [])]

        # ❌ REMOVED the Y-position fallback
        # If no start blocks, return empty list (nothing to execute)
        if not start_blocks:
            return []  # No valid starting point

        # Perform topological sort
        execution_order = []
        visited = set()

        def dfs(block):
            if block is None or block in visited:
                return
            visited.add(block)

            # Add current block
            execution_order.append(block)

            # Visit connected blocks
            output_connections = getattr(block, 'output_connections', [])
            for conn in output_connections:
                if hasattr(conn, 'to_block') and conn.to_block is not None:
                    dfs(conn.to_block)

        # Start DFS from each start block
        for block in start_blocks:
            dfs(block)

        # ✅ Check if we found all blocks or just a subset
        if len(execution_order) != len(self.pipeline_blocks):
            print(f"⚠️ Warning: Only {len(execution_order)} of {len(self.pipeline_blocks)} blocks are connected")
            # You might want to show a warning, but still return the connected ones
            # Or return empty list if you want ALL blocks to be connected

        return execution_order

    # ================== Run Pipeline ==================
    def run_pipeline(self):
        """Run pipeline using shared PipelineRunner."""
        if not config_manager.current_recipe:
            QMessageBox.warning(self, "⚠️ Warning", "Please select a recipe first!")
            return

        # Get execution order (now returns empty list if no valid connections)
        execution_order = self.get_execution_order()

        # ❌ NEW: Check if we have anything to execute
        if not execution_order:
            QMessageBox.warning(
                self,
                "⚠️ No Valid Pipeline",
                "No connected blocks found to execute.\n\n"
                "Please connect blocks with lines to create a valid pipeline.\n"
                "Blocks without connections will not run."
            )
            return

        # Also check if ALL blocks are connected (optional stricter check)
        if len(execution_order) != len(self.pipeline_blocks):
            reply = QMessageBox.question(
                self,
                "⚠️ Partial Pipeline",
                f"Only {len(execution_order)} out of {len(self.pipeline_blocks)} blocks are connected.\n\n"
                f"Unconnected blocks will NOT run.\n\n"
                f"Do you want to continue with only the connected blocks?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

        # Use the shared PipelineRunner
        success = PipelineRunner.run_pipeline(config_manager.current_recipe, self, execution_order)

        if success:
            print(f"Pipeline executed successfully from EditFlowPage")
        else:
            print(f"Pipeline execution failed from EditFlowPage")

    # ================== Assembly Block Execution ==================
    def configure_assembly_block(self, assembly_block):
        """Open AssemblyDialog for a specific block"""
        # Get block ID
        if not hasattr(assembly_block, 'block_id'):
            self.assign_block_id(assembly_block)

        # Get existing config
        existing_config = {}
        if hasattr(assembly_block, 'assembly_data') and assembly_block.assembly_data:
            existing_config = assembly_block.assembly_data.copy()
        else:
            existing_config = {}

        # Add block_id and block_name to config
        existing_config['block_id'] = assembly_block.block_id
        existing_config['block_name'] = f"Block_{assembly_block.block_id}"

        # Open dialog with existing configuration
        dialog = AssemblyDialog(
            parent=self,
            initial_config=existing_config,
            block_id=assembly_block.block_id,
            block_name=f"Block_{assembly_block.block_id}"
        )

        # Set dialog title
        if existing_config and existing_config.get('total_steps', 0) > 0:
            dialog.setWindowTitle(f"Edit Assembly Block {assembly_block.block_id}")
        else:
            dialog.setWindowTitle(f"Configure Assembly Block {assembly_block.block_id}")

        if dialog.exec() == QDialog.Accepted:
            # Get the updated configuration
            new_config = dialog.get_all_selections()

            # Save the configuration
            assembly_block.assembly_data = new_config

            # Update text display
            total_steps = new_config.get('total_steps', 0)
            if total_steps > 0:
                assembly_block.text.setPlainText(f"Assembly (Block {assembly_block.block_id}, {total_steps} steps)")
            else:
                assembly_block.text.setPlainText(f"Assembly (Block {assembly_block.block_id})")

            # REMOVED THE SUMMARY MESSAGE BOX
            # Just show a simple confirmation
            QMessageBox.information(self, "✅ Configuration Saved",
                                    f"Assembly block {assembly_block.block_id} configured successfully.")

            # Auto-save to file
            self.auto_save_assembly_config(assembly_block)

            return True
        else:
            # Dialog was cancelled
            return False

    def auto_save_assembly_config(self, assembly_block):
        """Auto-save assembly block configuration to JSON file"""
        if not config_manager.current_recipe:
            return

        if not hasattr(assembly_block, 'assembly_data') or not assembly_block.assembly_data:
            return

        # Create assembly configs folder
        recipe_path = config_manager.get_current_recipe_folder()
        if not recipe_path:
            return

        configs_folder = os.path.join(recipe_path, "assembly_configs")
        os.makedirs(configs_folder, exist_ok=True)

        # Save to block-specific JSON file
        config_file = os.path.join(configs_folder, f"block_{assembly_block.block_id}_config.json")

        try:
            with open(config_file, 'w') as f:
                json.dump(assembly_block.assembly_data, f, indent=2)
            print(f"DEBUG: Auto-saved config for block {assembly_block.block_id} to {config_file}")
        except Exception as e:
            print(f"ERROR: Failed to auto-save config: {str(e)}")

    def execute_assembly_block(self, assembly_block, step_number, total_blocks):
        """Execute an Assembly block using its stored data"""
        # Check if block has assembly_data
        if not hasattr(assembly_block, 'assembly_data') or not assembly_block.assembly_data:
            QMessageBox.warning(self, "⚠️ No Configuration",
                                "This Assembly block has no configuration!")
            return

        assembly_data = assembly_block.assembly_data
        total_steps = assembly_data.get('total_steps', 0)
        selections = assembly_data.get('selections', {})

        if total_steps == 0 or not selections:
            QMessageBox.warning(self, "⚠️ No Steps",
                                "This Assembly block has no assembly steps configured!")
            return

        # Show total steps first
        reply = QMessageBox.information(self, "🛠️ Assembly Block",
                                        f"This Assembly block has {total_steps} step(s).\n\n"
                                        f"Ready to start step-by-step verification?",
                                        QMessageBox.Ok | QMessageBox.Cancel)
        if reply != QMessageBox.Ok:
            return

        # Execute each step
        completed_steps = 0
        for step_num in range(1, total_steps + 1):
            step_key = str(step_num)
            if step_key in selections:
                if self.execute_assembly_step(assembly_block, step_num, total_steps, selections[step_key]):
                    completed_steps += 1
                else:
                    # User cancelled or marked as not complete
                    break
            else:
                QMessageBox.warning(self, "⚠️ Missing Step",
                                    f"Step {step_num} configuration not found!")
                break

        # After all steps are done
        QMessageBox.information(self, "✅ Assembly Complete",
                                f"Assembly verification completed!\n"
                                f"{completed_steps} of {total_steps} step(s) verified.")
        pass

    def get_captured_image_path(self, assembly_block, step_num, product_name):
        """Get the already-captured image from Assembly folder for specific block"""
        recipe_path = config_manager.get_current_recipe_folder()
        if not recipe_path:
            print(f"DEBUG: No recipe path found")
            return None

        # Get block-specific folder
        if not hasattr(assembly_block, 'block_id'):
            self.assign_block_id(assembly_block)

        # First, check the step folder
        step_folder = self.get_assembly_step_folder(assembly_block, step_num)
        if not step_folder or not os.path.exists(step_folder):
            print(f"DEBUG: Step folder not found: Step_{step_num}")
            return None

        # Look for image files in the step folder
        import glob
        image_patterns = [
            os.path.join(step_folder, "*.jpg"),
            os.path.join(step_folder, "*.jpeg"),
            os.path.join(step_folder, "*.png"),
            os.path.join(step_folder, "*.bmp"),
            os.path.join(step_folder, "*.JPG"),
            os.path.join(step_folder, "*.JPEG"),
            os.path.join(step_folder, "*.PNG"),
            os.path.join(step_folder, "*.BMP")
        ]

        image_files = []
        for pattern in image_patterns:
            image_files.extend(glob.glob(pattern))

        if image_files:
            # Return the most recent file
            image_files.sort(key=os.path.getmtime, reverse=True)
            latest_image = image_files[0]
            print(f"DEBUG: Found {len(image_files)} images in Step_{step_num}, using: {os.path.basename(latest_image)}")
            return latest_image

        print(f"DEBUG: No images found in Step_{step_num} folder")
        return None

    def show_comparison_step(self, step_num, total_steps, product_name,
                             reference_path, captured_path):
        """Show reference image vs captured image side by side"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Step {step_num}/{total_steps}: {product_name}")
        dialog.setMinimumSize(800, 500)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel(f"Step {step_num}: {product_name}")
        header.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Instructions
        instructions = QLabel("Compare Reference vs Actual Assembly")
        instructions.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #2c3e50;
                padding: 8px;
                background-color: #ecf0f1;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)

        # Split view for comparison
        splitter = QSplitter(Qt.Horizontal)

        # Left: Reference image (from Annotation)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        ref_header = QLabel("📋 Product Image")
        ref_header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 8px;
                background-color: #e3f2fd;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        ref_header.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(ref_header)

        ref_image_label = QLabel()
        ref_image_label.setAlignment(Qt.AlignCenter)

        if reference_path and os.path.exists(reference_path):
            pixmap = QPixmap(reference_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(350, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                ref_image_label.setPixmap(scaled_pixmap)
                ref_image_label.setToolTip(f"Reference: {os.path.basename(reference_path)}")
            else:
                ref_image_label.setText("❌ Cannot load reference")
        else:
            ref_image_label.setText("⚠️ Reference not found")

        ref_image_label.setStyleSheet("""
            QLabel {
                border: 3px solid #3498db;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 10px;
                min-height: 260px;
            }
        """)
        left_layout.addWidget(ref_image_label)
        left_layout.addStretch()

        # Right: Captured image (from Assembly folder)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        cap_header = QLabel("📸 Captured Assembly")
        cap_header.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding: 8px;
                background-color: #e8f8ef;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        cap_header.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(cap_header)

        cap_image_label = QLabel()
        cap_image_label.setAlignment(Qt.AlignCenter)

        if captured_path and os.path.exists(captured_path):
            pixmap = QPixmap(captured_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(350, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                cap_image_label.setPixmap(scaled_pixmap)
                filename = os.path.basename(captured_path)
                folder = os.path.basename(os.path.dirname(captured_path))
                cap_image_label.setToolTip(f"Captured: {folder}/{filename}")
            else:
                cap_image_label.setText("❌ Cannot load captured")
        else:
            cap_image_label.setText("⚠️ No captured image found\n(Captured during configuration)")
            cap_image_label.setStyleSheet("""
                QLabel {
                    color: #e74c3c;
                    font-size: 13px;
                }
            """)

        cap_image_label.setStyleSheet("""
            QLabel {
                border: 3px solid #2ecc71;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 10px;
                min-height: 260px;
            }
        """)
        right_layout.addWidget(cap_image_label)
        right_layout.addStretch()

        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 400])

        layout.addWidget(splitter)

        # Info text
        if captured_path:
            info_text = f"Captured image from Assembly/Step_{step_num}/ folder"
        else:
            info_text = "No captured image found. Image should have been captured during configuration."

        info_label = QLabel(info_text)
        info_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #7f8c8d;
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 6px;
                margin-top: 10px;
            }
        """)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Continue button
        continue_btn = QPushButton("▶ Continue to Verification")
        continue_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px;
                background-color: #9b59b6;
                color: white;
                border-radius: 6px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        continue_btn.clicked.connect(dialog.accept)
        layout.addWidget(continue_btn)

        return dialog.exec() == QDialog.Accepted

    def execute_assembly_step(self, assembly_block, step_num, total_steps, selection):
        """Execute a single assembly step - VERIFICATION with live camera comparison"""
        product_data = selection.get('product_data', {})
        product_name = product_data.get('name', f'Product {step_num}')
        reference_image_path = product_data.get('image_path')  # From Annotation folder

        # Try to get captured image from selection data first (saved path)
        saved_image_path = selection.get('captured_image_path')

        # If not in selection data, try to find it in the Assembly folder
        if not saved_image_path or not os.path.exists(saved_image_path):
            saved_image_path = self.get_captured_image_path(assembly_block, step_num, product_name)

        if not saved_image_path:
            QMessageBox.warning(self, "⚠️ No Saved Image",
                                f"No captured image found for Step {step_num}.\n"
                                f"Please capture an image during assembly configuration first.")
            return False

        # Step 1: Show reference image vs LIVE CAMERA for visual comparison
        continue_decision = self.show_live_camera_comparison(step_num, total_steps, product_name, reference_image_path)

        if continue_decision == "cancel":
            return False  # User cancelled entire process

        if continue_decision == "skip":
            QMessageBox.information(self, "Step Skipped",
                                    f"Step {step_num} verification skipped.")
            return False  # Mark step as not completed

        # Step 2: Show saved image and ask for verification
        return self.verify_assembly_completion(step_num, product_name, saved_image_path)

    def open_assembly_block_folder(self, assembly_block):
        """Open the folder for a specific Assembly block"""
        if not config_manager.current_recipe:
            QMessageBox.warning(self, "Warning", "No recipe selected!")
            return

        recipe_path = config_manager.get_current_recipe_folder()
        if not recipe_path:
            QMessageBox.warning(self, "Warning", "Recipe folder not found!")
            return

        # Get block ID
        if not hasattr(assembly_block, 'block_id'):
            self.assign_block_id(assembly_block)

        # Construct folder path
        block_folder = os.path.join(recipe_path, "Assembly", f"Block_{assembly_block.block_id}")

        # Create folder if it doesn't exist
        os.makedirs(block_folder, exist_ok=True)

        # Open folder
        import subprocess
        import platform

        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", block_folder])
            elif platform.system() == "Darwin":
                subprocess.run(["open", block_folder])
            else:
                subprocess.run(["xdg-open", block_folder])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open folder:\n{str(e)}")

    def open_selected_assembly_folder(self):
        """Open folder for the selected Assembly block"""
        selected_items = self.scene.selectedItems()

        if not selected_items:
            QMessageBox.information(self, "Info", "Please select an Assembly block first")
            return

        # Find first selected Assembly block
        for item in selected_items:
            if isinstance(item, GraphicsBlock) and item.name == "Assembly":
                self.open_assembly_block_folder(item)
                return

        QMessageBox.warning(self, "Warning", "Selected item is not an Assembly block")

    # def show_live_camera_comparison(self, step_num, total_steps, product_name, reference_path):
    #     """Dialog 1: Reference image vs LIVE camera for visual comparison only"""
    #     # Check if we have prediction manager
    #     if not hasattr(self, 'prediction_manager'):
    #         from ui.components.prediction_manager import PredictionManager
    #         self.prediction_manager = PredictionManager()
    #
    #     # Show camera validation dialog for visual comparison
    #     camera_dialog = CameraValidationDialog(
    #         step_number=step_num,
    #         product_name=product_name,
    #         reference_image_path=reference_path,
    #         prediction_manager=self.prediction_manager,
    #         parent=self
    #     )
    #
    #     # Customize the dialog title and buttons
    #     camera_dialog.setWindowTitle(f"Step {step_num}/{total_steps}: Visual Comparison")
    #
    #     # Modify button texts if possible (depends on CameraValidationDialog implementation)
    #     # You might need to modify the CameraValidationDialog class to change button texts
    #
    #     result = camera_dialog.exec()
    #
    #     if result == QDialog.Accepted:
    #         # User clicked OK to continue
    #         return "continue"
    #     else:
    #         # User skipped or cancelled
    #         return "skip"

    def verify_assembly_completion(self, step_num, product_name, saved_image_path):
        """Dialog 2: Show saved image and ask verification"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Step {step_num}: Verify Assembly")
        dialog.setFixedSize(700, 600)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel(f"Step {step_num}: Verify Assembly Completion")
        header.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: white;
                background-color: #f39c12;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Information text
        info_label = QLabel(f"Image captured during assembly configuration:\n{product_name}")
        info_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #2c3e50;
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Show the saved image
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)

        if saved_image_path and os.path.exists(saved_image_path):
            try:
                pixmap = QPixmap(saved_image_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(500, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    image_label.setPixmap(scaled_pixmap)
                    image_label.setStyleSheet("""
                        QLabel {
                            border: 3px solid #3498db;
                            border-radius: 8px;
                            background-color: #f8f9fa;
                            padding: 5px;
                            margin: 10px;
                        }
                    """)

                    # Show file info
                    filename = os.path.basename(saved_image_path)
                    folder = os.path.basename(os.path.dirname(saved_image_path))
                    file_info = QLabel(f"📁 Location: {folder}/{filename}")
                    file_info.setStyleSheet("""
                        QLabel {
                            font-size: 12px;
                            color: #7f8c8d;
                            padding: 8px;
                            background-color: #ecf0f1;
                            border-radius: 4px;
                            margin: 5px 20px;
                        }
                    """)
                    file_info.setAlignment(Qt.AlignCenter)
                    layout.addWidget(file_info)
                else:
                    raise Exception("Cannot load image")
            except Exception as e:
                error_label = QLabel(f"❌ Cannot display image\n{str(e)}")
                error_label.setStyleSheet("""
                    QLabel {
                        color: #e74c3c;
                        font-size: 14px;
                        padding: 30px;
                        background-color: #ffebee;
                        border-radius: 8px;
                        margin: 20px;
                    }
                """)
                error_label.setAlignment(Qt.AlignCenter)
                layout.addWidget(error_label)
        else:
            missing_label = QLabel("⚠️ Saved image not found")
            missing_label.setStyleSheet("""
                QLabel {
                    color: #e74c3c;
                    font-size: 16px;
                    padding: 50px;
                    background-color: #ffebee;
                    border-radius: 8px;
                    margin: 20px;
                }
            """)
            missing_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(missing_label)

        layout.addWidget(image_label, alignment=Qt.AlignCenter)

        # Verification question
        question = QLabel(f"Is the assembly complete and correct?\n\n")
        question.setAlignment(Qt.AlignCenter)
        question.setStyleSheet("""
            QLabel {
                font-size: 15px;
                color: #2c3e50;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 8px;
                margin: 15px;
            }
        """)
        question.setWordWrap(True)
        layout.addWidget(question)

        # Buttons
        btn_layout = QHBoxLayout()

        # No button
        no_btn = QPushButton("❌ No, Not Complete")
        no_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 24px;
                background-color: #e74c3c;
                color: white;
                border-radius: 6px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        no_btn.clicked.connect(dialog.reject)

        # Yes button
        yes_btn = QPushButton("✅ Yes, Assembly Complete")
        yes_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 24px;
                background-color: #2ecc71;
                color: white;
                border-radius: 6px;
                min-width: 180px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        yes_btn.clicked.connect(dialog.accept)

        btn_layout.addWidget(no_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(yes_btn)

        layout.addLayout(btn_layout)

        result = dialog.exec()

        if result == QDialog.Accepted:
            print(f"DEBUG: Step {step_num} assembly verified as complete")
            return True
        else:
            print(f"DEBUG: Step {step_num} assembly marked as NOT complete")
            return False

    def get_latest_captured_image(self, assembly_block, step_num):
        """Get the most recent captured image for a specific Assembly block and step"""
        recipe_path = config_manager.get_current_recipe_folder()
        if not recipe_path:
            return None

        # Get block-specific folder
        if not hasattr(assembly_block, 'block_id'):
            self.assign_block_id(assembly_block)

        block_folder = os.path.join(recipe_path, "Assembly", f"Block_{assembly_block.block_id}")
        step_folder = os.path.join(block_folder, f"Step_{step_num}")

        if not os.path.exists(step_folder):
            return None

        # Look for image files
        import glob
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.JPG', '*.JPEG', '*.PNG', '*.BMP']
        all_images = []

        for ext in image_extensions:
            all_images.extend(glob.glob(os.path.join(step_folder, ext)))

        if not all_images:
            return None

        # Return the most recent file
        latest_image = max(all_images, key=os.path.getmtime)
        return latest_image

    def add_log(self, message):
        """Add log message to console (if you have one)"""
        print(f"Pipeline Log: {message}")

    # ================== Screw Block Execution ==================
    def execute_screw_block(self, screw_block, step_number, total_blocks):
        """Execute a Screw block - show information only"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Step {step_number}: Screw Operation")
        dialog.setFixedSize(500, 400)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(1)  # Reduced spacing
        layout.setContentsMargins(5, 5, 5, 5)  # Smaller margins

        # Header
        header = QLabel(f"🔩 Screw Operation - Step {step_number}")
        header.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: white;
                background-color: #f39c12;
                padding: 10px;
                border-radius: 8px;
                margin-bottom: 10px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Check if block has configuration
        if hasattr(screw_block, 'config') and screw_block.config:
            config = screw_block.config

            # Create info frame
            info_frame = QFrame()
            info_frame.setStyleSheet("""
                QFrame {
                    border: 2px solid #f39c12;
                    border-radius: 8px;
                    background-color: #fff9e6;
                    padding: 10px;
                    margin: 10px;
                }
            """)

            info_layout = QVBoxLayout(info_frame)

            # Title
            title_label = QLabel("⚙️ Screw Configuration")
            title_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: #d35400;
                    padding-bottom: 5px;
                    border-bottom: 1px solid #f39c12;
                    margin-bottom: 10px;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            info_layout.addWidget(title_label)

            # Parse configuration (handle both string and dict)
            if isinstance(config, dict):
                # Dictionary configuration
                screw_count = config.get('count', 'Not specified')
                screw_type = config.get('type', 'Not specified')
                torque = config.get('torque', 'Not specified')
                position = config.get('position', 'Not specified')
            elif isinstance(config, str):
                # Try to parse string configuration
                screw_count = "Not specified"
                screw_type = "Not specified"
                torque = "Not specified"
                position = "Not specified"

                lines = config.strip().split('\n')
                for line in lines:
                    line_lower = line.lower()
                    if 'count:' in line_lower:
                        screw_count = line.split(':')[-1].strip()
                    elif 'type:' in line_lower:
                        screw_type = line.split(':')[-1].strip()
                    elif 'torque:' in line_lower:
                        torque = line.split(':')[-1].strip()
                    elif 'position:' in line_lower:
                        position = line.split(':')[-1].strip()
            else:
                # Unknown format
                screw_count = "Unknown"
                screw_type = "Unknown"
                torque = "Unknown"
                position = "Unknown"

            # Display configuration as labels (read-only)
            info_grid = QGridLayout()
            info_grid.setSpacing(1)

            # Row 1: Screw Count
            count_label = QLabel(f"🔢 Screw Count:")
            count_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
            info_grid.addWidget(count_label, 0, 0)

            count_value = QLabel(str(screw_count))
            count_value.setStyleSheet("font-size: 14px; padding: 1px; background-color: #f8f9fa; border-radius: 4px;")
            info_grid.addWidget(count_value, 0, 1)

            # Row 2: Screw Type
            type_label = QLabel(f"⚙️ Screw Type:")
            type_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
            info_grid.addWidget(type_label, 1, 0)

            type_value = QLabel(str(screw_type))
            type_value.setStyleSheet("font-size: 14px; padding: 1px; background-color: #f8f9fa; border-radius: 4px;")
            info_grid.addWidget(type_value, 1, 1)

            # Row 3: Torque
            torque_label = QLabel(f"💪 Torque Setting:")
            torque_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
            info_grid.addWidget(torque_label, 2, 0)

            torque_value = QLabel(str(torque))
            torque_value.setStyleSheet("font-size: 14px; padding: 1px; background-color: #f8f9fa; border-radius: 4px;")
            info_grid.addWidget(torque_value, 2, 1)

            # Row 4: Position
            position_label = QLabel(f"📍 Screw Positions:")
            position_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
            info_grid.addWidget(position_label, 3, 0)

            position_value = QLabel(str(position))
            position_value.setStyleSheet(
                "font-size: 14px; padding: 1px; background-color: #f8f9fa; border-radius: 4px;")
            position_value.setWordWrap(True)
            info_grid.addWidget(position_value, 3, 1)

            info_layout.addLayout(info_grid)
            info_layout.addStretch()

            layout.addWidget(info_frame)

        else:
            # No configuration
            warning_frame = QFrame()
            warning_frame.setStyleSheet("""
                QFrame {
                    border: 2px dashed #e74c3c;
                    border-radius: 8px;
                    background-color: #ffebee;
                    padding: 30px;
                    margin: 20px;
                }
            """)

            warning_layout = QVBoxLayout(warning_frame)

            warning_label = QLabel("⚠️ No Configuration Found")
            warning_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: #c0392b;
                    text-align: center;
                }
            """)

            warning_text = QLabel(
                "This Screw block has not been configured.\n\nConfigure it in the flow editor before running pipeline.")
            warning_text.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    color: #7f8c8d;
                    text-align: center;
                    margin-top: 10px;
                }
            """)
            warning_text.setWordWrap(True)

            warning_layout.addWidget(warning_label)
            warning_layout.addWidget(warning_text)

            layout.addWidget(warning_frame)

        # Instructions section
        instructions_frame = QFrame()
        instructions_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #bdc3c7;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 15px;
                margin: 10px;
            }
        """)

        instructions_layout = QVBoxLayout(instructions_frame)

        instructions_title = QLabel("📋 Instructions:")
        instructions_title.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                padding-bottom: 5px;
                border-bottom: 1px solid #dfe6e9;
                margin-bottom: 10px;
            }
        """)

        instructions_text = QLabel(
            "1. Prepare the screwdriver/tool\n"
            "2. Position at specified locations\n"
            "3. Apply correct torque\n"
            "4. Verify tightness\n"
            "5. Check alignment"
        )
        instructions_text.setStyleSheet("font-size: 13px; color: #7f8c8d;")

        instructions_layout.addWidget(instructions_title)
        instructions_layout.addWidget(instructions_text)

        layout.addWidget(instructions_frame)

        # OK button (only for closing, no editing)
        ok_btn = QPushButton("✅ OK - Continue")
        ok_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 24px;
                background-color: #2ecc71;
                color: white;
                border-radius: 6px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)

        dialog.exec()

    # ================== Generic Block Execution ==================
    def execute_generic_block(self, block, step_number, total_blocks):
        """Execute a generic block - show basic information"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Step {step_number}: {block.name}")
        dialog.setFixedSize(400, 300)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel(f"{block.name} - Step {step_number}")
        header.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Block information
        info_label = QLabel(f"Executing: {block.name}\n\n"
                            f"Step {step_number} of {total_blocks}")
        info_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #2c3e50;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 8px;
                margin: 10px;
            }
        """)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Show configuration if exists
        if hasattr(block, 'config') and block.config:
            config_label = QLabel(f"Configuration:\n{block.config}")
            config_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #7f8c8d;
                    padding: 10px;
                    background-color: #ecf0f1;
                    border-radius: 6px;
                    margin: 10px;
                }
            """)
            config_label.setWordWrap(True)
            layout.addWidget(config_label)

        # OK button
        ok_btn = QPushButton("OK - Continue")
        ok_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 24px;
                background-color: #3498db;
                color: white;
                border-radius: 6px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)

        dialog.exec()

    def view_assembly_configuration(self, assembly_block):
        """View/Edit Assembly block configuration"""
        if not hasattr(assembly_block, 'assembly_data') or not assembly_block.assembly_data:
            reply = QMessageBox.question(self, "Configure Assembly",
                                         f"Assembly Block {assembly_block.block_id} has no configuration.\n\n"
                                         "Would you like to configure it now?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.configure_assembly_block(assembly_block)
            return

        # Show current configuration and ask what to do
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Assembly Block {assembly_block.block_id}")
        dialog.setFixedSize(600, 500)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel(f"📋 Assembly Block {assembly_block.block_id} - Configuration")
        header.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Configuration summary
        config = assembly_block.assembly_data
        total_steps = config.get('total_steps', 0)

        # Create scroll area for long configurations
        scroll_area = QWidget()
        scroll_layout = QVBoxLayout(scroll_area)

        if total_steps == 0:
            summary_label = QLabel("⚠️ No steps configured")
            summary_label.setStyleSheet("""
                QLabel {
                    color: #e74c3c;
                    font-size: 16px;
                    padding: 20px;
                    background-color: #ffebee;
                    border-radius: 8px;
                    margin: 10px;
                }
            """)
            summary_label.setAlignment(Qt.AlignCenter)
            scroll_layout.addWidget(summary_label)
        else:
            # Show configuration details
            details_label = QLabel(f"Current Configuration: {total_steps} step(s)")
            details_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    font-weight: bold;
                    color: #2c3e50;
                    padding: 10px;
                    background-color: #ecf0f1;
                    border-radius: 6px;
                    margin-bottom: 10px;
                }
            """)
            details_label.setAlignment(Qt.AlignCenter)
            scroll_layout.addWidget(details_label)

            # Show each step
            selections = config.get('selections', {})

            for step_num in range(1, total_steps + 1):
                step_key = str(step_num)
                step_data = selections.get(step_key, {}) if not isinstance(selections.get('selections'), dict) else \
                    selections.get('selections', {}).get(step_key, {})

                if step_data:
                    product_data = step_data.get('product_data', {})
                    product_name = product_data.get('name', f'Product {step_num}')

                    # Create step frame
                    step_frame = QFrame()
                    step_frame.setStyleSheet("""
                        QFrame {
                            border: 2px solid #3498db;
                            border-radius: 8px;
                            background-color: #f8f9fa;
                            margin: 5px;
                            padding: 10px;
                        }
                    """)

                    step_layout = QVBoxLayout(step_frame)

                    # Step header
                    step_header = QLabel(f"Step {step_num}: {product_name}")
                    step_header.setStyleSheet("""
                        QLabel {
                            font-weight: bold;
                            font-size: 14px;
                            color: #2c3e50;
                            padding-bottom: 5px;
                        }
                    """)
                    step_layout.addWidget(step_header)

                    # Step details
                    details_text = f"Product: {product_name}\n"

                    # Check for captured image
                    captured_path = step_data.get('captured_image_path')
                    if captured_path and os.path.exists(captured_path):
                        details_text += f"Image: ✅ Captured\n"
                        details_text += f"Path: {os.path.basename(os.path.dirname(captured_path))}/{os.path.basename(captured_path)}"
                    else:
                        details_text += f"Image: ❌ Not captured"

                    details_label = QLabel(details_text)
                    details_label.setStyleSheet("""
                        QLabel {
                            font-size: 12px;
                            color: #7f8c8d;
                            padding: 8px;
                            background-color: white;
                            border-radius: 4px;
                            border: 1px solid #dfe6e9;
                        }
                    """)
                    details_label.setWordWrap(True)
                    step_layout.addWidget(details_label)

                    scroll_layout.addWidget(step_frame)

        scroll_layout.addStretch()

        # Add scroll area to main layout
        layout.addWidget(scroll_area)

        # Button layout
        btn_layout = QHBoxLayout()

        # View Images button
        view_images_btn = QPushButton("👁️ View Images")
        view_images_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 10px 20px;
                background-color: #9b59b6;
                color: white;
                border-radius: 6px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        view_images_btn.clicked.connect(lambda: self.view_assembly_images(assembly_block))

        # Edit button
        edit_btn = QPushButton("✏️ Edit Configuration")
        edit_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 10px 20px;
                background-color: #3498db;
                color: white;
                border-radius: 6px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        edit_btn.clicked.connect(lambda: self.edit_assembly_configuration(dialog, assembly_block))

        # Close button
        close_btn = QPushButton("✕ Close")
        close_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 10px 20px;
                background-color: #95a5a6;
                color: white;
                border-radius: 6px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        close_btn.clicked.connect(dialog.reject)

        btn_layout.addWidget(view_images_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dialog.exec()

    def view_assembly_images(self, assembly_block):
        """View captured images for assembly block"""
        if not hasattr(assembly_block, 'assembly_data') or not assembly_block.assembly_data:
            QMessageBox.information(self, "No Images", "No configuration found for this block.")
            return

        config = assembly_block.assembly_data
        total_steps = config.get('total_steps', 0)

        if total_steps == 0:
            QMessageBox.information(self, "No Steps", "No steps configured for this block.")
            return

        # Create image viewer dialog
        viewer = QDialog(self)
        viewer.setWindowTitle(f"Assembly Block {assembly_block.block_id} - Captured Images")
        viewer.setMinimumSize(800, 600)

        layout = QVBoxLayout(viewer)

        # Tab widget for each step
        tab_widget = QTabWidget()

        selections = config.get('selections', {})
        step_selections = selections.get('selections', {}) if isinstance(selections,
                                                                         dict) and 'selections' in selections else selections

        for step_num in range(1, total_steps + 1):
            step_key = str(step_num)
            step_data = step_selections.get(step_key, {})

            if step_data:
                product_data = step_data.get('product_data', {})
                product_name = product_data.get('name', f'Product {step_num}')

                # Create tab for this step
                tab = QWidget()
                tab_layout = QVBoxLayout(tab)

                # Tab title with product name
                tab_title = QLabel(f"Step {step_num}: {product_name}")
                tab_title.setStyleSheet("""
                    QLabel {
                        font-size: 16px;
                        font-weight: bold;
                        color: #2c3e50;
                        padding: 10px;
                        background-color: #ecf0f1;
                        border-radius: 6px;
                        margin-bottom: 10px;
                    }
                """)
                tab_title.setAlignment(Qt.AlignCenter)
                tab_layout.addWidget(tab_title)

                # Check for captured image
                captured_path = step_data.get('captured_image_path')
                if captured_path and os.path.exists(captured_path):
                    image_label = QLabel()
                    pixmap = QPixmap(captured_path)

                    if not pixmap.isNull():
                        # Scale image to fit
                        scaled_pixmap = pixmap.scaled(700, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        image_label.setPixmap(scaled_pixmap)

                        # Image info
                        info_text = f"File: {os.path.basename(captured_path)}\n"
                        info_text += f"Size: {pixmap.width()}x{pixmap.height()} pixels\n"
                        info_text += f"Modified: {datetime.fromtimestamp(os.path.getmtime(captured_path)).strftime('%Y-%m-%d %H:%M:%S')}"

                        info_label = QLabel(info_text)
                        info_label.setStyleSheet("""
                            QLabel {
                                font-size: 12px;
                                color: #7f8c8d;
                                padding: 10px;
                                background-color: #f8f9fa;
                                border-radius: 6px;
                                margin-top: 10px;
                            }
                        """)
                        info_label.setAlignment(Qt.AlignCenter)

                        tab_layout.addWidget(image_label, alignment=Qt.AlignCenter)
                        tab_layout.addWidget(info_label)
                    else:
                        error_label = QLabel("❌ Cannot load image")
                        error_label.setStyleSheet("""
                            QLabel {
                                color: #e74c3c;
                                font-size: 16px;
                                padding: 50px;
                            }
                        """)
                        error_label.setAlignment(Qt.AlignCenter)
                        tab_layout.addWidget(error_label)
                else:
                    no_image_label = QLabel("⚠️ No image captured for this step")
                    no_image_label.setStyleSheet("""
                        QLabel {
                            color: #f39c12;
                            font-size: 16px;
                            padding: 50px;
                            background-color: #fef9e7;
                            border-radius: 8px;
                            margin: 20px;
                        }
                    """)
                    no_image_label.setAlignment(Qt.AlignCenter)
                    tab_layout.addWidget(no_image_label)

                tab_layout.addStretch()
                tab_widget.addTab(tab, f"Step {step_num}")

        layout.addWidget(tab_widget)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 10px 20px;
                background-color: #3498db;
                color: white;
                border-radius: 6px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        close_btn.clicked.connect(viewer.accept)
        layout.addWidget(close_btn)

        viewer.exec()

    def edit_assembly_configuration(self, parent_dialog, assembly_block):
        """Edit assembly configuration"""
        parent_dialog.accept()  # Close the view dialog

        # Open configuration dialog
        self.configure_assembly_block(assembly_block)

    # ================== Save Flow ==================
    def save_flow(self):
        """Save current flow to current recipe folder"""
        if not config_manager.current_recipe:
            QMessageBox.warning(self, "⚠️ Warning", "Please select a recipe first!")
            return

        # Create save data
        flow_data = {
            "recipe": config_manager.current_recipe,
            "saved_at": datetime.now().isoformat(),
            "blocks": [],
            "connections": []
        }

        # Assign IDs to Assembly blocks before saving
        assembly_count = 0
        for block in self.pipeline_blocks:
            if block.name == "Assembly":
                if not hasattr(block, 'block_id'):
                    self.assign_block_id(block)
                assembly_count += 1

        print(f"DEBUG: Saving {assembly_count} Assembly blocks with IDs")

        # Save pipeline blocks
        for block in self.pipeline_blocks:
            block_data = {
                "name": block.name,
                "x": block.pos().x(),
                "y": block.pos().y(),
                "config": block.config if hasattr(block, 'config') else None
            }

            # Save Assembly block ID and data
            if block.name == "Assembly":
                if hasattr(block, 'block_id'):
                    block_data["block_id"] = block.block_id
                    print(f"DEBUG: Saving block_id {block.block_id} for {block.name}")

                if hasattr(block, 'assembly_data') and block.assembly_data:
                    # CRITICAL: Ensure we save the complete assembly_data structure
                    block_data["assembly_data"] = block.assembly_data

                    # Debug print to see what's being saved
                    if 'selections' in block.assembly_data:
                        selections = block.assembly_data['selections']
                        print(f"DEBUG: Saving selections structure for block {block.block_id}:")
                        print(f"  Type: {type(selections)}")
                        if isinstance(selections, dict):
                            print(f"  Keys: {list(selections.keys())}")
                            for key, value in selections.items():
                                if key != 'total_steps':
                                    print(f"  Step {key}: {value.get('product_name', 'Unknown')}")

            flow_data["blocks"].append(block_data)

        # Save connections (existing code remains same)
        for conn in self.connections:
            if hasattr(conn, 'from_block') and hasattr(conn, 'to_block'):
                try:
                    from_index = self.pipeline_blocks.index(conn.from_block)
                    to_index = self.pipeline_blocks.index(conn.to_block)
                    conn_data = {
                        "from_block": from_index,
                        "to_block": to_index
                    }
                    flow_data["connections"].append(conn_data)
                except ValueError:
                    pass  # Skip invalid connections

        # Save to file
        flows_folder = os.path.join(config_manager.get_current_recipe_folder(), "flows")
        if flows_folder:
            os.makedirs(flows_folder, exist_ok=True)
            flow_file = os.path.join(flows_folder, "pipeline_flow.json")

            try:
                with open(flow_file, 'w') as f:
                    json.dump(flow_data, f, indent=2)
                print(f"DEBUG: Successfully saved flow to {flow_file}")
                QMessageBox.information(self, "✅ Success",
                                        f"Flow saved to:\n{flow_file}")
            except Exception as e:
                QMessageBox.critical(self, "❌ Error", f"Failed to save flow:\n{str(e)}")
                import traceback
                traceback.print_exc()
        else:
            QMessageBox.warning(self, "⚠️ Warning", "Could not determine flows folder")

    # ================== Load Flow ==================
    def on_load_flow_clicked(self):
        """Handle load flow button click"""
        try:
            # Get the current flows folder
            flows_folder = self.get_current_flows_folder()

            # Open file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Load Flow",
                flows_folder if flows_folder else "",
                "JSON Files (*.json);;All Files (*.*)"
            )

            if not file_path:
                return  # User cancelled

            # Check if file exists
            if not os.path.exists(file_path):
                QMessageBox.warning(
                    self,
                    "File Not Found",
                    f"Flow file not found:\n{file_path}"
                )
                return

            # Load and validate the file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    flow_data = json.load(f)

                # Validate that we loaded a dictionary
                if not isinstance(flow_data, dict):
                    QMessageBox.critical(
                        self,
                        "Invalid Format",
                        f"Flow file does not contain a valid configuration.\n"
                        f"Expected a JSON object, got {type(flow_data).__name__}."
                    )
                    return

                # ✅ FIX: Add file path to flow data for reference
                flow_data['file_path'] = file_path

                # Clear current flow before loading new one
                self.clear_flow_area()

                # ✅ FIX: Call load_flow with the flow_data dictionary
                success = self.load_flow(flow_data)  # ← Now passing the dictionary

                if success:
                    # Update Assembly block displays
                    self.update_assembly_block_displays()

                    QMessageBox.information(
                        self,
                        "✅ Load Successful",
                        f"Flow loaded successfully from:\n{os.path.basename(file_path)}"
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "❌ Load Failed",
                        f"Failed to load flow from:\n{os.path.basename(file_path)}\n\n"
                        f"Check the console for details."
                    )

            except json.JSONDecodeError as e:
                QMessageBox.critical(
                    self,
                    "Invalid JSON",
                    f"Flow file contains invalid JSON:\n{str(e)}"
                )
            except PermissionError:
                QMessageBox.critical(
                    self,
                    "Permission Denied",
                    f"Cannot read file:\n{file_path}\n\n"
                    f"Check file permissions."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Load Failed",
                    f"Failed to load flow:\n{str(e)}"
                )
                import traceback
                traceback.print_exc()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Unexpected error:\n{str(e)}"
            )
            import traceback
            traceback.print_exc()

    def load_flow(self, flow_data):
        """Load flow from data dictionary"""
        # ✅ CRITICAL DEBUGGING - SHOW EXACT CALLER
        print("\n" + "=" * 80)
        print("🔍 LOAD_FLOW CALLED")
        print(f"📥 Parameter type: {type(flow_data)}")
        print(f"📥 Parameter value: {flow_data}")
        print("\n📋 FULL CALL STACK:")
        import traceback
        stack = traceback.format_stack()
        for i, frame in enumerate(stack):
            print(f"  {i}: {frame.strip()}")
        print("=" * 80 + "\n")

        if isinstance(flow_data, bool):
            print(f"❌ CRITICAL ERROR: load_flow called with boolean: {flow_data}")
            print(f"❌ This should never happen!")
            return False

        if self._is_loading:
            print("⚠️ Already loading a flow, skipping...")
            return False

        self._is_loading = True
        try:
            # Check if flow_data is a dictionary
            if isinstance(flow_data, bool):
                print(f"❌ CRITICAL ERROR: load_flow called with boolean: {flow_data}")
                print(f"❌ Stack trace:")
                import traceback
                traceback.print_stack()
                return False

            if not isinstance(flow_data, dict):
                print(f"❌ Error: flow_data is {type(flow_data)}, expected dict")
                if isinstance(flow_data, bool):
                    print(
                        f"❌ Received boolean value: {flow_data} - this usually means the wrong value was passed to load_flow")
                return False

            print("\n" + "=" * 60)
            print(f"✅ Loading flow from {flow_data.get('file_path', 'memory')}")
            print(f"✅ Flow data type: {type(flow_data)}")
            print(f"✅ Flow keys: {list(flow_data.keys())}")
            print("=" * 60 + "\n")

            # Clear existing blocks
            self.clear_flow_area()

            # Reset block ID counter
            self.next_block_id = 1

            # Load blocks - handle both old and new format
            blocks_data = []

            # Handle different flow data structures
            if 'blocks' in flow_data:
                # New format: {"blocks": [...]}
                blocks_data = flow_data['blocks']
                print(f"Found {len(blocks_data)} blocks in 'blocks' array")
            elif isinstance(flow_data, list):
                # Old format: directly a list of blocks
                blocks_data = flow_data
                print(f"Found {len(blocks_data)} blocks in root array")
            else:
                print("⚠️ No blocks found in flow data")
                return True

            if not blocks_data:
                print("⚠️ No blocks found in flow data")
                return True

            # Load each block
            for block_info in blocks_data:
                # Check if block_info is a dictionary
                if not isinstance(block_info, dict):
                    print(f"⚠️ Skipping invalid block data: {block_info}")
                    continue

                block_name = block_info.get('name', 'Unknown')
                block_id = block_info.get('block_id', str(self.next_block_id))

                # Get position - with default values
                x = block_info.get('x', 100)
                y = block_info.get('y', 100)

                print(f"Loading block {self.next_block_id}: {block_name} at ({x}, {y})")

                # Create block based on name
                if block_name == "Assembly":
                    block = GraphicsBlock(
                        name=block_name,
                        action=None,
                        x=x,
                        y=y,
                        w=220,
                        h=44,
                        is_left_block=False,
                        block_id=block_id,
                        block_type="assembly"
                    )

                    # ✅ CRITICAL FIX: Restore assembly_data properly
                    if 'assembly_data' in block_info and block_info['assembly_data']:
                        block.assembly_data = block_info['assembly_data']
                        print(f"  ✅ Restored assembly_data with {block.assembly_data.get('total_steps', 0)} steps")
                    elif 'config' in block_info and block_info['config']:
                        # Try config as fallback
                        block.assembly_data = block_info['config']
                        print(f"  ⚠️ Restored from config with {block.assembly_data.get('total_steps', 0)} steps")

                    # Set block_id
                    block.block_id = block_id

                    # Update appearance
                    if hasattr(block, 'update_block_appearance'):
                        block.update_block_appearance()

                    # Update text
                    if hasattr(block, 'text'):
                        total_steps = block.assembly_data.get('total_steps', 0) if block.assembly_data else 0
                        if total_steps > 0:
                            block.text.setPlainText(f"Assembly (Block {block_id}, {total_steps} steps)")
                        else:
                            block.text.setPlainText(f"Assembly (Block {block_id})")

                        # Re-center text
                        text_rect = block.text.boundingRect()
                        text_x = (block.block_width - text_rect.width()) / 2
                        text_y = (block.block_height - text_rect.height()) / 2
                        block.text.setPos(text_x, text_y)

                elif block_name == "Screw":
                    block = GraphicsBlock(
                        name=block_name,
                        action=None,
                        x=x,
                        y=y,
                        w=220,
                        h=44,
                        is_left_block=False,
                        block_id=block_id,
                        block_type="screw"
                    )

                    # Restore config
                    if 'config' in block_info:
                        block.config = block_info['config']

                elif block_name == "End":
                    block = GraphicsBlock(
                        name=block_name,
                        action=None,
                        x=x,
                        y=y,
                        w=220,
                        h=44,
                        is_left_block=False,
                        block_id=block_id,
                        block_type="end"
                    )
                else:
                    print(f"⚠️ Unknown block type: {block_name}")
                    continue

                # Add block to scene
                self.scene.addItem(block)

                # Store in blocks list
                if not hasattr(self, 'pipeline_blocks'):
                    self.pipeline_blocks = []
                self.pipeline_blocks.append(block)

                # Update next_block_id
                try:
                    if int(block_id) >= self.next_block_id:
                        self.next_block_id = int(block_id) + 1
                except (ValueError, TypeError):
                    pass

            # Load connections
            if 'connections' in flow_data:
                connections_data = flow_data['connections']
                print(f"Loading {len(connections_data)} connections")

                for conn_info in connections_data:
                    if isinstance(conn_info, dict):
                        self.load_connection(conn_info)

            print(
                f"\n✅ Loaded {len(self.pipeline_blocks)} blocks and {len(connections_data) if 'connections' in flow_data else 0} connections")

            # Update button states
            self.update_buttons_state()

            return True

        except Exception as e:
            print(f"\n❌ Error loading flow: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_connection(self, conn_info):
        """Load a connection from saved data"""
        try:
            from_index = conn_info.get('from_block')
            to_index = conn_info.get('to_block')

            # Check if indices are valid
            if from_index is None or to_index is None:
                print(f"    Invalid connection data: missing indices")
                return False

            if from_index >= len(self.pipeline_blocks) or to_index >= len(self.pipeline_blocks):
                print(f"    Invalid connection indices: {from_index} -> {to_index}")
                return False

            from_block = self.pipeline_blocks[from_index]
            to_block = self.pipeline_blocks[to_index]

            # Don't connect a block to itself
            if from_block == to_block:
                print(f"    Skipping self-connection")
                return False

            # Create the connection
            connection = ConnectionLine(from_block, to_block, self.scene)
            self.scene.addItem(connection)
            self.connections.append(connection)

            # Update block connection lists
            if not hasattr(from_block, 'output_connections'):
                from_block.output_connections = []
            if not hasattr(to_block, 'input_connections'):
                to_block.input_connections = []

            from_block.output_connections.append(connection)
            to_block.input_connections.append(connection)

            connection.from_block = from_block
            connection.to_block = to_block

            # Update the connection position
            connection.update_position()

            print(f"    Loaded connection: {from_block.name} (idx:{from_index}) -> {to_block.name} (idx:{to_index})")
            return True

        except Exception as e:
            print(f"    Error loading connection: {e}")
            return False

    def auto_load_flow(self):
        """Automatically load flow from the current recipe's flows folder"""
        if not config_manager.current_recipe:
            QMessageBox.warning(self, "⚠️ Warning", "Please select a recipe first!")
            return

        # Get the flow file path
        flows_folder = self.get_current_flows_folder()
        if not flows_folder:
            QMessageBox.warning(self, "⚠️ Warning", "Could not determine flows folder!")
            return

        flow_file = os.path.join(flows_folder, "pipeline_flow.json")

        # Check if file exists
        if not os.path.exists(flow_file):
            QMessageBox.warning(
                self,
                "No Flow Found",
                f"No saved flow found for recipe '{config_manager.current_recipe}'.\n\n"
                f"Expected file: {flow_file}"
            )
            return

        try:
            # Load and parse the JSON file
            with open(flow_file, 'r', encoding='utf-8') as f:
                flow_data = json.load(f)

            # Add file path for reference
            flow_data['file_path'] = flow_file

            # Clear current flow before loading
            self.clear_flow_area()

            # Load the flow
            success = self.load_flow(flow_data)

            if success:
                # Update Assembly block displays
                self.update_assembly_block_displays()

                QMessageBox.information(
                    self,
                    "✅ Load Successful",
                    f"Flow loaded successfully from:\n{os.path.basename(flow_file)}"
                )
            else:
                QMessageBox.critical(
                    self,
                    "❌ Load Failed",
                    f"Failed to load flow from:\n{os.path.basename(flow_file)}\n\n"
                    f"Check the console for details."
                )

        except json.JSONDecodeError as e:
            QMessageBox.critical(
                self,
                "Invalid JSON",
                f"Flow file contains invalid JSON:\n{str(e)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Failed",
                f"Failed to load flow:\n{str(e)}"
            )
            import traceback
            traceback.print_exc()

    def get_current_flows_folder(self):
        """Get the flows folder for current recipe"""
        if not config_manager.current_recipe:
            return ""

        recipe_folder = config_manager.get_current_recipe_folder()
        if recipe_folder:
            flows_folder = os.path.join(recipe_folder, "flows")
            os.makedirs(flows_folder, exist_ok=True)
            return flows_folder

        return ""

    def clear_flow_area(self):
        """Clear all blocks and connections from the pipeline area"""
        # Remove all pipeline blocks
        if hasattr(self, 'pipeline_blocks'):
            for block in list(self.pipeline_blocks):
                if block in self.scene.items():
                    self.scene.removeItem(block)
            self.pipeline_blocks.clear()

        # Remove all connections
        if hasattr(self, 'connections'):
            for conn in list(self.connections):
                if conn in self.scene.items():
                    self.scene.removeItem(conn)
            self.connections.clear()

        # Reset next_block_id
        self.next_block_id = 1

        print("✅ Cleared flow area")

    # In EditFlowPage, after adding/removing connections
    def update_all_connection_status(self):
        for block in self.pipeline_blocks:
            if hasattr(block, 'update_visual_connection_status'):
                block.update_visual_connection_status()

    def validate_assembly_config(self, config):
        """Validate assembly configuration structure"""
        if not isinstance(config, dict):
            print(f"    Config is not a dict: {type(config)}")
            return False

        # Check for required keys
        required_keys = ['total_steps', 'selections', 'block_id']
        for key in required_keys:
            if key not in config:
                print(f"    Missing required key: {key}")
                return False

        # Validate selections
        selections = config.get('selections', {})
        if not isinstance(selections, dict):
            print(f"    selections is not a dict: {type(selections)}")
            return False

        # Check if selections contains actual step data or just metadata
        has_step_keys = False
        for key in selections.keys():
            if key.isdigit():  # Step keys should be numbers
                has_step_keys = True
                break

        if not has_step_keys:
            print(f"    No step keys found in selections")
            # Check if it's the new nested structure
            if 'total_steps' in selections and 'selections' in selections:
                step_selections = selections.get('selections', {})
                if isinstance(step_selections, dict):
                    for step_key in step_selections.keys():
                        if step_key.isdigit():
                            has_step_keys = True
                            break

        if not has_step_keys:
            print(f"    No valid step data found")
            return False

        return True

    def clean_assembly_config(self, config, block_id):
        """Clean and normalize assembly configuration"""
        if not config:
            return {
                'total_steps': 0,
                'selections': {},
                'block_id': block_id,
                'block_name': f"Block_{block_id}"
            }

        cleaned_config = config.copy()

        # Ensure block_id is correct
        cleaned_config['block_id'] = block_id

        # Ensure block_name exists
        if 'block_name' not in cleaned_config:
            cleaned_config['block_name'] = f"Block_{block_id}"

        # Handle selections structure
        selections = cleaned_config.get('selections', {})

        if not isinstance(selections, dict):
            cleaned_config['selections'] = {}
            return cleaned_config

        # Check if it's the new nested structure
        if 'total_steps' in selections and 'selections' in selections:
            # It's the new structure: selections contains 'total_steps' and nested 'selections'
            total_steps = selections.get('total_steps', 0)
            step_selections = selections.get('selections', {})

            # Update the config to use the flat structure
            cleaned_config['total_steps'] = total_steps
            cleaned_config['selections'] = step_selections

            print(f"    Converted nested structure to flat: {total_steps} steps")

        # Clean selections - remove non-step keys
        clean_selections = {}
        total_steps = 0

        for key, value in cleaned_config.get('selections', {}).items():
            if key.isdigit():  # Only keep numeric keys (step numbers)
                step_num = int(key)
                total_steps = max(total_steps, step_num)

                if isinstance(value, dict):
                    clean_selections[key] = value
                else:
                    # If value is not a dict, create basic structure
                    clean_selections[key] = {
                        'product_id': f'Unknown_{key}',
                        'product_data': {'name': f'Step {key}'},
                        'capture_info': {}
                    }

        # Remove non-step keys like 'block_id', 'block_name', 'total_steps' from selections
        cleaned_config['selections'] = clean_selections

        # Update total_steps if needed
        if 'total_steps' not in cleaned_config or cleaned_config['total_steps'] < total_steps:
            cleaned_config['total_steps'] = total_steps

        print(f"    Cleaned config: {total_steps} valid steps")

        # Validate each step has required structure
        for step_key, step_data in clean_selections.items():
            if not isinstance(step_data, dict):
                clean_selections[step_key] = {
                    'product_id': f'Unknown_{step_key}',
                    'product_data': {'name': f'Step {step_key}'},
                    'capture_info': {}
                }
            else:
                # Ensure required fields exist
                if 'product_id' not in step_data:
                    step_data['product_id'] = f'Unknown_{step_key}'
                if 'product_data' not in step_data:
                    step_data['product_data'] = {'name': f'Step {step_key}'}
                if 'capture_info' not in step_data:
                    step_data['capture_info'] = {}

        return cleaned_config

    def reconstruct_assembly_data(self, assembly_block):
        """Reconstruct assembly data with captured image paths after loading"""
        if not hasattr(assembly_block, 'assembly_data') or not assembly_block.assembly_data:
            print(f"    No assembly_data to reconstruct")
            return

        if not hasattr(assembly_block, 'block_id'):
            self.assign_block_id(assembly_block)

        assembly_data = assembly_block.assembly_data
        selections = assembly_data.get('selections', {})
        total_steps = assembly_data.get('total_steps', 0)

        print(f"    Reconstructing paths for block {assembly_block.block_id}, {total_steps} steps")

        if not selections or total_steps == 0:
            print(f"    No steps to reconstruct")
            return

        reconstructed_count = 0

        # Check each step folder for images
        for step_num in range(1, total_steps + 1):
            step_key = str(step_num)

            if step_key not in selections:
                # Create empty step data if missing
                selections[step_key] = {
                    'product_id': f'Unknown_{step_key}',
                    'product_data': {'name': f'Step {step_key}'},
                    'capture_info': {}
                }

            step_data = selections[step_key]

            if not isinstance(step_data, dict):
                # Fix if step_data is not a dict
                selections[step_key] = {
                    'product_id': f'Unknown_{step_key}',
                    'product_data': {'name': f'Step {step_key}'},
                    'capture_info': {}
                }
                step_data = selections[step_key]

            # Get product name for logging
            product_name = step_data.get('product_data', {}).get('name', f'Step {step_num}')

            # Only reconstruct if path doesn't exist or is invalid
            current_path = step_data.get('captured_image_path')

            # Check if the step folder exists
            step_folder = self.get_assembly_step_folder(assembly_block, step_num)
            if not step_folder or not os.path.exists(step_folder):
                print(f"      Step {step_num}: No step folder found")
                # Create the step folder
                step_folder = self.get_assembly_step_folder(assembly_block, step_num)
                if step_folder:
                    print(f"      Created step folder: {step_folder}")
                continue

            if not current_path or not os.path.exists(current_path):
                # Find captured image path from disk
                captured_path = self.get_captured_image_path(assembly_block, step_num, product_name)

                if captured_path and os.path.exists(captured_path):
                    step_data['captured_image_path'] = captured_path
                    reconstructed_count += 1
                    print(f"      Step {step_num}: Reconstructed path -> {os.path.basename(captured_path)}")
                else:
                    # Check for any image in step folder
                    import glob
                    step_folder = self.get_assembly_step_folder(assembly_block, step_num)
                    if step_folder and os.path.exists(step_folder):
                        image_patterns = [os.path.join(step_folder, "*.jpg"),
                                          os.path.join(step_folder, "*.jpeg"),
                                          os.path.join(step_folder, "*.png"),
                                          os.path.join(step_folder, "*.bmp"),
                                          os.path.join(step_folder, "*.JPG"),
                                          os.path.join(step_folder, "*.JPEG"),
                                          os.path.join(step_folder, "*.PNG"),
                                          os.path.join(step_folder, "*.BMP")]

                        image_files = []
                        for pattern in image_patterns:
                            image_files.extend(glob.glob(pattern))

                        if image_files:
                            # Use the most recent image
                            image_files.sort(key=os.path.getmtime, reverse=True)
                            latest_image = image_files[0]
                            step_data['captured_image_path'] = latest_image
                            reconstructed_count += 1
                            print(f"      Step {step_num}: Found image -> {os.path.basename(latest_image)}")
                        else:
                            print(f"      Step {step_num}: No image found in step folder")
            else:
                print(f"      Step {step_num}: Path already exists -> {os.path.basename(current_path)}")

        print(f"    Total paths reconstructed: {reconstructed_count}/{total_steps}")

    def reconstruct_assembly_data(self, assembly_block):
        """Reconstruct assembly data with captured image paths after loading"""
        if not hasattr(assembly_block, 'assembly_data') or not assembly_block.assembly_data:
            return

        if not hasattr(assembly_block, 'block_id'):
            self.assign_block_id(assembly_block)

        assembly_data = assembly_block.assembly_data
        selections = assembly_data.get('selections', {})

        # Check the structure
        if isinstance(selections, dict):
            # New structure: selections contains 'total_steps' and 'selections'
            if 'total_steps' in selections:
                total_steps = selections.get('total_steps', 0)
                step_selections = selections.get('selections', {})

                # Reconstruct paths for each step
                for step_num in range(1, total_steps + 1):
                    step_key = str(step_num)
                    if step_key in step_selections:
                        step_data = step_selections[step_key]

                        # Find captured image path
                        captured_path = self.get_captured_image_path(assembly_block, step_num,
                                                                     step_data.get('product_name', ''))
                        if captured_path and os.path.exists(captured_path):
                            step_data['captured_image_path'] = captured_path
                            print(f"DEBUG: Reconstructed path for step {step_num}: {captured_path}")

            # Old structure: selections is directly the step dictionary
            else:
                for step_key, step_data in selections.items():
                    if isinstance(step_data, dict):
                        step_num = int(step_key) if step_key.isdigit() else 0
                        if step_num > 0:
                            captured_path = self.get_captured_image_path(assembly_block, step_num,
                                                                         step_data.get('product_name', ''))
                            if captured_path and os.path.exists(captured_path):
                                step_data['captured_image_path'] = captured_path
                                print(f"DEBUG: Reconstructed path for step {step_key}: {captured_path}")

    def _verify_loaded_data(self):
        """Verify that all configuration data was loaded correctly"""
        print("\n=== DETAILED DATA VERIFICATION ===")

        for i, block in enumerate(self.pipeline_blocks):
            print(f"\nBlock {i}: {block.name}")

            if block.name == "Assembly":
                print(f"  Block ID: {getattr(block, 'block_id', 'Not set')}")
                print(f"  Has assembly_data: {hasattr(block, 'assembly_data')}")

                if hasattr(block, 'assembly_data') and block.assembly_data:
                    data = block.assembly_data
                    print(f"  assembly_data type: {type(data)}")
                    print(f"  Keys: {list(data.keys())}")

                    if 'total_steps' in data:
                        print(f"  Total steps: {data['total_steps']}")

                    if 'selections' in data:
                        selections = data['selections']
                        print(f"  selections type: {type(selections)}")

                        if isinstance(selections, dict):
                            # Count valid step keys
                            step_keys = [k for k in selections.keys() if k.isdigit()]
                            print(f"    Valid step keys: {len(step_keys)}")

                            # Show each step
                            for step_key in sorted(step_keys, key=lambda x: int(x)):
                                step_data = selections[step_key]
                                if isinstance(step_data, dict):
                                    product_id = step_data.get('product_id', 'Unknown')
                                    product_name = step_data.get('product_data', {}).get('name', 'Unknown')
                                    has_image = step_data.get('captured_image_path') is not None
                                    print(
                                        f"      Step {step_key}: {product_name} (ID: {product_id}), Image: {'✓' if has_image else '✗'}")
                                else:
                                    print(f"      Step {step_key}: INVALID DATA ({type(step_data)})")
                else:
                    print(f"  WARNING: No assembly_data found")

        print("\n" + "=" * 60)

    # ================== Assembly Folder Management ==================
    def get_assembly_block_folder(self, assembly_block):
        """Get or create folder for a specific Assembly block"""
        recipe_path = config_manager.get_current_recipe_folder()
        if not recipe_path:
            return None

        # Ensure block has a unique ID
        if not hasattr(assembly_block, 'block_id'):
            self.assign_block_id(assembly_block)

        # Create folder: Assembly/Block_<id>/
        assembly_folder = os.path.join(recipe_path, "Assembly")
        block_folder = os.path.join(assembly_folder, f"Block_{assembly_block.block_id}")
        os.makedirs(block_folder, exist_ok=True)

        return block_folder

    def assign_block_id(self, assembly_block):
        """Assign a unique ID to an Assembly block"""
        # Get all Assembly blocks in pipeline
        assembly_blocks = [b for b in self.pipeline_blocks if b.name == "Assembly"]

        # Find next available ID
        used_ids = []
        for block in assembly_blocks:
            if hasattr(block, 'block_id'):
                try:
                    used_ids.append(int(block.block_id))
                except (ValueError, TypeError):
                    pass

        # Find next available number (starting from 1)
        next_id = 1
        while next_id in used_ids:
            next_id += 1

        assembly_block.block_id = str(next_id)
        return next_id

    def get_assembly_step_folder(self, assembly_block, step_num):
        """Get or create folder for a specific step of an Assembly block"""
        block_folder = self.get_assembly_block_folder(assembly_block)
        if not block_folder:
            return None

        # Create step folder with consistent naming
        step_folder = os.path.join(block_folder, f"Step_{step_num}")

        try:
            os.makedirs(step_folder, exist_ok=True)
            return step_folder
        except Exception as e:
            print(f"ERROR: Failed to create step folder {step_folder}: {str(e)}")
            return None

    def update_assembly_block_displays(self):
        """Update all Assembly block displays with their IDs and step counts"""
        for block in self.pipeline_blocks:
            if block.name == "Assembly":
                if not hasattr(block, 'block_id'):
                    self.assign_block_id(block)

                # Update the text display
                if hasattr(block, 'text'):
                    # Check if block has assembly_data
                    if hasattr(block, 'assembly_data') and block.assembly_data:
                        # Get total steps from the nested structure
                        total_steps = 0
                        selections_metadata = block.assembly_data.get('selections', {})
                        if selections_metadata and isinstance(selections_metadata, dict):
                            # The actual step count is in selections_metadata
                            total_steps = selections_metadata.get('total_steps', 0)

                        if total_steps > 0:
                            block.text.setPlainText(f"Assembly (Block {block.block_id}, {total_steps} steps)")
                            # Set color to indicate configured
                            block.setPen(QPen(QColor("#1d4ed8"), 2))
                        else:
                            block.text.setPlainText(f"Assembly (Block {block.block_id})")
                            # Set default color for unconfigured blocks
                            block.setBrush(QBrush(QColor("#93c5fd")))  # Light blue
                            block.setPen(QPen(QColor("#1d4ed8"), 2))
                    else:
                        block.text.setPlainText(f"Assembly (Block {block.block_id})")
                        # Set default color for unconfigured blocks
                        block.setBrush(QBrush(QColor("#93c5fd")))
                        block.setPen(QPen(QColor("#1d4ed8"), 2))

    # ================== Clear All ==================
    def clear_all(self, confirm=True):
        """Clear all blocks and connections"""
        if confirm:
            reply = QMessageBox.question(self, "Confirm Clear",
                                         "Are you sure you want to clear all blocks and connections?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return

        # Clear all blocks
        for block in list(self.pipeline_blocks):
            self.remove_block(block)
            self.scene.removeItem(block)
        self.pipeline_blocks.clear()

        # Clear all connections
        for conn in list(self.connections):
            self.scene.removeItem(conn)
        self.connections.clear()

        self.update_buttons_state()

        if confirm:
            QMessageBox.information(self, "✅ Cleared", "All blocks and connections have been cleared.")

    # ================== Delete Selected ==================
    def delete_selected(self):
        """Delete selected blocks and their connections"""
        selected_items = self.scene.selectedItems()

        if not selected_items:
            QMessageBox.information(self, "ℹ️ Information", "No items selected")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {len(selected_items)} selected item(s)?\n\nThis will also delete all connected lines.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        blocks_to_delete = []
        connections_to_delete = []

        # Identify blocks and connections to delete
        for item in selected_items:
            if isinstance(item, GraphicsBlock) and not item.is_left_block:
                blocks_to_delete.append(item)

                # Find connections related to this block
                for conn in self.connections:
                    if conn.from_block == item or conn.to_block == item:
                        if conn not in connections_to_delete:
                            connections_to_delete.append(conn)

            elif isinstance(item, ConnectionLine):
                if item not in connections_to_delete:
                    connections_to_delete.append(item)

        # Remove connections
        for conn in connections_to_delete:
            self.remove_connection(conn)

        # Remove blocks
        for block in blocks_to_delete:
            self.remove_block(block)
            self.scene.removeItem(block)
            if block in self.pipeline_blocks:
                self.pipeline_blocks.remove(block)

        # Update button states
        self.update_buttons_state()

        QMessageBox.information(self, "✅ Deleted",
                                f"Deleted {len(blocks_to_delete)} block(s) and {len(connections_to_delete)} connection(s)")

    def ensure_attributes(self):
        """Ensure all necessary attributes exist"""
        if not hasattr(self, 'config'):
            self.config = None
        if not hasattr(self, 'assembly_data'):
            self.assembly_data = None

    @classmethod
    def from_dict(cls, data, parent_scene=None):
        """Create block from saved data"""
        # Find corresponding action
        from ..components.block_functions import BLOCKS
        action = None
        for name, act in BLOCKS:
            if name == data["name"]:
                action = act
                break

        if not action:
            return None

        # Create block
        block = cls(
            data["name"],
            action,
            data["x"],
            data["y"],
            is_left_block=False
        )

        # Restore configuration
        if data.get("config"):
            block.config = data["config"]

        # RESTORE ASSEMBLY DATA
        if "assembly_data" in data:
            block.assembly_data = data["assembly_data"]

            # Update visual state
            if data["name"] == "Assembly" and block.assembly_data:
                block.setBrush(QBrush(QColor("#a5b4fc")))
                total_steps = block.assembly_data.get('total_steps', 0)
                if total_steps > 0:
                    block.text.setPlainText(f"Assembly ({total_steps} steps)")

        return block