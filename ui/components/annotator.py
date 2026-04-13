import os
import random
import shutil
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QImage, QFont,
    QBrush, QCursor, QPalette, QLinearGradient)
from PySide6.QtCore import Qt, QRectF, QPointF


class AnnotationWidget(QWidget):
    def __init__(self, get_current_label, get_label_color):
        super().__init__()
        self.get_current_label = get_current_label
        self.get_label_color = get_label_color

        self.pixmap = None
        self.scaled_pixmap = None

        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self.drawing = False
        self.start_img_pt = QPointF()
        self.end_img_pt = QPointF()

        # [(QRectF, label)]
        self.boxes = []

        # Keep track of label to class_id mapping
        self.label_to_id = {}
        self.next_class_id = 0

        # Selection and editing state
        self.selected_index = -1  # Index of selected box
        self.dragging = False  # Whether dragging the entire box
        self.resizing = False  # Whether resizing the box
        self.resize_handle = -1  # Which resize handle is being used

        # Define handle positions
        self.HANDLE_SIZE = 8
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

    def check_training_ready(self, folder_path):
        """Check if dataset is ready for training"""
        yaml_path = os.path.join(folder_path, "data.yaml")
        if not os.path.exists(yaml_path):
            return False, "data.yaml not found"

        # Check if train/val folders exist and have files
        images_train_dir = os.path.join(folder_path, "images", "train")
        images_val_dir = os.path.join(folder_path, "images", "val")

        if not os.path.exists(images_train_dir) or not os.path.exists(images_val_dir):
            return False, "Train/val folders not found"

        # Check if there are images in train folder
        train_images = [f for f in os.listdir(images_train_dir) if f.lower().endswith('.bmp')]
        if len(train_images) == 0:
            return False, "No training images found"

        return True, f"Ready for training: {len(train_images)} training images"

    # ---------------- Image handling ----------------
    def load_image(self, path):
        if not path.lower().endswith(".bmp"):
            return
        self.pixmap = QPixmap(path)
        self.current_image_path = path  # Store current image path
        self.update_scaled_pixmap()

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
        if not self.pixmap:
            return

        screen_pos = event.position()
        img_pos = self.screen_to_image(screen_pos)

        if event.button() == Qt.LeftButton:
            # Check if clicking on a resize handle of selected box
            if self.selected_index >= 0:
                rect, _ = self.boxes[self.selected_index]
                handle_idx = self.get_resize_handle_at_point(screen_pos, rect)
                if handle_idx >= 0:
                    self.resizing = True
                    self.resize_handle = handle_idx
                    self.drag_start_pos = img_pos
                    self.original_rect = rect
                    return

            # Check if clicking inside an existing box
            box_idx = self.get_box_at_point(img_pos)
            if box_idx >= 0:
                self.selected_index = box_idx
                self.dragging = True
                self.drag_start_pos = img_pos
                self.drag_offset = img_pos - self.boxes[box_idx][0].topLeft()
                self.update()
                return

            # Otherwise start drawing a new box
            self.selected_index = -1
            self.drawing = True
            self.start_img_pt = img_pos
            self.end_img_pt = img_pos

        elif event.button() == Qt.RightButton:
            # Right click to select box without dragging
            box_idx = self.get_box_at_point(img_pos)
            self.selected_index = box_idx
            self.dragging = False
            self.resizing = False
            self.update()

        self.update()

    def mouseMoveEvent(self, event):
        if not self.pixmap:
            return

        screen_pos = event.position()
        img_pos = self.screen_to_image(screen_pos)

        # Update cursor based on hover state
        if not (self.drawing or self.dragging or self.resizing):
            # Check if hovering over resize handle
            if self.selected_index >= 0:
                rect, _ = self.boxes[self.selected_index]
                handle_idx = self.get_resize_handle_at_point(screen_pos, rect)
                if handle_idx >= 0:
                    # Set appropriate cursor based on handle position
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

                    if handle_type in cursor_map:
                        self.setCursor(cursor_map[handle_type])
                    else:
                        self.setCursor(Qt.ArrowCursor)
                    self.update()
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
        elif self.dragging and self.selected_index >= 0:
            rect, label = self.boxes[self.selected_index]
            new_pos = img_pos - self.drag_offset
            rect.moveTopLeft(new_pos)
            self.boxes[self.selected_index] = (rect, label)
        elif self.resizing and self.selected_index >= 0:
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

            self.boxes[self.selected_index] = (new_rect.normalized(), label)

        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.drawing:
                rect = QRectF(self.start_img_pt, self.end_img_pt).normalized()
                if rect.width() > 5 and rect.height() > 5:  # Minimum size
                    label = self.get_current_label()

                    color = self.get_label_color(label)
                    print(f"Box added with label '{label}', color: {color.name()}")

                    # REMOVED: Get average color and save to JSON
                    # Just add the box without color saving
                    self.boxes.append((rect, label))
                    self.selected_index = len(self.boxes) - 1

                    # Original save (YOLO format only)
                    if hasattr(self, 'current_image_path'):
                        self.save_annotations(self.current_image_path)

                self.drawing = False

            self.dragging = False
            self.resizing = False
            self.setCursor(Qt.CrossCursor)
            self.update()

    # ---------------- Rendering ----------------
    def paintEvent(self, event):
        if not self.scaled_pixmap:
            return

        painter = QPainter(self)
        painter.drawPixmap(self.offset_x, self.offset_y, self.scaled_pixmap)

        # Draw all boxes
        for i, (rect, label) in enumerate(self.boxes):
            # Get color - use the label as-is or extract class name
            color = self.get_label_color(label)

            # IMPORTANT: Use SOLID lines for all boxes
            if i == self.selected_index:
                # Selected box: solid yellow border (NOT dashed)
                pen = QPen(Qt.yellow, 2, Qt.SolidLine)  # Changed from DashLine to SolidLine
            else:
                # Normal box: solid color border
                pen = QPen(color, 2, Qt.SolidLine)

            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            r = self.image_to_screen(rect)
            painter.drawRect(r)

            # Draw label
            if i == self.selected_index:
                painter.setPen(Qt.yellow)
            else:
                painter.setPen(color)

            # Check if this is a numeric label (like "0", "1", "2")
            # or a text label (like "piano", "SIP_TEST")
            if label.isdigit():
                # This is a numeric label like "0" - add class ID
                class_id = self.get_class_id(label)
                label_text = f"{label} ({class_id})"
            else:
                # This is a text label - display as-is
                label_text = label

            painter.drawText(r.topLeft() + QPointF(3, -3), label_text)

            # Draw resize handles for selected box
            if i == self.selected_index:
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

        # Draw temporary box while drawing (ONLY this should be dashed)
        if self.drawing:
            pen = QPen(Qt.white, 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            temp = QRectF(self.start_img_pt, self.end_img_pt).normalized()
            painter.drawRect(self.image_to_screen(temp))

    # ---------------- Undo ----------------
    def undo_last(self):
        if self.boxes:
            if self.selected_index == len(self.boxes) - 1:
                self.selected_index = -1
            self.boxes.pop()
            self.update()

    # Delete selected box
    def delete_selected(self):
        if self.selected_index >= 0:
            self.boxes.pop(self.selected_index)
            self.selected_index = -1
            self.update()

    # ---------------- Save ----------------
    def save_annotations(self, image_path):
        """Save annotations in YOLO format"""
        if not self.pixmap or not image_path:
            return

        image_width = self.pixmap.width()
        image_height = self.pixmap.height()

        # Save in YOLO format
        yolo_path = os.path.splitext(image_path)[0] + ".txt"
        self.save_yolo_annotations(yolo_path, image_width, image_height)

        # Save class mapping
        folder_path = os.path.dirname(image_path)
        self.save_class_mapping(folder_path)

        print(f"✓ Saved YOLO annotations to: {os.path.basename(yolo_path)}")

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

    def auto_split_and_generate_yaml(self, source_folder, labeling_path):
        """
        Split dataset by COPYING files from:
            source_folder/positive
            source_folder/negative
            source_folder/empty

        Originals remain untouched.
        """
        try:
            images_train_dir = os.path.join(source_folder, "images", "train")
            images_val_dir = os.path.join(source_folder, "images", "val")
            labels_train_dir = os.path.join(source_folder, "labels", "train")
            labels_val_dir = os.path.join(source_folder, "labels", "val")

            for dir_path in [images_train_dir, images_val_dir, labels_train_dir, labels_val_dir]:
                os.makedirs(dir_path, exist_ok=True)

            # optional: clear old generated split only
            for folder in [images_train_dir, images_val_dir, labels_train_dir, labels_val_dir]:
                for f in os.listdir(folder):
                    fp = os.path.join(folder, f)
                    if os.path.isfile(fp):
                        os.remove(fp)

            category_folders = ["positive", "negative", "empty"]
            valid_exts = ('.bmp', '.jpg', '.jpeg', '.png', '.tif', '.tiff')

            total_train = 0
            total_val = 0

            for category in category_folders:
                category_path = os.path.join(source_folder, category)

                if not os.path.exists(category_path):
                    print(f"⚠️ Folder not found: {category_path}")
                    continue

                image_files = [
                    f for f in os.listdir(category_path)
                    if f.lower().endswith(valid_exts)
                ]

                if not image_files:
                    print(f"⚠️ No images found in: {category_path}")
                    continue

                random.shuffle(image_files)

                if len(image_files) == 1:
                    split_idx = 1
                else:
                    split_idx = max(1, int(len(image_files) * 0.8))
                    if split_idx >= len(image_files):
                        split_idx = len(image_files) - 1

                train_images = image_files[:split_idx]
                val_images = image_files[split_idx:]

                print(f"\n{category}: total={len(image_files)}, train={len(train_images)}, val={len(val_images)}")

                # COPY train
                for img_file in train_images:
                    src_img = os.path.join(category_path, img_file)
                    dst_img_name = f"{category}_{img_file}"
                    dst_img = os.path.join(images_train_dir, dst_img_name)
                    shutil.copy2(src_img, dst_img)

                    label_file = os.path.splitext(img_file)[0] + ".txt"
                    src_label = os.path.join(category_path, label_file)
                    dst_label_name = f"{category}_{label_file}"
                    dst_label = os.path.join(labels_train_dir, dst_label_name)

                    if os.path.exists(src_label):
                        shutil.copy2(src_label, dst_label)
                    else:
                        with open(dst_label, "w", encoding="utf-8") as f:
                            pass

                # COPY val
                for img_file in val_images:
                    src_img = os.path.join(category_path, img_file)
                    dst_img_name = f"{category}_{img_file}"
                    dst_img = os.path.join(images_val_dir, dst_img_name)
                    shutil.copy2(src_img, dst_img)

                    label_file = os.path.splitext(img_file)[0] + ".txt"
                    src_label = os.path.join(category_path, label_file)
                    dst_label_name = f"{category}_{label_file}"
                    dst_label = os.path.join(labels_val_dir, dst_label_name)

                    if os.path.exists(src_label):
                        shutil.copy2(src_label, dst_label)
                    else:
                        with open(dst_label, "w", encoding="utf-8") as f:
                            pass

                total_train += len(train_images)
                total_val += len(val_images)

            if total_train == 0 and total_val == 0:
                print("❌ No images found in positive/negative/empty")
                return False

            success = self.generate_data_yaml_after_split(source_folder, labeling_path)

            if not success:
                print("❌ Failed to generate data.yaml")
                return False

            print(f"\n✅ Done")
            print(f"Train images: {total_train}")
            print(f"Val images: {total_val}")
            print("Original files in positive/negative/empty remain unchanged.")

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

    def generate_data_yaml_after_split(self, capture_image_path, labeling_path):
        """Generate data.yaml with class names from labeling folder"""
        try:
            # Get class mapping from labeling folder
            class_map = self.get_class_map_from_labeling_path(labeling_path)

            # CRITICAL: Ensure classes are contiguous starting from 0
            # If you have classes 0 and 1, but not 2, that's fine
            # But the mapping should only include your actual classes
            class_map = dict(sorted(class_map.items()))

            # Verify class IDs are contiguous
            expected_ids = list(range(len(class_map)))
            actual_ids = list(class_map.keys())
            if actual_ids != expected_ids:
                print(f"⚠️ Warning: Class IDs are not contiguous: {actual_ids}")
                print(f"   Expected: {expected_ids}")
                print("   This can cause detection of non-existent classes!")

            yaml_path = os.path.join(capture_image_path, "data.yaml")

            # Use absolute paths
            abs_path = os.path.abspath(capture_image_path)

            # Create YAML content with CORRECT number of classes
            yaml_content = f"""# YOLOv11 Dataset Configuration
# Generated by BMP Annotation Tool

path: {abs_path}
train: images/train
val: images/val

# IMPORTANT: nc MUST equal the number of classes you have
nc: {len(class_map)}

names:
"""

            # Add class names in order (0, 1, 2, ...)
            for class_id in sorted(class_map.keys()):
                class_name = class_map[class_id]
                yaml_content += f"  {class_id}: {class_name}\n"

            # Write YAML file
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            print(f"✓ Generated data.yaml at: {yaml_path}")
            print(f"✓ Number of classes (nc): {len(class_map)}")
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
        print(f"DEBUG [AnnotationWidget]: Received {len(predictions)} predictions")

        # Clear existing boxes first
        self.boxes.clear()

        for i, pred in enumerate(predictions):
            bbox = pred.get('bbox', [0, 0, 0, 0])
            confidence = pred.get('confidence', 0.0)
            class_id = pred.get('class_id', 0)
            actual_class_name = pred.get('class_name', f'class_{class_id}')  # Get the actual name

            # Use the actual class name
            label = f"{actual_class_name} ({confidence:.2f})"  # This will be "PLC (0.99)"

            # Create QRectF from bbox
            if len(bbox) >= 4:
                rect = QRectF(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])

                print(f"DEBUG [AnnotationWidget] Prediction {i}:")
                print(f"  - Class: '{actual_class_name}' (ID: {class_id})")  # Changed this line
                print(f"  - Storing label as: '{label}'")
                print(f"  - BBox: {bbox}")
                print(f"  - Confidence: {confidence:.2f}")

                self.boxes.append((rect, label))
            else:
                print(f"  - ERROR: Invalid bbox format: {bbox}")

        self.update()
        print(f"DEBUG [AnnotationWidget]: Updated with {len(self.boxes)} boxes")

    def save_predictions_as_annotations(self, image_path, predictions, format_type="yolo"):
        """
        Save predictions as annotations in specified format

        Args:
            image_path: Path to the image file
            predictions: List of prediction dictionaries
            format_type: "yolo" or "pixel" or "both"
        """
        if not self.pixmap or not image_path:
            return

        image_width = self.pixmap.width()
        image_height = self.pixmap.height()

        # Create labels directory if it doesn't exist
        labels_dir = os.path.join(os.path.dirname(image_path), "labels")
        os.makedirs(labels_dir, exist_ok=True)

        # Get base filename
        base_name = os.path.splitext(os.path.basename(image_path))[0]

        if format_type in ["yolo", "both"]:
            # Save YOLO format
            yolo_path = os.path.join(labels_dir, base_name + ".txt")
            self._save_yolo_predictions(yolo_path, predictions, image_width, image_height)

        if format_type in ["pixel", "both"]:
            # Save pixel coordinates format
            pixel_path = os.path.join(labels_dir, base_name + "_pixel.txt")
            self._save_pixel_predictions(pixel_path, predictions)

        print(f"✓ Saved predictions as annotations in {format_type} format")

    def _save_yolo_predictions(self, filepath, predictions, image_width, image_height):
        """Save predictions in YOLO format (normalized)"""
        lines = []
        for pred in predictions:
            bbox = pred['bbox']  # [x1, y1, x2, y2]
            class_id = pred['class_id']

            # Convert to YOLO format (x_center, y_center, width, height, normalized)
            x_center = ((bbox[0] + bbox[2]) / 2) / image_width
            y_center = ((bbox[1] + bbox[3]) / 2) / image_height
            width = (bbox[2] - bbox[0]) / image_width
            height = (bbox[3] - bbox[1]) / image_height

            # Ensure values are within [0, 1] range
            x_center = max(0, min(1, x_center))
            y_center = max(0, min(1, y_center))
            width = max(0, min(1, width))
            height = max(0, min(1, height))

            # Format: class_id x_center y_center width height
            line = f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
            lines.append(line)

        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines))

        print(f"  - YOLO format saved to: {os.path.basename(filepath)}")

        # Also print first few lines for verification
        if lines:
            print("  Sample YOLO format:")
            for i, line in enumerate(lines[:3]):
                print(f"    Box {i}: {line}")

    def _save_pixel_predictions(self, filepath, predictions):
        """Save predictions in pixel coordinates format"""
        lines = []
        for pred in predictions:
            bbox = pred['bbox']  # [x1, y1, x2, y2]
            class_id = pred['class_id']
            class_name = pred.get('class_name', f'class_{class_id}')
            confidence = pred['confidence']

            # Format: class_id class_name confidence x1 y1 x2 y2
            line = f"{class_id} {class_name} {confidence:.4f} {bbox[0]:.1f} {bbox[1]:.1f} {bbox[2]:.1f} {bbox[3]:.1f}"
            lines.append(line)

        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Format: class_id class_name confidence x1 y1 x2 y2\n")
            if lines:
                f.write("\n".join(lines))

        print(f"  - Pixel format saved to: {os.path.basename(filepath)}")

        # Also print first few lines for verification
        if lines:
            print("  Sample pixel format:")
            for i, line in enumerate(lines[:3]):
                print(f"    Box {i}: {line}")

    def get_average_color(self, rect: QRectF) -> tuple:
        """Get average RGB color from the selected region"""
        if not self.pixmap:
            return None

        # Convert QRectF to integer coordinates
        x1 = max(0, int(rect.x()))
        y1 = max(0, int(rect.y()))
        x2 = min(self.pixmap.width(), int(rect.x() + rect.width()))
        y2 = min(self.pixmap.height(), int(rect.y() + rect.height()))

        if x1 >= x2 or y1 >= y2:
            return None

        # Get image as QImage
        img = self.pixmap.toImage().convertToFormat(QImage.Format_RGB32)

        # Calculate average color
        r_sum = g_sum = b_sum = 0
        pixel_count = 0

        for y in range(y1, y2):
            for x in range(x1, x2):
                color = QColor(img.pixel(x, y))
                r_sum += color.red()
                g_sum += color.green()
                b_sum += color.blue()
                pixel_count += 1

        if pixel_count == 0:
            return None

        return (r_sum / pixel_count, g_sum / pixel_count, b_sum / pixel_count)