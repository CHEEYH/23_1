import numpy as np
from PySide6.QtWidgets import QGraphicsLineItem
from PySide6.QtGui import QPen, QColor, QPainterPathStroker
from PySide6.QtCore import Qt, QPointF


class ConnectionLine(QGraphicsLineItem):
    def __init__(self, from_block, to_block, parent_scene):
        super().__init__()
        self.from_block = from_block
        self.to_block = to_block
        self.parent_scene = parent_scene

        # Arrow lines (for permanent connections only)
        self.arrow_line1 = None
        self.arrow_line2 = None

        # Create connection line with arrow
        self.setPen(QPen(QColor("#6366f1"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(1)  # Above blocks

        # ✅ Make selectable and hoverable
        self.setFlag(QGraphicsLineItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Add to block's connection lists
        if from_block and hasattr(from_block, 'output_connections'):
            from_block.output_connections.append(self)

        if to_block and hasattr(to_block, 'input_connections'):
            to_block.input_connections.append(self)

        self.update_position()

    def shape(self):
        """Return a larger shape for easier clicking"""
        path = super().shape()
        stroker = QPainterPathStroker()  # Now this works
        stroker.setWidth(10)
        return stroker.createStroke(path)

    def boundingRect(self):
        """Return a larger bounding rect for hover/selection"""
        base_rect = super().boundingRect()
        return base_rect.adjusted(-5, -5, 5, 5)

    def paint(self, painter, option, widget=None):
        """Custom paint to show selection state"""
        if self.isSelected():
            # Selected - red and thicker
            self.setPen(QPen(QColor("#ef4444"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        else:
            # Normal - purple
            self.setPen(QPen(QColor("#6366f1"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

        # Call parent paint
        super().paint(painter, option, widget)

        # Update arrow colors
        if self.arrow_line1 and self.arrow_line2:
            if self.isSelected():
                self.arrow_line1.setPen(QPen(QColor("#ef4444"), 3))
                self.arrow_line2.setPen(QPen(QColor("#ef4444"), 3))
            else:
                self.arrow_line1.setPen(QPen(QColor("#6366f1"), 3))
                self.arrow_line2.setPen(QPen(QColor("#6366f1"), 3))

    def hoverEnterEvent(self, event):
        """Highlight when mouse hovers"""
        if not self.isSelected():
            self.setPen(QPen(QColor("#8b5cf6"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Revert when mouse leaves"""
        if not self.isSelected():
            self.setPen(QPen(QColor("#6366f1"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        super().hoverLeaveEvent(event)

    def update_position(self):
        """Update line position based on block positions"""
        if not self.from_block or not self.to_block:
            return

        # Get current scene positions
        from_scene_pos = self.from_block.scenePos()
        to_scene_pos = self.to_block.scenePos()

        # Calculate port positions
        from_port_x = from_scene_pos.x() + self.from_block.block_width
        from_port_y = from_scene_pos.y() + self.from_block.block_height / 2

        to_port_x = to_scene_pos.x()
        to_port_y = to_scene_pos.y() + self.to_block.block_height / 2

        # Update the line
        self.setLine(from_port_x, from_port_y, to_port_x, to_port_y)

        # Update arrow head
        self.draw_arrow_head(QPointF(from_port_x, from_port_y),
                             QPointF(to_port_x, to_port_y))

    def draw_arrow_head(self, from_pos, to_pos):
        """Draw arrow head"""
        # Remove old arrow lines
        self.remove_arrow_lines()

        angle = np.arctan2(to_pos.y() - from_pos.y(),
                           to_pos.x() - from_pos.x())
        arrow_length = 12
        arrow_angle = np.pi / 6

        # Arrow point 1
        x1 = to_pos.x() - arrow_length * np.cos(angle - arrow_angle)
        y1 = to_pos.y() - arrow_length * np.sin(angle - arrow_angle)

        # Arrow point 2
        x2 = to_pos.x() - arrow_length * np.cos(angle + arrow_angle)
        y2 = to_pos.y() - arrow_length * np.sin(angle + arrow_angle)

        # Create new arrow lines
        self.arrow_line1 = QGraphicsLineItem(to_pos.x(), to_pos.y(), x1, y1, self)
        self.arrow_line1.setPen(QPen(QColor("#6366f1"), 3))
        self.arrow_line1.setZValue(1)

        self.arrow_line2 = QGraphicsLineItem(to_pos.x(), to_pos.y(), x2, y2, self)
        self.arrow_line2.setPen(QPen(QColor("#6366f1"), 3))
        self.arrow_line2.setZValue(1)

    def remove_arrow_lines(self):
        """Remove arrow lines"""
        if self.arrow_line1:
            if self.arrow_line1.scene():
                self.arrow_line1.scene().removeItem(self.arrow_line1)
            self.arrow_line1 = None

        if self.arrow_line2:
            if self.arrow_line2.scene():
                self.arrow_line2.scene().removeItem(self.arrow_line2)
            self.arrow_line2 = None

    def remove(self):
        """Remove connection from both blocks and scene"""
        # Remove from block's connection lists
        if self.from_block and hasattr(self.from_block, 'output_connections'):
            if self in self.from_block.output_connections:
                self.from_block.output_connections.remove(self)

        if self.to_block and hasattr(self.to_block, 'input_connections'):
            if self in self.to_block.input_connections:
                self.to_block.input_connections.remove(self)

        # Remove arrow lines
        self.remove_arrow_lines()

        # Remove from scene
        if self.scene():
            self.scene().removeItem(self)