# ui/graphics/graphics_block.py
import os

import numpy as np
from PySide6.QtWidgets import (
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsEllipseItem,
    QMenu, QMessageBox, QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QPen, QColor, QFont
from ..components.dialogs import AssemblyDialog, ScrewDialog, ConfigurationOptionsDialog


class GraphicsBlock(QGraphicsRectItem):
    def __init__(self, name, action, x=0, y=0, w=220, h=44, is_left_block=False,
                 block_id=None, block_type=None):
        super().__init__(0, 0, w, h)
        self.name = name
        self.action = action
        self.is_left_block = is_left_block
        self.block_width = w
        self.block_height = h
        self.config = None  # Store configuration information
        self.is_selected = False
        self.assembly_data = None  # Store detailed assembly data

        # Handle block_id and block_type
        if block_id is None:
            self.block_id = None
        else:
            self.block_id = str(block_id)

        if block_type is None:
            self.block_type = name.lower()
        else:
            self.block_type = block_type

        if self.block_id is not None:
            self.block_name = f"Block_{self.block_id}"
        else:
            self.block_name = None

        # Set initial block position
        self.setPos(x, y)

        # Set rectangle style (temporary colors, will be updated by update_block_appearance)
        self.setBrush(QBrush(QColor("#93c5fd")))  # Default blue
        self.setPen(QPen(QColor("#1d4ed8"), 2))

        # Only blocks on right panel can be moved
        if not is_left_block:
            self.setFlag(QGraphicsRectItem.ItemIsMovable, True)
            self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, True)
            self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)

        # Create text FIRST before calling update_block_appearance
        self.text = QGraphicsTextItem(name, self)
        font = QFont("Segoe UI", 11, QFont.Bold)
        self.text.setFont(font)

        # Calculate text position - center aligned
        text_rect = self.text.boundingRect()
        text_x = (w - text_rect.width()) / 2
        text_y = (h - text_rect.height()) / 2
        self.text.setPos(text_x, text_y)

        # Now update appearance (this will set colors and potentially update text)
        self.update_block_appearance()

        # Create ports for flow blocks
        if not is_left_block:
            self.input_connections = []  # Input connection lines
            self.output_connections = []  # Output connection lines

            # End block has no output port
            if name != "End":
                # Output port at right edge center
                self.output_port = QGraphicsEllipseItem(w - 12, h / 2 - 12, 24, 24, self)
                self.output_port.setBrush(QBrush(QColor("#22c55e")))  # Green output
                self.output_port.setPen(QPen(QColor("#15803d"), 1))
                self.output_port.setZValue(10)
                self.output_port.setAcceptHoverEvents(True)
                self.output_port.port_type = "output"

            # Assembly, Screw and End blocks have input ports
            if name in ["Assembly", "Screw", "End"]:
                # Input port at left edge center
                self.input_port = QGraphicsEllipseItem(-12, h / 2 - 12, 24, 24, self)
                self.input_port.setBrush(QBrush(QColor("#3b82f6")))  # Blue input
                self.input_port.setPen(QPen(QColor("#1d4ed8"), 1))
                self.input_port.setZValue(10)
                self.input_port.setAcceptHoverEvents(True)
                self.input_port.port_type = "input"

    def mouseDoubleClickEvent(self, event):
        try:
            scene = self.scene()
            if scene and hasattr(scene, "page") and scene.page:
                if self.name == "Assembly":
                    scene.page.configure_assembly_block(self)
                    event.accept()
                    return
                elif self.name == "Screw":
                    scene.page.configure_screw_block(self)
                    event.accept()
                    return
        except Exception as e:
            print(f"ERROR in mouseDoubleClickEvent: {e}")

        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self.is_left_block:
            return

        menu = QMenu()

        # Single Configure option that opens edit dialog
        configure_action = menu.addAction("⚙️ Configure")

        menu.addSeparator()
        remove_action = menu.addAction("🗑️ Delete Block")

        selected = menu.exec(event.screenPos())

        if selected == configure_action:
            self.open_configuration_dialog(edit_mode=True)
        elif selected == remove_action:
            self.remove_block()

    def show_configuration_options(self):
        """Show configuration options dialog with edit/view choices"""
        # For double-click, always go to edit mode with existing config
        if self.name in ["Assembly", "Screw"]:
            if self.config:
                # Already configured - open edit dialog directly
                self.open_configuration_dialog(edit_mode=True)
            else:
                # Not configured yet - open edit dialog
                self.open_configuration_dialog(edit_mode=True)

    def open_configuration_dialog(self, edit_mode=False):
        """Open configuration dialog for this block"""
        if self.name == "Assembly":
            # Get existing configuration if editing
            initial_config = None
            if hasattr(self, 'assembly_data') and self.assembly_data:
                initial_config = self.assembly_data

            # Get block information
            block_id = getattr(self, 'block_id', '1')
            block_name = getattr(self, 'block_name', f"Assembly Block {block_id}")

            # Add block_name to config
            if initial_config:
                initial_config['block_name'] = block_name
                initial_config['block_id'] = block_id

            # Create and show AssemblyDialog
            dialog = AssemblyDialog(
                parent=None,  # Add parent parameter
                initial_config=initial_config,
                block_id=block_id,
                block_name=block_name  # PASS BLOCK NAME
            )

            if dialog.exec() == QDialog.Accepted:
                # Update with new configuration
                self.update_assembly_configuration(dialog)
            else:
                # User cancelled - configuration unchanged
                print("Configuration edit cancelled")

        elif self.name == "Screw":
            self.configure_screw()

    # In graphics_block.py, in update_assembly_configuration method:

    def update_assembly_configuration(self, dialog):
        """Update assembly block with configuration from dialog"""
        if not hasattr(dialog, 'get_all_selections'):
            return

        # Get the complete configuration from dialog
        config = dialog.get_all_selections()

        # Try to get block_name from various sources
        block_name = None

        # First try from dialog
        if hasattr(dialog, 'block_name'):
            block_name = dialog.block_name
        # Then try from config
        elif 'block_name' in config:
            block_name = config['block_name']
        # Finally, create a default
        else:
            block_name = f"Assembly {self.block_id}"

        # Store the configuration
        self.config = {
            'block_type': 'assembly',
            'block_id': self.block_id,
            'block_name': block_name,
            'total_steps': config.get('total_steps', 1),
            'selections': {}
        }

        # Store the complete assembly config for later use
        self.assembly_config = config
        self.assembly_data = config  # Also set this for backward compatibility

        # IMPORTANT: Iterate through the 'selections' dictionary
        selections_dict = config.get('selections', {})

        for step_str, selection_data in selections_dict.items():
            # Make sure we have a valid selection
            if not isinstance(selection_data, dict):
                continue

            # Get the product_id - now we're accessing the dictionary correctly
            product_id = selection_data.get('product_id', '')
            product_data = selection_data.get('product_data', {})
            capture_info = selection_data.get('capture_info', {})

            self.config['selections'][step_str] = {
                'product_id': product_id,
                'product_name': product_data.get('name', ''),
                'product_data': product_data,
                'capture_info': capture_info
            }

        # Update the block appearance
        self.update_block_appearance()
        self.setToolTip(self.get_configuration_summary())

    def update_block_appearance(self):
        """Update the block's visual appearance based on configuration status"""
        # Change color when configured
        if self.config:
            # Configured - darker color
            if self.name == "Assembly":
                self.setBrush(QBrush(QColor("#3b82f6")))  # Darker blue
                self.setPen(QPen(QColor("#1e3a8a"), 2))
            elif self.name == "Screw":
                self.setBrush(QBrush(QColor("#4ade80")))  # Darker green
                self.setPen(QPen(QColor("#166534"), 2))
            elif self.name == "End":
                self.setBrush(QBrush(QColor("#f87171")))  # Darker red
                self.setPen(QPen(QColor("#991b1b"), 2))
            else:
                self.setBrush(QBrush(QColor("#fdba74")))  # Darker orange
                self.setPen(QPen(QColor("#9a3412"), 2))

            # Update text to show configured status - only if text exists
            if hasattr(self, 'text') and self.text:
                if hasattr(self, 'config') and isinstance(self.config, dict) and 'total_steps' in self.config:
                    self.text.setPlainText(f"{self.name}\n({self.config['total_steps']} steps)")
                else:
                    self.text.setPlainText(f"{self.name}\n(Configured)")

                # Re-center the text
                text_rect = self.text.boundingRect()
                text_x = (self.block_width - text_rect.width()) / 2
                text_y = (self.block_height - text_rect.height()) / 2
                self.text.setPos(text_x, text_y)
        else:
            # Not configured - original colors
            if self.name == "Assembly":
                self.setBrush(QBrush(QColor("#93c5fd")))  # Light blue
                self.setPen(QPen(QColor("#1d4ed8"), 2))
            elif self.name == "Screw":
                self.setBrush(QBrush(QColor("#86efac")))  # Light green
                self.setPen(QPen(QColor("#16a34a"), 2))
            elif self.name == "End":
                self.setBrush(QBrush(QColor("#fca5a5")))  # Light red
                self.setPen(QPen(QColor("#dc2626"), 2))
            else:
                self.setBrush(QBrush(QColor("#fef3c7")))  # Light yellow
                self.setPen(QPen(QColor("#d97706"), 2))

            # Reset text to original name - only if text exists
            if hasattr(self, 'text') and self.text:
                self.text.setPlainText(self.name)

                # Re-center the text
                text_rect = self.text.boundingRect()
                text_x = (self.block_width - text_rect.width()) / 2
                text_y = (self.block_height - text_rect.height()) / 2
                self.text.setPos(text_x, text_y)

    def get_configuration_summary(self):
        """Get a summary of the configuration for tooltip"""
        if not hasattr(self, 'config'):
            return "Double-click to configure"

        # Use block_name from config or fallback to self.block_name
        block_name = self.config.get('block_name', self.block_name)

        summary = f"{block_name}\n"
        summary += f"Type: {self.config.get('block_type', 'Assembly').title()}\n"

        if 'selections' in self.config:
            selections = self.config['selections']
            summary += f"Steps: {len(selections)}\n"

            for step_num, selection in selections.items():
                product_name = selection.get('product_name', 'Unknown')
                summary += f"  Step {step_num}: {product_name}\n"

                # Add capture info if available
                capture_info = selection.get('capture_info', {})
                if capture_info.get('current_image') or capture_info.get('capture_folder'):
                    summary += f"    ✓ Image captured\n"

        return summary

    # In GraphicsBlock class, add a method to check if block is connected

    def is_connected_to_pipeline(self):
        """Check if this block is part of a valid pipeline"""
        # A block is connected if it has an input connection OR output connection
        has_input = hasattr(self, 'input_connections') and len(self.input_connections) > 0
        has_output = hasattr(self, 'output_connections') and len(self.output_connections) > 0

        # Special case: End block only needs input
        if self.name == "End":
            return has_input

        # Other blocks need either input OR output (but typically both in a chain)
        return has_input or has_output

    def update_visual_connection_status(self):
        """Update block appearance based on connection status"""
        if not self.is_left_block:  # Only for pipeline blocks
            if self.is_connected_to_pipeline():
                # Connected - normal appearance
                self.setOpacity(1.0)
                self.setToolTip("Connected to pipeline")
            else:
                # Unconnected - faded appearance
                self.setOpacity(0.6)
                self.setToolTip("⚠️ Not connected - will NOT run")

    def itemChange(self, change, value):
        """Called when item properties change (like position)"""
        if change == QGraphicsRectItem.ItemPositionChange and self.scene():
            # Block is moving - schedule connection updates after movement
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.update_connections)

        return super().itemChange(change, value)

    def update_connections(self):
        """Update all connections attached to this block"""
        # Update output connections
        if hasattr(self, 'output_connections'):
            for conn in self.output_connections:
                if conn and conn.scene():
                    conn.update_position()

        # Update input connections
        if hasattr(self, 'input_connections'):
            for conn in self.input_connections:
                if conn and conn.scene():
                    conn.update_position()

    # In graphics_block.py, when opening the dialog for an existing configuration:

    def open_assembly_dialog_with_existing_config(self):
        """Open assembly dialog with existing configuration"""
        # Get existing config
        existing_config = {}

        if hasattr(self, 'assembly_config'):
            # Use the stored assembly config directly
            existing_config = self.assembly_config
        elif hasattr(self, 'config') and 'selections' in self.config:
            # Reconstruct from our simplified config
            existing_config = {
                'block_id': self.config.get('block_id', self.block_id),
                'block_name': self.config.get('block_name', self.block_name),
                'total_steps': self.config.get('total_steps', 1),
                'selections': {}
            }

            for step_str, selection in self.config['selections'].items():
                existing_config['selections'][step_str] = {
                    'product_id': selection.get('product_id', ''),
                    'product_data': selection.get('product_data', {}),
                    'capture_info': selection.get('capture_info', {})
                }

        # Create dialog with existing configuration
        dialog = AssemblyDialog(
            parent=self.parent_widget,
            initial_config=existing_config,
            block_id=self.block_id,
            block_name=self.block_name
        )

        return dialog

    def configure_screw(self):
        initial_config = None
        if self.config:
            initial_config = self.parse_screw_config()

        dialog = ScrewDialog(
            parent=None,
            block_id=str(self.block_id) if self.block_id is not None else None,
            block_name=f"Block_{self.block_id}" if self.block_id is not None else None
        )

        if initial_config:
            dialog.screw_spinbox.setValue(initial_config.get('count', 4))
            if initial_config.get('type') in ["M3", "M4", "M5", "M6", "M8", "M10", "Custom"]:
                index = dialog.screw_type_combo.findText(initial_config.get('type'))
                if index >= 0:
                    dialog.screw_type_combo.setCurrentIndex(index)
            dialog.torque_spinbox.setValue(initial_config.get('torque', 10))

        if dialog.exec():
            self.update_screw_configuration(dialog)
        else:
            print("Screw configuration cancelled")

    def parse_screw_config(self):
        """Parse existing screw configuration into dictionary"""
        if not self.config:
            return {}

        if isinstance(self.config, dict):
            # Already in dictionary format
            return self.config
        else:
            # Legacy string format
            config_dict = {}
            lines = self.config.split('\n')
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    if key == 'Type':
                        config_dict['type'] = value
                    elif key == 'Count':
                        config_dict['count'] = int(value) if value.isdigit() else 4
                    elif key == 'Torque':
                        # Extract numeric value from "10 N·m"
                        nums = ''.join(filter(str.isdigit, value))
                        config_dict['torque'] = int(nums) if nums else 10

            config_dict['block_type'] = 'screw'
            return config_dict

    def update_screw_configuration(self, dialog):
        self.config = {
            'block_type': 'screw',
            'block_id': str(self.block_id) if self.block_id is not None else None,
            'block_name': f"Block_{self.block_id}" if self.block_id is not None else None,
            'type': dialog.screw_type,
            'count': dialog.screw_count,
            'torque': dialog.torque
        }

        self.update_block_appearance()

        if self.block_id is not None:
            self.text.setPlainText(f"Screw (Block {self.block_id}, {dialog.screw_count}x {dialog.screw_type})")
        else:
            self.text.setPlainText(f"Screw ({dialog.screw_count}x {dialog.screw_type})")

        text_rect = self.text.boundingRect()
        text_x = (self.block_width - text_rect.width()) / 2
        text_y = (self.block_height - text_rect.height()) / 2
        self.text.setPos(text_x, text_y)

    def show_configuration_view(self):
        """Show configuration in a view-only dialog"""
        if not self.config:
            QMessageBox.information(None, f"📋 {self.name} Configuration",
                                    "No configuration saved yet.\n\nDouble-click to configure.")
            return

        if self.name == "Assembly" and self.assembly_data:
            self.show_assembly_configuration_view()
        else:
            # For screw and other blocks
            dialog = QDialog()
            dialog.setWindowTitle(f"📋 {self.name} Configuration")
            dialog.setFixedSize(500, 400)

            layout = QVBoxLayout(dialog)

            # Configuration text
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(self.config)
            text_edit.setStyleSheet("""
                QTextEdit {
                    font-family: 'Courier New', monospace;
                    font-size: 12px;
                    background-color: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    padding: 10px;
                }
            """)

            layout.addWidget(text_edit)

            # Buttons - only show edit button for configurable blocks
            button_layout = QHBoxLayout()

            if self.name in ["Assembly", "Screw"]:  # Add other configurable blocks
                edit_btn = QPushButton("✏️ Edit Configuration")
                edit_btn.clicked.connect(lambda: self.open_configuration_dialog(edit_mode=True))
                edit_btn.clicked.connect(dialog.accept)
                button_layout.addWidget(edit_btn)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)

            button_layout.addStretch()
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)
            dialog.exec()

    def show_assembly_configuration_view(self):
        """Show assembly configuration with detailed view"""
        dialog = QDialog()
        dialog.setWindowTitle("📋 Assembly Configuration")
        dialog.setFixedSize(600, 500)

        layout = QVBoxLayout(dialog)

        # Create HTML content
        html_content = self.format_configuration_html()

        # Text edit for HTML display
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(html_content)
        text_edit.setStyleSheet("""
            QTextEdit {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 15px;
            }
        """)

        layout.addWidget(text_edit)

        # Buttons
        button_layout = QHBoxLayout()

        edit_btn = QPushButton("✏️ Edit Configuration")
        edit_btn.clicked.connect(lambda: self.open_configuration_dialog(edit_mode=True))
        edit_btn.clicked.connect(dialog.accept)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)

        button_layout.addStretch()
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dialog.exec()

    def format_configuration_html(self):
        """Format assembly configuration as HTML"""
        if not self.assembly_data:
            return f"<pre>{self.config}</pre>"

        html = """
        <html>
        <head>
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; color: #333; }
            h2 { color: #1d4ed8; border-bottom: 2px solid #93c5fd; padding-bottom: 8px; }
            h3 { color: #1e40af; margin-top: 20px; }
            .step-card { 
                background-color: #f0f9ff; 
                border: 1px solid #93c5fd; 
                border-radius: 8px; 
                padding: 15px; 
                margin: 10px 0; 
            }
            .step-header { 
                color: #1e40af; 
                font-weight: bold; 
                font-size: 14px; 
                margin-bottom: 8px; 
            }
            .detail-row { 
                margin: 4px 0; 
                padding-left: 15px; 
            }
            .status-trained { color: #16a34a; font-weight: bold; }
            .status-untrained { color: #dc2626; font-weight: bold; }
            .summary { 
                background-color: #f8fafc; 
                border: 1px solid #e2e8f0; 
                border-radius: 6px; 
                padding: 10px; 
                margin: 15px 0; 
            }
        </style>
        </head>
        <body>
        """

        html += f"<h2>Assembly Configuration</h2>"
        html += f'<div class="summary">'
        html += f'<p><b>Total Steps:</b> {self.assembly_data["total_steps"]}</p>'
        html += f'<p><b>Block Name:</b> Assembly ({self.assembly_data["total_steps"]} steps)</p>'
        html += '</div>'

        for step, selection in self.assembly_data['selections'].items():
            product_data = selection['product_data']
            product_id = selection['product_id']

            html += f'<div class="step-card">'
            html += f'<div class="step-header">Step {step}</div>'
            html += f'<div class="detail-row"><b>Product:</b> {product_data.get("name", product_id)}</div>'

            if product_data.get('model_path'):
                model_name = os.path.basename(product_data['model_path'])
                html += f'<div class="detail-row"><b>Model:</b> {model_name}</div>'

            trained = product_data.get('trained', False)
            status_class = "status-trained" if trained else "status-untrained"
            status_text = "✅ Trained" if trained else "❌ Not Trained"
            html += f'<div class="detail-row"><b>Status:</b> <span class="{status_class}">{status_text}</span></div>'

            html += '</div>'

        html += "</body></html>"
        return html

    def configure_block(self):
        """Legacy method for backward compatibility"""
        self.open_configuration_dialog(edit_mode=True)

    def remove_block(self):
        """Delete function block"""
        reply = QMessageBox.question(None, "Confirm Delete",
                                     f"Are you sure you want to delete '{self.name}' block?",
                                     QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            scene = self.scene()
            if scene and hasattr(scene, "page"):
                # Remove all connections
                for conn in list(self.input_connections):
                    scene.page.remove_connection(conn)
                for conn in list(self.output_connections):
                    scene.page.remove_connection(conn)
                # Remove block from flow
                scene.page.remove_block(self)

            scene.removeItem(self)