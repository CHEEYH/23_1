import os
import random
import shutil
import math
from PySide6.QtWidgets import QWidget, QFileDialog
from PySide6.QtGui import QPainter, QPen, QPixmap, QColor, QBrush, QPolygon, QPolygonF
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, Signal


class AnnotationWidget(QWidget):
    status_message = Signal(str)
    def __init__(self, get_current_label, get_label_color):
        super().__init__()
        self.get_current_label = get_current_label
        self.get_label_color = get_label_color

        # Rotation-specific variables
        self.initial_angle = 0
        self.original_angle = 0
        self.rotation_center = QPointF()

        self.pixmap = None
        self.scaled_pixmap = None

        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self.drawing = False
        self.start_img_pt = QPointF()
        self.end_img_pt = QPointF()

        # CRITICAL: Add these missing attributes
        self.boxes = []  # Regular boxes list
        self.label_to_id = {}
        self.next_class_id = 0
        self.current_image_path = None

        # Store rotated boxes: [(cx, cy, width, height, angle, label)]
        self.rotated_boxes = []
        self.regular_boxes = self.boxes  # Reference to boxes list

        # OBB drawing state
        self.drawing_obb = False
        self.obb_points = []  # Store 4 corner points
        self.obb_temp_line = None  # For drawing in progress

        # Selection and editing state
        self.selected_index = -1
        self.selected_type = None  # 'regular' or 'rotated'
        self.dragging = False
        self.resizing = False
        self.rotating = False
        self.resize_handle = -1
        self.drag_start_pos = QPointF()
        self.drag_offset = QPointF()
        self.original_rect = QRectF()
        self.original_box = None

        self.HANDLE_SIZE = 8
        self.ROTATE_HANDLE_SIZE = 10
        self.handles = [
            (0, 0, "top-left"),  # 0
            (0.5, 0, "top"),  # 1
            (1, 0, "top-right"),  # 2
            (1, 0.5, "right"),  # 3
            (1, 1, "bottom-right"),  # 4
            (0.5, 1, "bottom"),  # 5
            (0, 1, "bottom-left"),  # 6
            (0, 0.5, "left")  # 7
        ]

        # OBB mode flag
        self.obb_mode = False
        self.angle_step = 5  # Rotation step in degrees

    def set_obb_mode_flag(self, labeling_path, enabled):
        """Set or remove OBB mode flag file"""
        flag_path = os.path.join(labeling_path, ".obb_mode")
        if enabled:
            with open(flag_path, 'w') as f:
                f.write('OBB mode enabled')
            print("✓ OBB mode flag set")
        else:
            if os.path.exists(flag_path):
                os.remove(flag_path)
                print("✓ OBB mode flag removed")

    # ---------------- Rotated Box Handling ----------------
    def get_rotated_box_corners(self, cx, cy, width, height, angle_deg):
        """Get 4 corner points of rotated rectangle"""
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        corners = []
        for dx, dy in [(-width / 2, -height / 2), (width / 2, -height / 2),
                       (width / 2, height / 2), (-width / 2, height / 2)]:
            # Rotate point
            x = cx + dx * cos_a - dy * sin_a
            y = cy + dx * sin_a + dy * cos_a
            corners.append(QPointF(x, y))
        return corners

    def convert_to_yolo_obb_format(self, cx, cy, width, height, angle, image_width, image_height):
        """Convert rotated box to YOLO OBB format: class_id x1 y1 x2 y2 x3 y3 x4 y4 (normalized)"""
        corners = self.get_rotated_box_corners(cx, cy, width, height, angle)

        # Normalize coordinates
        normalized = []
        for point in corners:
            normalized.append(point.x() / image_width)
            normalized.append(point.y() / image_height)

        return normalized

    def save_yolo_obb_annotations(self, path, image_width, image_height):
        """Save annotations in YOLO OBB format"""
        lines = []

        # Save rotated boxes
        for box in self.rotated_boxes:
            cx, cy, width, height, angle, label = box
            class_id = self.get_class_id(label)

            # Get 4 corners normalized
            corners_norm = self.convert_to_yolo_obb_format(
                cx, cy, width, height, angle, image_width, image_height
            )

            # Format: class_id x1 y1 x2 y2 x3 y3 x4 y4
            line = f"{class_id} " + " ".join([f"{c:.6f}" for c in corners_norm])
            lines.append(line)

        # Save regular boxes as OBB with angle 0
        for rect, label in self.regular_boxes:
            cx = rect.x() + rect.width() / 2
            cy = rect.y() + rect.height() / 2
            width = rect.width()
            height = rect.height()
            angle = 0.0
            class_id = self.get_class_id(label)

            corners_norm = self.convert_to_yolo_obb_format(
                cx, cy, width, height, angle, image_width, image_height
            )

            line = f"{class_id} " + " ".join([f"{c:.6f}" for c in corners_norm])
            lines.append(line)

        # Write to file
        with open(path, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines))

    # ---------------- Image handling ----------------
    def load_image(self, path):
        if not path.lower().endswith(".bmp"):
            return
        self.pixmap = QPixmap(path)
        self.current_image_path = path
        self.update_scaled_pixmap()

        # Load existing annotations
        self.load_existing_annotations(path)

    def resizeEvent(self, event):
        self.update_scaled_pixmap()

    def update_scaled_pixmap(self):
        if not self.pixmap:
            return

        self.scale = min(
            self.width() / self.pixmap.width(),
            self.height() / self.pixmap.height()
        )

        new_w = self.pixmap.width() * self.scale
        new_h = self.pixmap.height() * self.scale

        self.offset_x = (self.width() - new_w) / 2
        self.offset_y = (self.height() - new_h) / 2

        self.scaled_pixmap = self.pixmap.scaled(
            new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.update()

    # ---------------- Coordinate mapping ----------------
    def screen_to_image(self, pt: QPointF) -> QPointF:
        return QPointF(
            (pt.x() - self.offset_x) / self.scale,
            (pt.y() - self.offset_y) / self.scale
        )

    def image_to_screen(self, rect: QRectF) -> QRectF:
        return QRectF(
            rect.x() * self.scale + self.offset_x,
            rect.y() * self.scale + self.offset_y,
            rect.width() * self.scale,
            rect.height() * self.scale
        )

    # Get class ID for label
    def get_class_id(self, label):
        if label not in self.label_to_id:
            self.label_to_id[label] = self.next_class_id
            self.next_class_id += 1
        return self.label_to_id[label]

    # Convert bounding box to YOLO format
    def convert_to_yolo_format(self, rect, image_width, image_height):
        """Convert bounding box to YOLO format: class_id x_center y_center width height"""
        # Calculate center coordinates
        x_center = (rect.x() + rect.width() / 2) / image_width
        y_center = (rect.y() + rect.height() / 2) / image_height

        # Calculate normalized width and height
        width = rect.width() / image_width
        height = rect.height() / image_height

        return x_center, y_center, width, height

    # Check if point is inside a box
    def get_box_at_point(self, point: QPointF) -> int:
        """Return index of box containing the point, or -1 if none"""
        for i, (rect, _) in enumerate(reversed(self.boxes)):
            # Reverse iteration to select topmost box first
            actual_index = len(self.boxes) - 1 - i
            if rect.contains(point):
                return actual_index
        return -1

    # Check if point is on a resize handle
    def get_resize_handle_at_point(self, point: QPointF, rect: QRectF) -> int:
        """Return handle index if point is on a resize handle, otherwise -1"""
        screen_rect = self.image_to_screen(rect)

        for i, (rel_x, rel_y, _) in enumerate(self.handles):
            handle_x = screen_rect.x() + rel_x * screen_rect.width()
            handle_y = screen_rect.y() + rel_y * screen_rect.height()

            handle_rect = QRectF(
                handle_x - self.HANDLE_SIZE / 2,
                handle_y - self.HANDLE_SIZE / 2,
                self.HANDLE_SIZE,
                self.HANDLE_SIZE
            )

            if handle_rect.contains(point):
                return i
        return -1

    # ---------------- Mouse events ----------------
    def mousePressEvent(self, event):
        """Handle mouse press events for both regular and OBB boxes"""
        if not self.pixmap:
            return

        screen_pos = event.position()
        img_pos = self.screen_to_image(screen_pos)

        if event.button() == Qt.LeftButton:
            # ============= FIRST: Check if clicking on rotation handle of ANY OBB box =============
            # This needs to be checked BEFORE anything else, even before selecting the box
            for i, box in enumerate(self.rotated_boxes):
                if self.is_on_rotation_handle(screen_pos, box):
                    self.selected_index = i
                    self.selected_type = 'rotated'
                    self.rotating = True
                    self.dragging = False
                    self.resizing = False
                    self.drawing = False
                    self.drawing_obb = False
                    self.resize_handle = -1
                    self.drag_start_pos = img_pos
                    # Store the initial angle when rotation starts
                    self.initial_angle = math.degrees(math.atan2(
                        img_pos.y() - box[1],
                        img_pos.x() - box[0]
                    ))
                    self.original_angle = box[4]  # Store the original box angle
                    self.rotation_center = QPointF(box[0], box[1])
                    self.setCursor(Qt.CrossCursor)
                    self.status_message.emit("Drag to rotate box")
                    self.update()
                    return

            # ============= SECOND: Check if clicking on an existing OBB box =============
            obb_idx = self.get_obb_at_point(img_pos)
            if obb_idx >= 0:
                self.selected_index = obb_idx
                self.selected_type = 'rotated'

                # Check resize handles (corners)
                handle_idx = self.get_obb_resize_handle_at_point(screen_pos, self.rotated_boxes[self.selected_index])
                if handle_idx >= 0:
                    self.resizing = True
                    self.rotating = False
                    self.dragging = False
                    self.drawing = False
                    self.drawing_obb = False
                    self.resize_handle = handle_idx
                    self.drag_start_pos = img_pos
                    self.original_box = list(self.rotated_boxes[self.selected_index][:5])
                    self.setCursor(Qt.SizeAllCursor)
                    self.status_message.emit("Drag corner to resize box")
                    self.update()
                    return

                # Otherwise drag the entire box
                self.dragging = True
                self.rotating = False
                self.resizing = False
                self.drawing = False
                self.drawing_obb = False
                self.resize_handle = -1
                self.drag_start_pos = img_pos
                self.drag_offset = QPointF(
                    img_pos.x() - self.rotated_boxes[self.selected_index][0],
                    img_pos.y() - self.rotated_boxes[self.selected_index][1]
                )
                self.setCursor(Qt.ClosedHandCursor)
                self.status_message.emit("Drag to move box")
                self.update()
                return

            # ============= THIRD: OBB Drawing Mode =============
            if self.obb_mode:
                # Only enter drawing mode if not clicking on rotation handle or existing box
                self.handle_obb_mouse_press(img_pos)
                return

            # ============= FOURTH: Regular Box Handling =============

            # Check if clicking on resize handle of selected regular box
            if self.selected_index >= 0 and self.selected_type == 'regular':
                rect, _ = self.boxes[self.selected_index]
                handle_idx = self.get_resize_handle_at_point(screen_pos, rect)
                if handle_idx >= 0:
                    self.resizing = True
                    self.dragging = False
                    self.rotating = False
                    self.drawing = False
                    self.resize_handle = handle_idx
                    self.drag_start_pos = img_pos
                    self.original_rect = QRectF(rect)
                    self.set_resize_cursor(handle_idx)
                    self.update()
                    return

            # Regular box selection and drawing
            self.handle_regular_box_mouse_press(img_pos, screen_pos)

        # ============= RIGHT BUTTON: Selection and Cancellation =============
        elif event.button() == Qt.RightButton:
            # Clear OBB points if in drawing mode
            if self.obb_mode and self.drawing_obb:
                self.obb_points.clear()
                self.drawing_obb = False
                self.obb_temp_line = None
                self.status_message.emit("OBB drawing cancelled")
                self.setCursor(Qt.CrossCursor if self.obb_mode else Qt.ArrowCursor)
                self.update()
                return

            # Select box (regular or rotated)
            self.handle_selection(img_pos)

        self.update()

    def get_obb_at_point(self, point: QPointF) -> int:
        """Return index of rotated box containing the point, or -1 if none"""
        for i, (cx, cy, width, height, angle, _) in enumerate(reversed(self.rotated_boxes)):
            actual_index = len(self.rotated_boxes) - 1 - i
            corners = self.get_rotated_box_corners(cx, cy, width, height, angle)
            polygon = QPolygonF([QPointF(p.x(), p.y()) for p in corners])
            if polygon.containsPoint(point, Qt.OddEvenFill):
                return actual_index
        return -1

    def get_obb_resize_handle_at_point(self, screen_pos, box):
        """Check if click is on resize handle of OBB"""
        cx, cy, width, height, angle, _ = box
        corners = self.get_rotated_box_corners(cx, cy, width, height, angle)

        # Convert to screen coordinates
        screen_corners = []
        for point in corners:
            screen_point = QPointF(
                point.x() * self.scale + self.offset_x,
                point.y() * self.scale + self.offset_y
            )
            screen_corners.append(screen_point)

        # Check each corner for resize handle
        for i, corner in enumerate(screen_corners):
            handle_rect = QRectF(
                corner.x() - self.HANDLE_SIZE / 2,
                corner.y() - self.HANDLE_SIZE / 2,
                self.HANDLE_SIZE,
                self.HANDLE_SIZE
            )
            if handle_rect.contains(screen_pos):
                return i  # Return corner index (0-3)

        return -1

    def handle_selection(self, img_pos):
        """Handle box selection on right click"""
        # Clear any drawing states
        self.drawing = False
        self.drawing_obb = False
        self.dragging = False
        self.resizing = False
        self.rotating = False

        # Check rotated boxes first (they should have priority)
        for i, (cx, cy, width, height, angle, _) in enumerate(reversed(self.rotated_boxes)):
            actual_index = len(self.rotated_boxes) - 1 - i
            corners = self.get_rotated_box_corners(cx, cy, width, height, angle)

            # Check if point is inside rotated polygon
            polygon = QPolygonF([QPointF(p.x(), p.y()) for p in corners])
            if polygon.containsPoint(img_pos, Qt.OddEvenFill):
                self.selected_index = actual_index
                self.selected_type = 'rotated'
                self.status_message.emit(f"Selected rotated box {actual_index}")
                self.update()
                return

        # Check regular boxes
        box_idx = self.get_box_at_point(img_pos)
        if box_idx >= 0:
            self.selected_index = box_idx
            self.selected_type = 'regular'
            self.status_message.emit(f"Selected regular box {box_idx}")
            self.update()
        else:
            self.selected_index = -1
            self.selected_type = None
            self.status_message.emit("No box selected")
            self.update()

    def handle_regular_box_mouse_press(self, img_pos, screen_pos):
        """Handle mouse press for regular (non-OBB) boxes"""
        # Check if clicking inside an existing box
        box_idx = self.get_box_at_point(img_pos)
        if box_idx >= 0:
            self.selected_index = box_idx
            self.selected_type = 'regular'
            self.dragging = True
            self.drawing = False
            self.resizing = False
            self.rotating = False
            self.drag_start_pos = img_pos
            self.drag_offset = img_pos - self.boxes[box_idx][0].topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            self.status_message.emit("Drag to move box")
            self.update()
            return

        # Otherwise start drawing a new box
        self.selected_index = -1
        self.selected_type = None
        self.drawing = True
        self.dragging = False
        self.resizing = False
        self.rotating = False
        self.start_img_pt = img_pos
        self.end_img_pt = img_pos
        self.setCursor(Qt.CrossCursor)
        self.status_message.emit("Drag to draw bounding box")
        self.update()

    def handle_regular_box_mouse_move(self, img_pos, screen_pos):
        """Handle mouse move for regular (non-OBB) boxes"""
        # Update cursor based on hover state
        if not (self.drawing or self.dragging or self.resizing):
            # Check if hovering over resize handle
            if self.selected_index >= 0 and self.selected_type == 'regular':
                rect, _ = self.boxes[self.selected_index]
                handle_idx = self.get_resize_handle_at_point(screen_pos, rect)
                if handle_idx >= 0:
                    # Set appropriate cursor based on handle position
                    self.set_resize_cursor(handle_idx)
                    return
                elif rect.contains(img_pos):
                    self.setCursor(Qt.SizeAllCursor)
                    return

            # Check if hovering over any box
            if self.get_box_at_point(img_pos) >= 0:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)

        if self.drawing:
            self.end_img_pt = img_pos
        elif self.dragging and self.selected_index >= 0 and self.selected_type == 'regular':
            rect, label = self.boxes[self.selected_index]
            new_pos = img_pos - self.drag_offset
            rect.moveTopLeft(new_pos)
            self.boxes[self.selected_index] = (rect, label)
        elif self.resizing and self.selected_index >= 0 and self.selected_type == 'regular':
            rect, label = self.boxes[self.selected_index]
            delta = img_pos - self.drag_start_pos

            # Calculate new rect based on which handle is being dragged
            new_rect = QRectF(self.original_rect)

            if self.resize_handle in [0, 1, 2]:  # Top handles
                new_rect.setTop(new_rect.top() + delta.y())
            if self.resize_handle in [2, 3, 4]:  # Right handles
                new_rect.setRight(new_rect.right() + delta.x())
            if self.resize_handle in [4, 5, 6]:  # Bottom handles
                new_rect.setBottom(new_rect.bottom() + delta.y())
            if self.resize_handle in [6, 7, 0]:  # Left handles
                new_rect.setLeft(new_rect.left() + delta.x())

            # Ensure minimum size
            if new_rect.width() < 5:
                new_rect.setWidth(5)
            if new_rect.height() < 5:
                new_rect.setHeight(5)

            # Ensure the rectangle is normalized (positive width/height)
            new_rect = new_rect.normalized()

            self.boxes[self.selected_index] = (new_rect, label)

    def set_resize_cursor(self, handle_idx):
        """Set cursor based on resize handle position"""
        handles = ["top-left", "top", "top-right", "right",
                   "bottom-right", "bottom", "bottom-left", "left"]
        handle_type = handles[handle_idx]

        cursor_map = {
            "top-left": Qt.SizeFDiagCursor,
            "top-right": Qt.SizeBDiagCursor,
            "bottom-right": Qt.SizeFDiagCursor,
            "bottom-left": Qt.SizeBDiagCursor,
            "top": Qt.SizeVerCursor,
            "bottom": Qt.SizeVerCursor,
            "left": Qt.SizeHorCursor,
            "right": Qt.SizeHorCursor
        }

        self.setCursor(cursor_map.get(handle_type, Qt.ArrowCursor))

    def handle_obb_mouse_press(self, img_pos):
        """Handle mouse press in OBB mode for drawing new boxes"""
        # CRITICAL: Check if we're clicking on ANY rotation handle first
        screen_pos = QPointF(
            img_pos.x() * self.scale + self.offset_x,
            img_pos.y() * self.scale + self.offset_y
        )

        for box in self.rotated_boxes:
            if self.is_on_rotation_handle(screen_pos, box):
                return  # Don't start drawing, let the rotation handler take over

        # Check if we're clicking on any existing OBB box
        if self.get_obb_at_point(img_pos) >= 0:
            return  # Don't start drawing, let the interaction handler take over

        if not self.drawing_obb:
            # Start drawing new OBB
            self.drawing_obb = True
            self.drawing = False  # Ensure regular drawing is off
            self.dragging = False
            self.resizing = False
            self.rotating = False
            self.obb_points = [img_pos]
            self.obb_temp_line = None
            self.status_message.emit(f"OBB: Click corner {len(self.obb_points)}/4")
        else:
            # Add point to existing OBB drawing
            if len(self.obb_points) < 4:
                self.obb_points.append(img_pos)
                self.status_message.emit(f"OBB: Click corner {len(self.obb_points)}/4")

                if len(self.obb_points) == 4:
                    # Complete the OBB
                    self.complete_obb()
            else:
                # Reset and start new (should not happen with current logic)
                self.drawing_obb = False
                self.obb_points.clear()
                self.handle_obb_mouse_press(img_pos)

    def complete_obb(self):
        """Complete OBB drawing and add rotated box"""
        if len(self.obb_points) == 4:
            # Calculate center, width, height, angle from 4 points
            cx, cy, width, height, angle = self.calculate_obb_from_points(self.obb_points)

            if width > 5 and height > 5:
                label = self.get_current_label()
                self.rotated_boxes.append((cx, cy, width, height, angle, label))
                self.selected_index = len(self.rotated_boxes) - 1
                self.selected_type = 'rotated'

                # Auto-save
                if hasattr(self, 'current_image_path'):
                    self.save_annotations(self.current_image_path)

            self.drawing_obb = False
            self.obb_points.clear()
            self.obb_temp_line = None
            self.status_message.emit("OBB completed")
            self.update()

    def calculate_obb_from_points(self, points):
        """Calculate OBB parameters from 4 corner points"""
        if len(points) != 4:
            return 0, 0, 0, 0, 0

        # Sort points in clockwise order
        center = QPointF(sum(p.x() for p in points) / 4,
                         sum(p.y() for p in points) / 4)

        # Sort by angle around center
        def angle_from_center(p):
            return math.atan2(p.y() - center.y(), p.x() - center.x())

        sorted_points = sorted(points, key=angle_from_center)

        # Calculate width and height
        width = QLineF(sorted_points[0], sorted_points[1]).length()
        height = QLineF(sorted_points[1], sorted_points[2]).length()

        # Calculate angle of the first edge
        angle = math.degrees(math.atan2(
            sorted_points[1].y() - sorted_points[0].y(),
            sorted_points[1].x() - sorted_points[0].x()
        ))

        return center.x(), center.y(), width, height, angle

    def is_on_rotation_handle(self, screen_pos, box):
        """Check if click is on rotation handle"""
        cx, cy, width, height, angle, _ = box
        corners = self.get_rotated_box_corners(cx, cy, width, height, angle)

        # Get the top-left corner (index 0)
        top_left = corners[0]
        screen_top_left = QPointF(
            top_left.x() * self.scale + self.offset_x,
            top_left.y() * self.scale + self.offset_y
        )

        # Calculate handle position - offset from top-left corner
        # Position it diagonally up-left from the corner
        handle_offset = 20  # pixels offset from corner
        handle_pos = QPointF(
            screen_top_left.x() - handle_offset,
            screen_top_left.y() - handle_offset
        )

        # Create a circular hit area
        handle_rect = QRectF(
            handle_pos.x() - self.ROTATE_HANDLE_SIZE,
            handle_pos.y() - self.ROTATE_HANDLE_SIZE,
            self.ROTATE_HANDLE_SIZE * 2,
            self.ROTATE_HANDLE_SIZE * 2
        )

        return handle_rect.contains(screen_pos)

    def mouseMoveEvent(self, event):
        if not self.pixmap:
            return

        screen_pos = event.position()
        img_pos = self.screen_to_image(screen_pos)

        # Update cursor for rotation handles - this should happen even in OBB drawing mode
        if not (self.dragging or self.resizing or self.rotating):
            # Check rotation handles of ALL boxes, not just selected one
            for box in self.rotated_boxes:
                if self.is_on_rotation_handle(screen_pos, box):
                    self.setCursor(Qt.CrossCursor)
                    self.update()
                    return

        # Update cursor for OBB elements - ONLY if not in drawing mode
        if not self.drawing_obb and not (self.drawing or self.dragging or self.resizing or self.rotating):
            if self.selected_index >= 0 and self.selected_type == 'rotated':
                # Check resize handles
                handle_idx = self.get_obb_resize_handle_at_point(screen_pos, self.rotated_boxes[self.selected_index])
                if handle_idx >= 0:
                    self.setCursor(Qt.SizeAllCursor)
                    self.update()
                    return

                # Check if inside box
                cx, cy, width, height, angle, _ = self.rotated_boxes[self.selected_index]
                corners = self.get_rotated_box_corners(cx, cy, width, height, angle)
                polygon = QPolygonF([QPointF(p.x(), p.y()) for p in corners])
                if polygon.containsPoint(img_pos, Qt.OddEvenFill):
                    self.setCursor(Qt.SizeAllCursor)
                    self.update()
                    return

        # Handle OBB drawing - only if we're in drawing mode
        if self.obb_mode and self.drawing_obb and len(self.obb_points) > 0:
            self.obb_temp_line = img_pos
            self.update()
            return

        # Handle OBB rotation
        if self.rotating and self.selected_index >= 0 and self.selected_type == 'rotated':
            self.handle_rotation(img_pos, event)
            return

        # Handle OBB dragging
        if self.dragging and self.selected_index >= 0 and self.selected_type == 'rotated':
            cx, cy, width, height, angle, label = self.rotated_boxes[self.selected_index]
            new_cx = img_pos.x() - self.drag_offset.x()
            new_cy = img_pos.y() - self.drag_offset.y()
            self.rotated_boxes[self.selected_index] = (new_cx, new_cy, width, height, angle, label)
            self.update()
            return

        # Handle OBB resizing
        if self.resizing and self.selected_index >= 0 and self.selected_type == 'rotated':
            self.handle_obb_resize(img_pos, event)
            return

        # Handle regular box operations
        self.handle_regular_box_mouse_move(img_pos, screen_pos)

        self.update()

    def handle_obb_resize(self, img_pos, event):
        """Handle OBB resizing by dragging corners - keeps opposite corner fixed"""
        if self.selected_index >= 0 and self.selected_type == 'rotated':
            cx, cy, width, height, angle, label = self.rotated_boxes[self.selected_index]

            # Get current corners
            corners = self.get_rotated_box_corners(cx, cy, width, height, angle)

            # Which corner is being dragged (0-3)
            dragged_idx = self.resize_handle

            # Opposite corner index (2 for 0, 3 for 1, 0 for 2, 1 for 3)
            opposite_idx = (dragged_idx + 2) % 4

            # Get the opposite corner position (this should stay fixed)
            fixed_point = corners[opposite_idx]

            # Get the two adjacent corners
            adj1_idx = (dragged_idx + 1) % 4
            adj2_idx = (dragged_idx + 3) % 4

            # Calculate new position for dragged corner
            delta_x = img_pos.x() - self.drag_start_pos.x()
            delta_y = img_pos.y() - self.drag_start_pos.y()

            # Create new corners array
            new_corners = list(corners)
            new_corners[dragged_idx] = QPointF(
                corners[dragged_idx].x() + delta_x,
                corners[dragged_idx].y() + delta_y
            )

            # Update adjacent corners to maintain rectangle shape
            # They should lie on lines from fixed point through original adjacent corners
            vec_adj1 = corners[adj1_idx] - fixed_point
            vec_adj2 = corners[adj2_idx] - fixed_point

            # Project dragged corner onto these vectors to find new adjacent positions
            vec_dragged = new_corners[dragged_idx] - fixed_point

            # Calculate scaling factors
            if abs(vec_adj1.x()) > 0.001 or abs(vec_adj1.y()) > 0.001:
                scale1 = (vec_dragged.x() * vec_adj1.x() + vec_dragged.y() * vec_adj1.y()) / (
                            vec_adj1.x() ** 2 + vec_adj1.y() ** 2)
                scale1 = max(0.1, min(10, scale1))  # Limit scale
                new_corners[adj1_idx] = fixed_point + vec_adj1 * scale1

            if abs(vec_adj2.x()) > 0.001 or abs(vec_adj2.y()) > 0.001:
                scale2 = (vec_dragged.x() * vec_adj2.x() + vec_dragged.y() * vec_adj2.y()) / (
                            vec_adj2.x() ** 2 + vec_adj2.y() ** 2)
                scale2 = max(0.1, min(10, scale2))  # Limit scale
                new_corners[adj2_idx] = fixed_point + vec_adj2 * scale2

            # Recalculate OBB from updated corners
            new_cx, new_cy, new_width, new_height, new_angle = self.calculate_obb_from_points(new_corners)

            # Ensure minimum size
            if new_width > 5 and new_height > 5:
                self.rotated_boxes[self.selected_index] = (new_cx, new_cy, new_width, new_height, new_angle, label)
                self.drag_start_pos = img_pos
                self.status_message.emit(f"Resizing: {new_width:.1f} x {new_height:.1f}")

            self.update()

    def handle_rotation(self, img_pos, event):
        """Handle box rotation by dragging the blue circle - rotates relative to start position"""
        if self.selected_index >= 0 and self.selected_type == 'rotated':
            cx, cy, width, height, _, label = self.rotated_boxes[self.selected_index]

            # Calculate current angle between center and mouse position
            current_angle = math.degrees(math.atan2(
                img_pos.y() - cy,
                img_pos.x() - cx
            ))

            # Calculate the angle difference from the start position
            angle_delta = current_angle - self.initial_angle

            # Apply the delta to the original box angle
            new_angle = self.original_angle + angle_delta

            # Normalize angle to 0-360 range
            new_angle = new_angle % 360

            # Snap to angle_step increments if Shift key is pressed
            if event.modifiers() & Qt.ShiftModifier:
                new_angle = round(new_angle / self.angle_step) * self.angle_step

            # Update the box with new angle
            self.rotated_boxes[self.selected_index] = (cx, cy, width, height, new_angle, label)

            # Update status message with current angle
            self.status_message.emit(f"Rotation: {new_angle:.1f}°")

            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Handle OBB completion on release if we have 4 points
            if self.obb_mode and self.drawing_obb and len(self.obb_points) == 4:
                self.complete_obb()
                return

            if self.drawing:
                rect = QRectF(self.start_img_pt, self.end_img_pt).normalized()
                if rect.width() > 5 and rect.height() > 5:
                    label = self.get_current_label()
                    self.regular_boxes.append((rect, label))
                    self.selected_index = len(self.regular_boxes) - 1
                    self.selected_type = 'regular'

                    if hasattr(self, 'current_image_path'):
                        self.save_annotations(self.current_image_path)

                    self.drawing = False

            # Reset all interaction states
            self.dragging = False
            self.resizing = False
            self.rotating = False
            self.resize_handle = -1

            # Clear rotation-specific variables
            self.initial_angle = 0
            self.original_angle = 0

            # Reset cursor
            if self.obb_mode:
                self.setCursor(Qt.CrossCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

            self.update()

    def update_obb_cursor(self, screen_pos):
        """Update cursor when hovering over OBB elements"""
        if self.selected_index >= 0 and self.selected_type == 'rotated':
            # Check rotation handle first
            if self.is_on_rotation_handle(screen_pos, self.rotated_boxes[self.selected_index]):
                self.setCursor(Qt.CrossCursor)
                return True

            # Check resize handles
            handle_idx = self.get_obb_resize_handle_at_point(screen_pos, self.rotated_boxes[self.selected_index])
            if handle_idx >= 0:
                self.setCursor(Qt.SizeAllCursor)
                return True

            # Check if inside box
            cx, cy, width, height, angle, _ = self.rotated_boxes[self.selected_index]
            corners = self.get_rotated_box_corners(cx, cy, width, height, angle)
            img_pos = self.screen_to_image(screen_pos)
            polygon = QPolygonF([QPointF(p.x(), p.y()) for p in corners])

            if polygon.containsPoint(img_pos, Qt.OddEvenFill):
                self.setCursor(Qt.SizeAllCursor)
                return True

        return False

    # ---------------- Rendering ----------------
    def paintEvent(self, event):
        if not self.scaled_pixmap:
            return

        painter = QPainter(self)
        painter.drawPixmap(self.offset_x, self.offset_y, self.scaled_pixmap)

        # Draw regular boxes
        self.draw_regular_boxes(painter)

        # Draw rotated boxes
        self.draw_rotated_boxes(painter)

        # Draw OBB in progress
        if self.obb_mode and self.drawing_obb:
            self.draw_obb_in_progress(painter)

        # Draw temporary box while drawing regular box - MAKE IT VISIBLE
        if self.drawing and not self.obb_mode:
            pen = QPen(Qt.white, 2, Qt.SolidLine)  # Solid white line
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            temp_rect = QRectF(self.start_img_pt, self.end_img_pt).normalized()

            # Add a subtle glow effect
            screen_rect = self.image_to_screen(temp_rect)

            # Draw outer glow (semi-transparent)
            glow_pen = QPen(QColor(255, 255, 255, 100), 4, Qt.SolidLine)
            painter.setPen(glow_pen)
            painter.drawRect(screen_rect)

            # Draw solid white border
            pen = QPen(Qt.white, 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(screen_rect)

            # Draw dimensions text
            width = abs(temp_rect.width())
            height = abs(temp_rect.height())
            if width > 10 and height > 10:
                painter.setPen(Qt.white)
                text = f"{int(width)} x {int(height)}"
                painter.drawText(screen_rect.center() + QPointF(-30, -10), text)

    def draw_regular_boxes(self, painter):
        """Draw all regular (non-rotated) bounding boxes"""
        for i, (rect, label) in enumerate(self.regular_boxes):
            # Get base color for this label
            base_color = self.get_label_color(label)

            if i == self.selected_index and self.selected_type == 'regular':
                # SELECTED BOX: Solid yellow, thicker border
                pen = QPen(Qt.yellow, 3)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(pen)

                r = self.image_to_screen(rect)
                painter.drawRect(r)

                # Draw label with yellow
                painter.setPen(Qt.yellow)
                painter.drawText(r.topLeft() + QPointF(3, -3), label)

                # Draw resize handles for selected box
                painter.setBrush(QBrush(Qt.yellow))
                painter.setPen(QPen(Qt.black, 1))

                for rel_x, rel_y, _ in self.handles:
                    handle_x = r.x() + rel_x * r.width()
                    handle_y = r.y() + rel_y * r.height()

                    handle_rect = QRectF(
                        handle_x - self.HANDLE_SIZE / 2,
                        handle_y - self.HANDLE_SIZE / 2,
                        self.HANDLE_SIZE,
                        self.HANDLE_SIZE
                    )
                    painter.drawRect(handle_rect)

            else:
                # NON-SELECTED BOX: Transparent with thin border
                # Create a semi-transparent color
                transparent_color = QColor(base_color)
                transparent_color.setAlpha(150)  # 150 out of 255 = ~60% opaque

                pen = QPen(transparent_color, 1.5)  # Thinner border
                painter.setBrush(Qt.NoBrush)
                painter.setPen(pen)

                r = self.image_to_screen(rect)
                painter.drawRect(r)

                # Draw label with same transparency
                painter.setPen(transparent_color)
                painter.drawText(r.topLeft() + QPointF(3, -3), label)

    def draw_rotated_boxes(self, painter):
        """Draw all rotated bounding boxes"""
        for i, (cx, cy, width, height, angle, label) in enumerate(self.rotated_boxes):
            corners = self.get_rotated_box_corners(cx, cy, width, height, angle)

            # Convert to screen coordinates
            screen_corners = []
            for point in corners:
                screen_point = QPointF(
                    point.x() * self.scale + self.offset_x,
                    point.y() * self.scale + self.offset_y
                )
                screen_corners.append(screen_point)

            # Draw polygon
            polygon = QPolygonF(screen_corners)

            # Get base color for this label
            base_color = self.get_label_color(label)

            if i == self.selected_index and self.selected_type == 'rotated':
                # SELECTED BOX: Solid yellow, thicker border
                pen = QPen(Qt.yellow, 3)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(pen)
                painter.drawPolygon(polygon)

                # Draw label with yellow
                painter.setPen(Qt.yellow)
                painter.drawText(screen_corners[0] + QPointF(3, -3), label)

                # Draw resize handles at corners
                painter.setBrush(QBrush(Qt.yellow))
                painter.setPen(QPen(Qt.black, 1))
                for corner in screen_corners:
                    handle_rect = QRectF(
                        corner.x() - self.HANDLE_SIZE / 2,
                        corner.y() - self.HANDLE_SIZE / 2,
                        self.HANDLE_SIZE,
                        self.HANDLE_SIZE
                    )
                    painter.drawRect(handle_rect)

                # Draw rotation handle - only for selected box
                top_left = screen_corners[0]
                handle_offset = 20
                handle_pos = QPointF(
                    top_left.x() - handle_offset,
                    top_left.y() - handle_offset
                )

                # Draw rotation handle
                painter.setBrush(QBrush(Qt.cyan))
                painter.setPen(QPen(Qt.blue, 1))
                painter.drawEllipse(handle_pos, self.ROTATE_HANDLE_SIZE, self.ROTATE_HANDLE_SIZE)

                # Draw rotation icon
                painter.setPen(QPen(Qt.blue, 1))
                painter.drawText(handle_pos + QPointF(-8, -8), "↻")

            else:
                # NON-SELECTED BOX: Transparent with thin border
                # Create a semi-transparent color
                transparent_color = QColor(base_color)
                transparent_color.setAlpha(180)  # 180 out of 255 = ~70% opaque

                pen = QPen(transparent_color, 1.5)  # Thinner border
                painter.setBrush(Qt.NoBrush)
                painter.setPen(pen)
                painter.drawPolygon(polygon)

                # Draw label with same transparency
                painter.setPen(transparent_color)
                painter.drawText(screen_corners[0] + QPointF(3, -3), label)

    def draw_obb_in_progress(self, painter):
        """Draw OBB while user is placing points - MAKE IT VISIBLE"""
        if len(self.obb_points) == 0:
            return

        # Draw points with glow effect
        for point in self.obb_points:
            screen_point = QPointF(
                point.x() * self.scale + self.offset_x,
                point.y() * self.scale + self.offset_y
            )

            # Draw outer glow
            painter.setPen(QPen(QColor(255, 255, 255, 100), 4))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(screen_point, 8, 8)

            # Draw solid point
            painter.setPen(QPen(Qt.green, 2))
            painter.setBrush(QBrush(Qt.green))
            painter.drawEllipse(screen_point, 4, 4)

        # Draw lines between points with glow
        if len(self.obb_points) > 1:
            # Draw glow lines
            painter.setPen(QPen(QColor(255, 255, 255, 100), 4, Qt.SolidLine))
            for i in range(len(self.obb_points) - 1):
                p1 = QPointF(
                    self.obb_points[i].x() * self.scale + self.offset_x,
                    self.obb_points[i].y() * self.scale + self.offset_y
                )
                p2 = QPointF(
                    self.obb_points[i + 1].x() * self.scale + self.offset_x,
                    self.obb_points[i + 1].y() * self.scale + self.offset_y
                )
                painter.drawLine(p1, p2)

            # Draw solid lines
            painter.setPen(QPen(Qt.white, 2, Qt.SolidLine))
            for i in range(len(self.obb_points) - 1):
                p1 = QPointF(
                    self.obb_points[i].x() * self.scale + self.offset_x,
                    self.obb_points[i].y() * self.scale + self.offset_y
                )
                p2 = QPointF(
                    self.obb_points[i + 1].x() * self.scale + self.offset_x,
                    self.obb_points[i + 1].y() * self.scale + self.offset_y
                )
                painter.drawLine(p1, p2)

        # Draw temporary line to mouse with glow
        if self.obb_temp_line:
            last_point = self.obb_points[-1]
            p1 = QPointF(
                last_point.x() * self.scale + self.offset_x,
                last_point.y() * self.scale + self.offset_y
            )
            p2 = QPointF(
                self.obb_temp_line.x() * self.scale + self.offset_x,
                self.obb_temp_line.y() * self.scale + self.offset_y
            )

            # Draw glow line
            painter.setPen(QPen(QColor(255, 255, 255, 100), 4, Qt.DashLine))
            painter.drawLine(p1, p2)

            # Draw solid dashed line
            painter.setPen(QPen(Qt.white, 2, Qt.DashLine))
            painter.drawLine(p1, p2)

            # Draw mouse position indicator
            painter.setPen(QPen(Qt.green, 1))
            painter.setBrush(QBrush(QColor(0, 255, 0, 100)))
            painter.drawEllipse(p2, 6, 6)

    # ---------------- Undo ----------------
    def undo_last(self):
        """Undo the last drawn box"""
        if self.regular_boxes:
            # Remove from regular boxes
            self.regular_boxes.pop()
            self.selected_index = -1
            self.selected_type = None
            self.update()
            self.status_message.emit("Last regular box removed")
        elif self.rotated_boxes:
            # Remove from rotated boxes
            self.rotated_boxes.pop()
            self.selected_index = -1
            self.selected_type = None
            self.update()
            self.status_message.emit("Last rotated box removed")

    # Delete selected box
    def delete_selected(self):
        """Delete the selected box"""
        if self.selected_index >= 0:
            if self.selected_type == 'regular' and self.selected_index < len(self.regular_boxes):
                self.regular_boxes.pop(self.selected_index)
                self.status_message.emit("Regular box deleted")
            elif self.selected_type == 'rotated' and self.selected_index < len(self.rotated_boxes):
                self.rotated_boxes.pop(self.selected_index)
                self.status_message.emit("Rotated box deleted")

            self.selected_index = -1
            self.selected_type = None
            self.update()

    # ---------------- Save ----------------
    def save_annotations(self, image_path):
        """Save annotations in YOLO OBB format"""
        if not self.pixmap or not image_path:
            return

        image_width = self.pixmap.width()
        image_height = self.pixmap.height()

        # Save in YOLO OBB format
        yolo_path = os.path.splitext(image_path)[0] + ".txt"
        self.save_yolo_obb_annotations(yolo_path, image_width, image_height)

        # Save class mapping
        folder_path = os.path.dirname(image_path)
        self.save_class_mapping(folder_path)

        print(f"✓ Saved YOLO OBB annotations to: {os.path.basename(yolo_path)}")

    def load_existing_annotations(self, image_path):
        """Load existing YOLO OBB annotations"""
        txt_path = os.path.splitext(image_path)[0] + '.txt'

        if not os.path.exists(txt_path):
            self.regular_boxes.clear()
            self.rotated_boxes.clear()
            self.update()
            return

        # Load classes.txt if exists
        classes_path = os.path.join(os.path.dirname(image_path), 'classes.txt')
        if os.path.exists(classes_path):
            with open(classes_path, 'r', encoding='utf-8') as f:
                class_names = [line.strip() for line in f.readlines() if line.strip()]
                for idx, name in enumerate(class_names):
                    self.label_to_id[name] = idx
                    self.next_class_id = max(self.next_class_id, idx + 1)

        # Load YOLO OBB annotations
        self.regular_boxes.clear()
        self.rotated_boxes.clear()

        with open(txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 9:  # OBB format: class_id x1 y1 x2 y2 x3 y3 x4 y4
                    class_id = int(parts[0])

                    # Get 8 normalized coordinates
                    coords = [float(x) for x in parts[1:9]]

                    img_w = self.pixmap.width()
                    img_h = self.pixmap.height()

                    # Convert to pixel coordinates
                    points = []
                    for i in range(0, 8, 2):
                        x = coords[i] * img_w
                        y = coords[i + 1] * img_h
                        points.append(QPointF(x, y))

                    # Calculate OBB parameters
                    cx = sum(p.x() for p in points) / 4
                    cy = sum(p.y() for p in points) / 4

                    # Calculate width, height, angle
                    width = QLineF(points[0], points[1]).length()
                    height = QLineF(points[1], points[2]).length()
                    angle = math.degrees(math.atan2(
                        points[1].y() - points[0].y(),
                        points[1].x() - points[0].x()
                    ))

                    # Get class name
                    class_name = next((name for name, cid in self.label_to_id.items()
                                       if cid == class_id), str(class_id))

                    self.rotated_boxes.append((cx, cy, width, height, angle, class_name))

        print(f"✓ Loaded {len(self.rotated_boxes)} rotated annotations from {os.path.basename(txt_path)}")
        self.update()

    # Add signal for status messages
    status_message = Signal(str)

    def save_yolo_annotations(self, path, image_width, image_height):
        """Save annotations in YOLO format: class_id x_center y_center width height"""
        lines = []
        for rect, label in self.boxes:
            class_id = self.get_class_id(label)
            x_center, y_center, width, height = self.convert_to_yolo_format(
                rect, image_width, image_height
            )

            # Format: class_id x_center y_center width height
            line = f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
            lines.append(line)

        # Write to file (create empty file if no annotations)
        with open(path, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines))
            # If no boxes, create empty file (image with no objects)

    def save_class_mapping(self, folder_path):
        """Save class_id to label mapping as classes.txt"""
        if not self.label_to_id:
            return

        mapping_path = os.path.join(folder_path, "classes.txt")

        # Sort by class_id to maintain consistent order
        sorted_items = sorted(self.label_to_id.items(), key=lambda x: x[1])

        # Only write if file doesn't exist or needs updating
        write_file = True
        if os.path.exists(mapping_path):
            try:
                with open(mapping_path, "r", encoding="utf-8") as f:
                    existing_labels = [line.strip() for line in f.readlines() if line.strip()]

                # Check if mapping is the same
                if len(existing_labels) == len(sorted_items):
                    match = all(existing_labels[i] == label for i, (label, _) in enumerate(sorted_items))
                    if match:
                        write_file = False
            except:
                pass

        if write_file:
            with open(mapping_path, "w", encoding="utf-8") as f:
                for label, class_id in sorted_items:
                    f.write(f"{label}\n")

            print(f"✓ Saved class mapping to: classes.txt")
            print("Class IDs:")
            for label, class_id in sorted_items:
                print(f"  {class_id}: {label}")

    def generate_data_yaml_after_split(self, capture_image_path, labeling_path):
        """Generate data.yaml with class names from labeling folder"""
        try:
            # Get class mapping from labeling folder
            class_map = self.get_class_map_from_labeling_path(labeling_path)

            yaml_path = os.path.join(capture_image_path, "data.yaml")

            # Use absolute paths
            abs_path = os.path.abspath(capture_image_path)

            # Check if this is an OBB dataset by looking for .obb_mode flag
            is_obb = os.path.exists(os.path.join(labeling_path, ".obb_mode"))

            # Create YAML content
            yaml_content = f"""# YOLOv11 Dataset Configuration
    # Generated by BMP Annotation Tool

    path: {abs_path}
    train: images/train
    val: images/val
    nc: {len(class_map)}
    """

            # Add task specification for OBB
            if is_obb:
                yaml_content += f"task: obb\n"

            yaml_content += f"names:\n"

            # Add class names in order (0, 1, 2, ...)
            for class_id in sorted(class_map.keys()):
                class_name = class_map[class_id]
                yaml_content += f"  {class_id}: {class_name}\n"

            # Write YAML file
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            print(f"✓ Generated {'OBB ' if is_obb else ''}data.yaml at: {yaml_path}")
            print("Class mapping:")
            for class_id, class_name in sorted(class_map.items()):
                print(f"  {class_id}: {class_name}")

            # Also save class names to classes.txt for reference
            self.save_class_names_to_file(capture_image_path, class_map)

            return True

        except Exception as e:
            print(f"Error generating data.yaml: {e}")
            import traceback
            traceback.print_exc()
            return False

    def auto_split_and_generate_yaml(self, source_folder, labeling_path):
        """Auto split dataset and generate data.yaml for YOLO training"""
        try:
            # 1. FIRST SPLIT THE DATASET
            # Create directory structure
            images_train_dir = os.path.join(source_folder, "images", "train")
            images_val_dir = os.path.join(source_folder, "images", "val")
            labels_train_dir = os.path.join(source_folder, "labels", "train")
            labels_val_dir = os.path.join(source_folder, "labels", "val")

            for dir_path in [images_train_dir, images_val_dir, labels_train_dir, labels_val_dir]:
                os.makedirs(dir_path, exist_ok=True)

            # Get all images from source folder
            image_files = []
            for ext in ['.bmp', '.jpg', '.jpeg', '.png', '.tif', '.tiff']:
                image_files.extend([f for f in os.listdir(source_folder)
                                    if f.lower().endswith(ext)])

            if not image_files:
                print("No image files found for training")
                return False

            # Get all label files from source folder
            label_files = [f for f in os.listdir(source_folder)
                           if f.lower().endswith('.txt')]

            # Shuffle and split (80% train, 20% val)
            random.shuffle(image_files)
            split_idx = int(len(image_files) * 0.8)
            train_images = image_files[:split_idx]
            val_images = image_files[split_idx:]

            print(f"Total images: {len(image_files)}")
            print(f"Train images: {len(train_images)}")
            print(f"Val images: {len(val_images)}")

            # Copy images and labels to respective folders
            for img_file in train_images:
                # Copy image
                src_img = os.path.join(source_folder, img_file)
                dst_img = os.path.join(images_train_dir, img_file)
                if os.path.exists(src_img):
                    shutil.copy2(src_img, dst_img)

                # Copy corresponding label file if exists
                label_file = os.path.splitext(img_file)[0] + '.txt'
                if label_file in label_files:
                    src_label = os.path.join(source_folder, label_file)
                    dst_label = os.path.join(labels_train_dir, label_file)
                    if os.path.exists(src_label):
                        shutil.copy2(src_label, dst_label)

            for img_file in val_images:
                # Copy image
                src_img = os.path.join(source_folder, img_file)
                dst_img = os.path.join(images_val_dir, img_file)
                if os.path.exists(src_img):
                    shutil.copy2(src_img, dst_img)

                # Copy corresponding label file if exists
                label_file = os.path.splitext(img_file)[0] + '.txt'
                if label_file in label_files:
                    src_label = os.path.join(source_folder, label_file)
                    dst_label = os.path.join(labels_val_dir, label_file)
                    if os.path.exists(src_label):
                        shutil.copy2(src_label, dst_label)

            # 2. NOW GENERATE DATA.YAML
            success = self.generate_data_yaml_after_split(source_folder, labeling_path)

            if not success:
                print("Warning: Could not generate data.yaml with class names")
                return False

            print(f"✓ Dataset split and data.yaml created successfully!")
            print(f"✓ {len(train_images)} images copied to images/train/")
            print(f"✓ {len(val_images)} images copied to images/val/")
            print(f"✓ Dataset structure ready for YOLOv11 training")

            return True

        except Exception as e:
            print(f"Error in auto_split_and_generate_yaml: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_dataset_structure(self, folder_path):
        """Create suggested YOLO dataset directory structure"""
        # Create images and labels directories
        images_train_dir = os.path.join(folder_path, "images", "train")
        images_val_dir = os.path.join(folder_path, "images", "val")
        labels_train_dir = os.path.join(folder_path, "labels", "train")
        labels_val_dir = os.path.join(folder_path, "labels", "val")

        # Create directories if they don't exist
        os.makedirs(images_train_dir, exist_ok=True)
        os.makedirs(images_val_dir, exist_ok=True)
        os.makedirs(labels_train_dir, exist_ok=True)
        os.makedirs(labels_val_dir, exist_ok=True)

        # Create a simple README file
        readme_path = os.path.join(folder_path, "README.txt")
        readme_content = """YOLOv11 Dataset Structure

This folder contains annotations in YOLO format. For training with YOLOv11:

1. Organize your dataset:
   - Place training images in: images/train/
   - Place validation images in: images/val/
   - Corresponding label files should be in: labels/train/ and labels/val/

2. Update data.yaml paths if needed.

3. For manual organization, you can use this structure:

dataset/
   data.yaml
   classes.txt
   images/
      train/       # Training images
      val/         # Validation images
   labels/
      train/       # Training labels (.txt files)
      val/         # Validation labels (.txt files)

4. To use with YOLOv11:
   yolo train data=data.yaml model=yolo11n.pt

Note: This tool saves annotations directly in the image folder.
You may need to move files to the appropriate train/val folders.
"""

        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)

    def toggle_obb_mode(self, checked):
        """Toggle Oriented Bounding Box mode"""
        self.obb_mode = checked
        if checked:
            self.setCursor(Qt.CrossCursor)
            self.status_message.emit("OBB Mode: Click 4 corners to define rotated box")
        else:
            self.drawing_obb = False
            self.obb_points.clear()
            self.obb_temp_line = None
            self.status_message.emit("OBB Mode disabled")
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def set_obb_mode_flag(self, labeling_path, enabled):
        """Set or remove OBB mode flag file"""
        if labeling_path and os.path.exists(os.path.dirname(labeling_path)):
            flag_path = os.path.join(labeling_path, ".obb_mode")
            try:
                if enabled:
                    with open(flag_path, 'w') as f:
                        f.write('OBB mode enabled')
                    print("✓ OBB mode flag set")
                else:
                    if os.path.exists(flag_path):
                        os.remove(flag_path)
                        print("✓ OBB mode flag removed")
            except Exception as e:
                print(f"Error setting OBB mode flag: {e}")

    def get_class_map_from_labeling_path(self, labeling_path):
        """
        Extract class_id → class_name from filenames like:
        0_SIP.bmp, 1_piano.bmp, 2_phone.bmp
        """
        class_map = {}

        if not os.path.exists(labeling_path):
            print(f"Labeling path does not exist: {labeling_path}")
            # Return default mapping if path doesn't exist
            return {0: "object"}

        print(f"Scanning labeling path: {labeling_path}")
        print(f"Files found: {os.listdir(labeling_path)}")

        for file in os.listdir(labeling_path):
            if not file.lower().endswith(('.bmp', '.jpg', '.jpeg', '.png')):
                continue

            # Remove extension
            name_without_ext = os.path.splitext(file)[0]

            # Split by underscore to get class_id and class_name
            # Format: 0_SIP, 1_piano, etc.
            if '_' in name_without_ext:
                try:
                    # Split only on first underscore in case class_name has underscores
                    parts = name_without_ext.split('_', 1)
                    if len(parts) == 2:
                        cls_id_str = parts[0]
                        cls_name = parts[1]

                        # Convert class_id to integer
                        cls_id = int(cls_id_str)

                        print(f"Found class mapping: {cls_id} -> {cls_name} (from {file})")

                        # Check for conflicts
                        if cls_id in class_map and class_map[cls_id] != cls_name:
                            print(f"⚠️ Warning: Class ID {cls_id} conflict: "
                                  f"'{class_map[cls_id]}' vs '{cls_name}'")
                            # Keep the first one found
                        else:
                            class_map[cls_id] = cls_name

                except ValueError as e:
                    print(f"⚠️ Skipping file {file}: Cannot parse class ID - {e}")
                    continue
                except Exception as e:
                    print(f"⚠️ Skipping file {file}: {e}")
                    continue

        # If no valid files found, use default mapping
        if not class_map:
            print("No valid class files found, using default mapping")
            class_map = {0: "object"}

        # Sort by class_id
        class_map = dict(sorted(class_map.items()))

        print(f"Final class mapping: {class_map}")
        return class_map

    def save_class_names_to_file(self, folder_path, class_map):
        """Save class names in order to classes.txt"""
        classes_txt_path = os.path.join(folder_path, "classes.txt")

        with open(classes_txt_path, "w", encoding="utf-8") as f:
            for class_id in sorted(class_map.keys()):
                class_name = class_map[class_id]
                f.write(f"{class_name}\n")

        print(f"✓ Updated classes.txt with {len(class_map)} classes")
        print("Classes in order:")
        for class_id, class_name in sorted(class_map.items()):
            print(f"  {class_id}: {class_name}")

    def display_predictions(self, predictions):
        """Display model predictions on the image"""
        try:
            print(f"DEBUG [AnnotationWidget]: Received {len(predictions)} predictions")

            # Clear existing boxes first
            self.boxes.clear()
            self.regular_boxes = self.boxes  # Update reference
            self.rotated_boxes.clear()  # Also clear rotated boxes

            for i, pred in enumerate(predictions):
                try:
                    bbox = pred.get('bbox', [0, 0, 0, 0])
                    confidence = pred.get('confidence', 0.0)
                    class_id = pred.get('class_id', 0)
                    actual_class_name = pred.get('class_name', f'class_{class_id}')
                    is_obb = pred.get('is_obb', False)

                    # Use the actual class name
                    label = f"{actual_class_name} ({confidence:.2f})"

                    # Create QRectF from bbox
                    if len(bbox) >= 4:
                        rect = QRectF(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])

                        print(f"DEBUG [AnnotationWidget] Prediction {i}:")
                        print(f"  - Class: '{actual_class_name}' (ID: {class_id})")
                        print(f"  - Label: '{label}'")
                        print(f"  - BBox: {bbox}")
                        print(f"  - Confidence: {confidence:.2f}")
                        print(f"  - Is OBB: {is_obb}")

                        if is_obb and 'corners' in pred:
                            # Handle OBB prediction
                            corners = pred['corners']
                            if len(corners) == 4:
                                # Calculate OBB parameters from corners
                                cx = sum(c[0] for c in corners) / 4
                                cy = sum(c[1] for c in corners) / 4

                                # Calculate width, height, angle
                                width = math.sqrt(
                                    (corners[1][0] - corners[0][0]) ** 2 + (corners[1][1] - corners[0][1]) ** 2)
                                height = math.sqrt(
                                    (corners[2][0] - corners[1][0]) ** 2 + (corners[2][1] - corners[1][1]) ** 2)
                                angle = math.degrees(math.atan2(
                                    corners[1][1] - corners[0][1],
                                    corners[1][0] - corners[0][0]
                                ))

                                self.rotated_boxes.append((cx, cy, width, height, angle, label))
                        else:
                            # Handle regular box
                            self.boxes.append((rect, label))
                    else:
                        print(f"  - ERROR: Invalid bbox format: {bbox}")

                except Exception as e:
                    print(f"Error processing prediction {i}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            self.update()
            print(
                f"DEBUG [AnnotationWidget]: Updated with {len(self.boxes)} regular boxes and {len(self.rotated_boxes)} rotated boxes")

        except Exception as e:
            print(f"FATAL ERROR in display_predictions: {e}")
            import traceback
            traceback.print_exc()

    def clear_calibration_points(self):
        """Clear all calibration points"""
        if hasattr(self, 'calibration_points'):
            self.calibration_points.clear()
        self.update()

    def add_calibration_point(self, pixel_x, pixel_y, world_x, world_y):
        """Add a calibration point"""
        if not hasattr(self, 'calibration_points'):
            self.calibration_points = []

    # for assembly laser remove UI color
    def reset_selection(self):
        """Reset all selection and interaction states and clear all boxes data and UI"""
        # Clear all boxes data
        self.boxes.clear()
        self.regular_boxes = self.boxes  # Update reference
        self.rotated_boxes.clear()

        # Reset selection states
        self.selected_index = -1
        self.selected_type = None
        self.dragging = False
        self.resizing = False
        self.rotating = False
        self.resize_handle = -1

        # Reset drawing states
        self.drawing = False
        self.drawing_obb = False
        self.start_img_pt = QPointF()
        self.end_img_pt = QPointF()
        self.current_rect = None

        # Reset OBB drawing states
        self.obb_points.clear()
        self.obb_temp_line = None
        self.obb_corners = []

        # Clear any temporary or cached data
        self.temp_box_corners = []

        # Force complete redraw
        self.update()

    # use for prevent multiple bounding box
    def safe_clear_boxes(self):
        """Safely clear ALL boxes and reset selection"""
        # Clear regular boxes
        self.boxes.clear()
        self.regular_boxes = self.boxes  # Update reference

        # Clear rotated boxes
        self.rotated_boxes.clear()

        # Reset ALL selection and interaction states
        self.selected_index = -1
        self.selected_type = None
        self.drawing = False
        self.dragging = False
        self.resizing = False
        self.rotating = False
        self.resize_handle = -1

        # Reset OBB drawing states
        self.drawing_obb = False
        self.obb_points.clear()
        self.obb_temp_line = None

        # Reset any temporary variables
        self.current_rect = None
        self.start_img_pt = QPointF()
        self.end_img_pt = QPointF()

        # Force complete redraw
        self.update()
