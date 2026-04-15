import time
import gc
import math
import random
import cv2
import numpy as np
import mediapipe as mp
import winsound
import json
import os
import threading


from PySide6.QtCore import QThread, Signal
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from pyorbbecsdk import *
from pyorbbecsdk import OBSensorType, OBFormat

BaseOptions = python.BaseOptions
HandLandmarker = vision.HandLandmarker
HandLandmarkerOptions = vision.HandLandmarkerOptions

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17)
]


def create_hand_landmarker():
    options = HandLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path="hand_landmarker.task",
            delegate=python.BaseOptions.Delegate.CPU
        ),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.55,
        min_hand_presence_confidence=0.55,
        min_tracking_confidence=0.55
    )
    return HandLandmarker.create_from_options(options)


class OrbbecCameraThread(QThread):
    frame_signal = Signal(np.ndarray)
    error_signal = Signal(str)
    status_signal = Signal(str)

    start_pipeline_signal = Signal()  # First trigger (show QR popup)
    confirm_qr_signal = Signal()  # Second trigger (confirm QR)

    trigger_continue_signal = Signal()  # Hold 3s
    trigger_stop_signal = Signal()  # Hold 5s

    ok_status_signal = Signal()
    ng_status_signal = Signal(str)
    idle_status_signal = Signal()

    def __init__(self):
        super().__init__()
        self.running = True

        self.ctx = None
        self.pipeline = None
        self.config = None

        self.hand_landmarker = None
        self.last_result = None

        self.frame_counter = 0
        self.start_timestamp = None

        self.label_switch_threshold = 5
        self.handedness_score_threshold = 0.80

        self.next_track_id = 0
        self.hand_tracks = {}
        self.max_tracking_distance = 200
        self.max_missing_frames = 8

        self.landmark_smoothing_alpha = 0.65
        self.box_smoothing_alpha = 0.70

        self.process_every_n = 1

        # Target box (alarm)
        self.target_box = None
        self.target_box_size = 100
        self.warning_active = False
        self.request_new_target = False
        self.external_target_bbox = None
        self.target_lock = threading.Lock()
        self.use_external_target = True

        self.target_enter_time = None
        self.alarm_delay_sec = 0.5

        self.wrong_location_enter_time = None
        self.wrong_location_delay_sec = 1

        self.clear_error_delay_sec = 0.35  # 50ms
        self.clear_error_start_time = None

        # ========== SINGLE TRIGGER BOX WITH STATE ==========
        self.trigger_box = None
        self.trigger_box_size = 120
        self.trigger_position = {
            "relative_x": 0.4999999999999997,  # ← 确保这些存在
            "relative_y": 0.6499999999999998,
            "size": 60
        }

        # State machine
        self.trigger_state = "idle"  # idle, waiting_qr, confirmed, missing_decision
        self.trigger_enter_time = None
        self.trigger_delay_sec = 1.0
        self.trigger_was_used = False  # Prevent re-trigger in same state

        # Missing-object special mode
        self.trigger_mode = "normal"  # normal / missing_decision
        self.trigger_continue_delay_sec = 3.0
        self.trigger_stop_delay_sec = 5.0
        self.trigger_last_stage = None

        # Visual colors for different states
        self.trigger_colors = {
            "idle": (255, 165, 0),  # Orange - ready to start
            "waiting_qr": (0, 255, 255),  # Cyan - waiting for QR scan
            "confirmed": (0, 255, 0)  # Green - confirmed, running
        }

        self.use_trigger_boxes = True
        # ===================================================

        # ========== NEW: Store all detection boxes ==========
        self.all_detection_boxes = []  # List of (bbox, class_name, confidence)
        self.all_boxes_lock = threading.Lock()
        # ===================================================

        self.resolution_printed = False

        self.latest_frame = None
        self.request_capture = False
        self.capture_index = 0

        # sound control
        self.last_beep_time = 0.0
        self.beep_interval_sec = 0.5
        self.beep_frequency = 2500
        self.beep_duration_ms = 50

        self.orbbec_homography = None

        # ========== TRACK ERROR STATE ==========
        self.error_sent = False  # Track if error message already sent
        # ======================================

        # ========== UI STATUS STATE ==========
        self._last_ui_status = "idle"  # idle / ok / ng
        self._last_ng_name = ""
        # ====================================

        # ===== UI delay control =====
        self.ok_enter_time = None
        self.ng_enter_time = None
        self.ui_delay_sec = 0.5
        # ===========================

    def stop(self):
        self.running = False
        self.wait(3000)
        if self.isRunning():
            self.terminate()

    def load_orbbec_homography(self):
        try:
            homography_path = r"C:\Users\PC_AI_DS\Desktop\Xlent\23_1\orbbec_homography.json"

            os.makedirs(os.path.dirname(homography_path), exist_ok=True)

            if not os.path.exists(homography_path):
                self.status_signal.emit(f"Homography file not found: {homography_path}")
                print(f"⚠ Homography file not found: {homography_path}")
                self.orbbec_homography = None
                return None

            with open(homography_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            H = np.array(data["homography"], dtype=np.float32)
            self.orbbec_homography = H

            print(f"✅ Loaded Orbbec homography from: {homography_path}")
            print("Homography matrix:")
            print(H)

            return H


        except Exception as e:

            self.status_signal.emit(f"Failed to load homography: {e}")

            print(f"❌ Failed to load homography: {e}")

            self.orbbec_homography = None

            return None

    def map_bbox_with_homography(self, bbox, H):
        x1, y1, x2, y2 = bbox[:4]

        corners = np.array([
            [[x1, y1]],
            [[x2, y1]],
            [[x2, y2]],
            [[x1, y2]],
        ], dtype=np.float32)

        mapped = cv2.perspectiveTransform(corners, H)

        xs = mapped[:, 0, 0]
        ys = mapped[:, 0, 1]

        nx1 = int(round(xs.min()))
        ny1 = int(round(ys.min()))
        nx2 = int(round(xs.max()))
        ny2 = int(round(ys.max()))

        return (nx1, ny1, nx2, ny2)

    def set_recipe_name(self, recipe_name):
        self.current_recipe_name = recipe_name

    def init_trigger_box(self, frame_shape):
        """Initialize trigger box at fixed position"""
        if self.trigger_box is not None:
            return

        h, w = frame_shape[:2]
        size = self.trigger_position["size"]
        center_x = int(w * self.trigger_position["relative_x"])
        center_y = int(h * self.trigger_position["relative_y"])

        x1 = max(10, min(w - size - 10, center_x - size // 2))
        y1 = max(10, min(h - size - 10, center_y - size // 2))
        self.trigger_box = (x1, y1, x1 + size, y1 + size)

        print(f"🔲 Trigger box initialized at: {self.trigger_box}")

    def set_trigger_state(self, state):
        """Change trigger box state externally (from main_page)"""
        self.trigger_state = state
        self.trigger_enter_time = None
        self.trigger_was_used = False
        print(f"[Orbbec] Trigger state changed to: {state}")

    def set_trigger_mode(self, mode="normal"):
        """Change trigger behavior mode."""
        self.trigger_mode = mode
        self.trigger_enter_time = None
        self.trigger_was_used = False
        self.trigger_last_stage = None
        print(f"[Orbbec] Trigger mode changed to: {mode}")

    def reset_trigger_progress(self):
        """Reset current hold progress."""
        self.trigger_enter_time = None
        self.trigger_was_used = False
        self.trigger_last_stage = None

    def check_hand_in_trigger_box(self, hand_landmarks_smoothed, frame_shape):
        """Check if hand is inside trigger box"""
        if self.trigger_box is None:
            return False

        tx1, ty1, tx2, ty2 = self.trigger_box
        h, w = frame_shape[:2]

        tx1 = max(0, min(w - 1, tx1))
        ty1 = max(0, min(h - 1, ty1))
        tx2 = max(0, min(w - 1, tx2))
        ty2 = max(0, min(h - 1, ty2))

        for lm in hand_landmarks_smoothed:
            lx = int(lm[0] * w)
            ly = int(lm[1] * h)
            if tx1 <= lx <= tx2 and ty1 <= ly <= ty2:
                return True
        return False

    def draw_trigger_box(self, frame, hand_inside=False):
        """Draw trigger box with state-appropriate styling"""
        if self.trigger_box is None or not self.use_trigger_boxes:
            return frame

        x1, y1, x2, y2 = self.trigger_box
        color = self.trigger_colors.get(self.trigger_state, (255, 165, 0))

        if self.trigger_mode == "missing_decision":
            label = "HOLD 3S=CONTINUE / 5S=STOP"
            color = (0, 255, 255) if hand_inside else (255, 165, 0)
        else:
            labels = {
                "idle": "HAND HERE TO START",
                "waiting_qr": "SCAN QR THEN HOLD HERE",
                "confirmed": "✓ CONFIRMED - RUNNING"
            }
            label = labels.get(self.trigger_state, "TRIGGER BOX")

        show_countdown = hand_inside and not self.trigger_was_used and self.trigger_enter_time is not None

        thickness = 4 if hand_inside else 3
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        corner_len = 20
        cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, 3)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, 3)
        cv2.line(frame, (x2, y1), (x2 - corner_len, y1), color, 3)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, 3)
        cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, 3)
        cv2.line(frame, (x1, y2), (x1, y2 - corner_len), color, 3)
        cv2.line(frame, (x2, y2), (x2 - corner_len, y2), color, 3)
        cv2.line(frame, (x2, y2), (x2, y2 - corner_len), color, 3)

        label_x = x1 + (x2 - x1) // 2 - 120
        label_y = max(y1 - 10, 25)

        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(
            frame,
            (label_x - 5, label_y - text_h - 3),
            (label_x + text_w + 5, label_y + 5),
            (0, 0, 0),
            -1
        )
        cv2.putText(frame, label, (label_x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        if show_countdown:
            elapsed = time.perf_counter() - self.trigger_enter_time

            if self.trigger_mode == "missing_decision":
                center_x = x1 + (x2 - x1) // 2
                center_y = y2 + 25
                radius = 20

                # 3秒 Continue 提示
                if elapsed < self.trigger_continue_delay_sec:
                    remain = self.trigger_continue_delay_sec - elapsed
                    progress = elapsed / self.trigger_continue_delay_sec

                    cv2.circle(frame, (center_x, center_y), radius, (50, 50, 50), -1)
                    cv2.circle(frame, (center_x, center_y), radius, (0, 255, 255), 2)

                    angle = int(360 * progress)
                    cv2.ellipse(frame, (center_x, center_y), (radius - 3, radius - 3), 90, 0, angle, (0, 255, 255), 3)

                    cv2.putText(frame, f"{max(1, int(math.ceil(remain)))}",
                                (center_x - 10, center_y + 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                    cv2.putText(frame, "CONTINUE",
                                (x1 - 5, y2 + 55),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                # 3~5秒 Stop 提示
                elif elapsed < self.trigger_stop_delay_sec:
                    remain = self.trigger_stop_delay_sec - elapsed
                    progress = (elapsed - self.trigger_continue_delay_sec) / (
                            self.trigger_stop_delay_sec - self.trigger_continue_delay_sec
                    )

                    cv2.circle(frame, (center_x, center_y), radius, (50, 50, 50), -1)
                    cv2.circle(frame, (center_x, center_y), radius, (0, 0, 255), 2)

                    angle = int(360 * progress)
                    cv2.ellipse(frame, (center_x, center_y), (radius - 3, radius - 3), 90, 0, angle, (0, 0, 255), 3)

                    cv2.putText(frame, f"{max(1, int(math.ceil(remain)))}",
                                (center_x - 10, center_y + 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                    cv2.putText(frame, "STOP",
                                (x1 + 20, y2 + 55),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            else:
                if elapsed < self.trigger_delay_sec:
                    remain = self.trigger_delay_sec - elapsed

                    center_x = x1 + (x2 - x1) // 2
                    center_y = y2 + 25
                    radius = 20

                    cv2.circle(frame, (center_x, center_y), radius, (50, 50, 50), -1)
                    cv2.circle(frame, (center_x, center_y), radius, color, 2)

                    angle = int(360 * (elapsed / self.trigger_delay_sec))
                    cv2.ellipse(frame, (center_x, center_y), (radius - 3, radius - 3), 90, 0, angle, color, 3)

                    cv2.putText(frame, f"{int(remain)}", (center_x - 12, center_y + 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                    progress = elapsed / self.trigger_delay_sec
                    bar_width = int((x2 - x1) * progress)
                    cv2.rectangle(frame, (x1, y2 + 5), (x1 + bar_width, y2 + 12), (0, 255, 0), -1)
                    cv2.rectangle(frame, (x1, y2 + 5), (x2, y2 + 12), (100, 100, 100), 1)

        return frame

    def update_trigger_logic(self, hand_in_box, current_time):
        """Handle trigger state machine safely"""
        if not self.use_trigger_boxes:
            return

        if current_time is None:
            return

        if self.trigger_state == "confirmed":
            return

        # safety guards
        if self.trigger_enter_time is not None and not isinstance(self.trigger_enter_time, (int, float)):
            self.trigger_enter_time = None

        if self.trigger_mode == "missing_decision" and self.trigger_last_stage is None:
            self.trigger_last_stage = None

        if hand_in_box and not self.trigger_was_used:
            if self.trigger_enter_time is None:
                self.trigger_enter_time = current_time
                self.trigger_last_stage = None
                self.status_signal.emit(f"Hand in trigger box - holding to {self.trigger_state}")
                return

            if self.trigger_enter_time is None:
                return

            elapsed = current_time - self.trigger_enter_time

            # ===== Missing decision mode: 3s continue, 5s stop =====
            if self.trigger_mode == "missing_decision":
                if elapsed >= self.trigger_stop_delay_sec:
                    self.trigger_was_used = True
                    self.trigger_enter_time = None
                    self.trigger_last_stage = "stop"
                    print("[Orbbec] 🖐️ Hold 5s - STOP")
                    self.status_signal.emit("Hold 5s detected - stopping pipeline")
                    self.trigger_stop_signal.emit()
                    return

                elif elapsed >= self.trigger_continue_delay_sec:
                    if self.trigger_last_stage != "continue_ready":
                        self.trigger_last_stage = "continue_ready"
                        self.status_signal.emit("Hold 3s reached - release now to continue")
                return

            # ===== Normal mode =====
            if elapsed >= self.trigger_delay_sec:
                self.trigger_was_used = True
                self.trigger_enter_time = None

                if self.trigger_state == "idle":
                    print("[Orbbec] 🖐️ First trigger - Starting pipeline (QR popup)")
                    self.status_signal.emit("Triggered! Opening QR scanner...")
                    self.start_pipeline_signal.emit()

                elif self.trigger_state == "waiting_qr":
                    print("[Orbbec] 🖐️ Second trigger - Confirming QR and running pipeline")
                    self.status_signal.emit("QR confirmed! Starting assembly...")
                    self.confirm_qr_signal.emit()

                elif self.trigger_state == "assembly":
                    print("[Orbbec] 🖐️ Assembly trigger - verify/continue")
                    self.status_signal.emit("Assembly trigger detected")
                    self.start_pipeline_signal.emit()

                elif self.trigger_state == "result":
                    print("[Orbbec] 🖐️ Result trigger - continue")
                    self.status_signal.emit("Result continue trigger")
                    self.start_pipeline_signal.emit()

                elif self.trigger_state == "screw":
                    print("[Orbbec] 🖐️ Screw trigger")
                    self.status_signal.emit("Screw trigger detected")
                    self.start_pipeline_signal.emit()

                elif self.trigger_state == "video":
                    print("[Orbbec] 🖐️ Video trigger - continue")
                    self.status_signal.emit("Video continue trigger")
                    self.start_pipeline_signal.emit()

                else:
                    print(f"[Orbbec] 🖐️ Unknown trigger state '{self.trigger_state}' - fallback start")
                    self.status_signal.emit(f"Trigger fallback for state: {self.trigger_state}")
                    self.start_pipeline_signal.emit()

        else:
            # Hand left box
            if self.trigger_enter_time is not None and isinstance(self.trigger_enter_time, (int, float)):
                elapsed = current_time - self.trigger_enter_time

                if self.trigger_mode == "missing_decision":
                    # release after >=3s and <5s => continue
                    if self.trigger_continue_delay_sec <= elapsed < self.trigger_stop_delay_sec and not self.trigger_was_used:
                        self.trigger_was_used = True
                        self.trigger_enter_time = None
                        self.trigger_last_stage = "continue"
                        print("[Orbbec] 🖐️ Released after 3s - CONTINUE")
                        self.status_signal.emit("Released after 3s - continuing pipeline")
                        self.trigger_continue_signal.emit()
                        return

                self.status_signal.emit("Hand left trigger box - cancelled")

            self.trigger_enter_time = None
            self.trigger_last_stage = None

    def set_trigger_box_position(self, relative_x=0.85, relative_y=0.85, size=120):
        """
        动态改变 trigger box 位置

        Args:
            relative_x: 0.0 = 左边, 1.0 = 右边
            relative_y: 0.0 = 顶部, 1.0 = 底部
            size: 像素大小
        """
        # 更新位置配置
        self.trigger_position = {
            "relative_x": relative_x,
            "relative_y": relative_y,
            "size": size
        }

        # 重置 trigger box，下次绘制时会重新计算
        self.trigger_box = None

        print(f"🔲 Trigger box position updated to: X={relative_x}, Y={relative_y}, size={size}")

        # 如果有当前帧，立即重新初始化
        if hasattr(self, 'latest_frame') and self.latest_frame is not None:
            self.init_trigger_box(self.latest_frame.shape)
            print(f"   New trigger box position: {self.trigger_box}")

    # =============================================

    def randomize_target(self):
        self.request_new_target = True
        self.target_enter_time = None
        self.warning_active = False

    def capture_image(self):
        self.request_capture = True

    def set_external_target_bbox(self, bbox):
        with self.target_lock:
            if bbox and len(bbox) >= 4:
                print("\n========== INPUT RAW BBOX ==========")
                print(f"bbox = {bbox}")

                if self.orbbec_homography is None:
                    self.load_orbbec_homography()

                if self.orbbec_homography is not None:
                    try:
                        mapped_bbox = self.map_bbox_with_homography(bbox, self.orbbec_homography)
                        x1, y1, x2, y2 = mapped_bbox

                        print("\n========== AFTER HOMOGRAPHY ==========")
                        print(f"mapped_bbox = {mapped_bbox}")

                    except Exception as e:
                        print(f"❌ Homography mapping failed: {e}")
                        x1, y1, x2, y2 = bbox[:4]
                else:
                    print("⚠ No homography loaded, fallback to raw bbox")
                    x1, y1, x2, y2 = bbox[:4]

                x1 = int(round(x1))
                y1 = int(round(y1))
                x2 = int(round(x2))
                y2 = int(round(y2))

                print("\n========== AFTER ROUND ==========")
                print(f"Rounded bbox: x1={x1}, y1={y1}, x2={x2}, y2={y2}")

                if self.latest_frame is not None:
                    h, w = self.latest_frame.shape[:2]
                    print("\n========== FRAME SIZE ==========")
                    print(f"Frame width={w}, height={h}")

                    x1 = max(0, min(w - 1, x1))
                    y1 = max(0, min(h - 1, y1))
                    x2 = max(0, min(w - 1, x2))
                    y2 = max(0, min(h - 1, y2))

                    print("\n========== AFTER CLAMP ==========")
                    print(f"Clamped bbox: x1={x1}, y1={y1}, x2={x2}, y2={y2}")

                self.external_target_bbox = (x1, y1, x2, y2)
                self.target_box = self.external_target_bbox
                self.request_new_target = False
                self.target_enter_time = None
                self.warning_active = False

                print("\n========== FINAL TARGET BOX ==========")
                print(f"self.external_target_bbox = {self.external_target_bbox}")
                print("======================================\n")

            else:
                self.external_target_bbox = None
                print("\n[set_external_target_bbox] Invalid bbox, set to None\n")

    def clear_external_target_bbox(self):
        with self.target_lock:
            self.external_target_bbox = None
            self.target_box = None
            self.request_new_target = True
            self.target_enter_time = None
            self.warning_active = False

    def play_alarm_sound_async(self):
        """Non-blocking alarm sound"""

        def _play():
            try:
                winsound.Beep(self.beep_frequency, self.beep_duration_ms)
            except:
                pass

        threading.Thread(target=_play, daemon=True).start()

    def distance(self, p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def get_palm_center_xy(self, hand, frame_shape):
        h, w = frame_shape[:2]
        palm_ids = [0, 5, 9, 13, 17]
        xs = [hand[i].x * w for i in palm_ids]
        ys = [hand[i].y * h for i in palm_ids]
        return int(sum(xs) / len(xs)), int(sum(ys) / len(ys))

    def get_bbox_xyxy(self, hand, frame_shape):
        h, w = frame_shape[:2]
        xs = [lm.x * w for lm in hand]
        ys = [lm.y * h for lm in hand]
        return (
            int(min(xs)), int(min(ys)),
            int(max(xs)), int(max(ys))
        )

    def is_hand_reliable(self, hand):
        margin = 0.03
        inside = 0
        for lm in hand:
            if margin <= lm.x <= 1.0 - margin and margin <= lm.y <= 1.0 - margin:
                inside += 1
        return inside >= 16

    def create_new_track(self, wrist_xy, palm_xy, bbox_xyxy, raw_label, score, hand_landmarks):
        track_id = self.next_track_id
        self.next_track_id += 1

        self.hand_tracks[track_id] = {
            "wrist": wrist_xy,
            "palm": palm_xy,
            "bbox": bbox_xyxy,
            "stable_label": raw_label,
            "candidate_label": raw_label,
            "candidate_count": 1,
            "missing_frames": 0,
            "score": score,
            "smoothed_landmarks": np.array([[lm.x, lm.y, lm.z] for lm in hand_landmarks], dtype=np.float32),
        }
        return track_id

    def smooth_hand_landmarks(self, track_id, hand_landmarks):
        track = self.hand_tracks[track_id]
        current = np.array([[lm.x, lm.y, lm.z] for lm in hand_landmarks], dtype=np.float32)

        if track["smoothed_landmarks"] is None:
            track["smoothed_landmarks"] = current
            return current

        alpha = self.landmark_smoothing_alpha
        prev = track["smoothed_landmarks"]
        smoothed = alpha * current + (1.0 - alpha) * prev
        track["smoothed_landmarks"] = smoothed
        return smoothed

    def smooth_bbox(self, track_id, bbox_xyxy):
        track = self.hand_tracks[track_id]
        current = np.array(bbox_xyxy, dtype=np.float32)

        if track["bbox"] is None:
            track["bbox"] = tuple(current.astype(int))
            return track["bbox"]

        prev = np.array(track["bbox"], dtype=np.float32)
        alpha = self.box_smoothing_alpha
        smoothed = alpha * current + (1.0 - alpha) * prev
        track["bbox"] = tuple(smoothed.astype(int))
        return track["bbox"]

    def cleanup_lost_tracks(self):
        for track_id in list(self.hand_tracks.keys()):
            if self.hand_tracks[track_id]["missing_frames"] > self.max_missing_frames:
                del self.hand_tracks[track_id]

    def update_stable_label(self, track_id, raw_label, score):
        track = self.hand_tracks[track_id]

        if raw_label == track["stable_label"]:
            track["candidate_label"] = raw_label
            track["candidate_count"] = 1
            track["score"] = score
            return track["stable_label"]

        if raw_label == track["candidate_label"]:
            track["candidate_count"] += 1
        else:
            track["candidate_label"] = raw_label
            track["candidate_count"] = 1

        if (
                track["candidate_count"] >= self.label_switch_threshold
                and score >= self.handedness_score_threshold
        ):
            track["stable_label"] = raw_label
            track["candidate_count"] = 0

        track["score"] = score
        return track["stable_label"]

    def match_hands_to_tracks(self, detections):
        if not detections:
            for track_id in list(self.hand_tracks.keys()):
                self.hand_tracks[track_id]["missing_frames"] += 1
            self.cleanup_lost_tracks()
            return []

        assigned_tracks = set()
        assigned_detections = []

        for det in detections:
            palm_xy = det["palm"]

            best_track_id = None
            best_dist = 1e9

            for track_id, track in self.hand_tracks.items():
                if track_id in assigned_tracks:
                    continue

                dist = self.distance(palm_xy, track["palm"])
                if dist < best_dist and dist < self.max_tracking_distance:
                    best_dist = dist
                    best_track_id = track_id

            if best_track_id is None:
                best_track_id = self.create_new_track(
                    det["wrist"],
                    det["palm"],
                    det["bbox"],
                    det["raw_label"],
                    det["score"],
                    det["hand_landmarks"]
                )
            else:
                track = self.hand_tracks[best_track_id]
                track["wrist"] = det["wrist"]
                track["palm"] = det["palm"]
                track["score"] = det["score"]
                track["missing_frames"] = 0

            assigned_tracks.add(best_track_id)
            det["track_id"] = best_track_id
            assigned_detections.append(det)

        for track_id in list(self.hand_tracks.keys()):
            if track_id not in assigned_tracks:
                self.hand_tracks[track_id]["missing_frames"] += 1

        self.cleanup_lost_tracks()
        return assigned_detections

    def convert_orbbec_color_frame_to_bgr(self, color_frame):
        if color_frame is None:
            return None

        width = color_frame.get_width()
        height = color_frame.get_height()
        fmt = color_frame.get_format()

        if not self.resolution_printed:
            print("Raw frame width:", width)
            print("Raw frame height:", height)
            print("Raw frame format:", fmt)
            self.resolution_printed = True

        data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)

        try:
            if fmt == OBFormat.RGB:
                img = data.reshape((height, width, 3))
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                return img
            elif fmt == OBFormat.BGR:
                img = data.reshape((height, width, 3))
                return img
            elif fmt == OBFormat.MJPG:
                img = cv2.imdecode(data, cv2.IMREAD_COLOR)
                return img
            elif fmt == OBFormat.YUYV:
                img = data.reshape((height, width, 2))
                img = cv2.cvtColor(img, cv2.COLOR_YUV2BGR_YUY2)
                return img
            elif fmt == OBFormat.UYVY:
                img = data.reshape((height, width, 2))
                img = cv2.cvtColor(img, cv2.COLOR_YUV2BGR_UYVY)
                return img
            else:
                self.status_signal.emit(f"Unsupported color format: {fmt}")
                return None

        except Exception as e:
            self.status_signal.emit(f"Frame conversion error: {e}")
            return None

    def setup_orbbec_pipeline(self):
        self.ctx = Context()
        dev_list = self.ctx.query_devices()

        if dev_list.get_count() == 0:
            raise RuntimeError("No Orbbec device found")

        self.pipeline = Pipeline()
        self.config = Config()

        profile_list = self.pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        color_profile = None

        preferred_settings = [
            (640, 480, OBFormat.MJPG, 30),
            (640, 480, OBFormat.RGB, 30),
            (640, 480, OBFormat.YUYV, 30),
            (1280, 720, OBFormat.MJPG, 30),
        ]

        for width, height, fmt, fps in preferred_settings:
            try:
                color_profile = profile_list.get_video_stream_profile(width, height, fmt, fps)
                if color_profile is not None:
                    self.status_signal.emit(
                        f"Using color profile: {width}x{height}, format={fmt}, fps={fps}"
                    )
                    break
            except Exception:
                pass

        if color_profile is None:
            color_profile = profile_list.get_default_video_stream_profile()
            self.status_signal.emit("Using default color profile")

        self.config.enable_stream(color_profile)
        self.pipeline.start(self.config)

        self.status_signal.emit("Orbbec color stream started")

    def draw_hands_and_target(self, frame, result):
        if frame is None:
            return frame

        h, w = frame.shape[:2]

        # ========== TARGET BOX (from AI detection) ==========
        with self.target_lock:
            external_bbox = self.external_target_bbox

        if external_bbox is not None and self.use_external_target:
            x1, y1, x2, y2 = external_bbox

            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))

            if x2 > x1 and y2 > y1:
                self.target_box = (x1, y1, x2, y2)
                self.request_new_target = False
            else:
                self.target_box = None
        else:
            # 沒有 detection 就不要 target box
            self.target_box = None
            self.request_new_target = False

        # Draw target box
        if self.target_box is not None:
            tx1, ty1, tx2, ty2 = self.target_box

            cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (0, 255, 255), 2)
            cv2.putText(
                frame,
                "TARGET",
                (tx1, max(ty1 - 8, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

        # ========== HAND DETECTION ==========
        hit_target = False
        detections = []

        if result and result.hand_landmarks and result.handedness:
            for i, hand in enumerate(result.hand_landmarks):
                if i >= len(result.handedness):
                    continue

                if not self.is_hand_reliable(hand):
                    continue

                handed = result.handedness[i][0]
                raw_label = handed.category_name
                score = float(handed.score)

                wrist = hand[0]
                wx = int(wrist.x * frame.shape[1])
                wy = int(wrist.y * frame.shape[0])
                palm_xy = self.get_palm_center_xy(hand, frame.shape)
                bbox_xyxy = self.get_bbox_xyxy(hand, frame.shape)

                detections.append({
                    "wrist": (wx, wy),
                    "palm": palm_xy,
                    "bbox": bbox_xyxy,
                    "raw_label": raw_label,
                    "score": score,
                    "hand_landmarks": hand
                })

        assigned_detections = self.match_hands_to_tracks(detections)

        # Track hand positions
        hand_in_trigger = False
        hand_in_wrong_location = False
        wrong_location_name = None

        for det in assigned_detections:
            hand = det["hand_landmarks"]
            raw_label = det["raw_label"]
            score = det["score"]
            track_id = det["track_id"]

            stable_label = self.update_stable_label(track_id, raw_label, score)
            smoothed = self.smooth_hand_landmarks(track_id, hand)
            smoothed_bbox = self.smooth_bbox(track_id, det["bbox"])

            x1, y1, x2, y2 = smoothed_bbox
            palm_x, palm_y = self.hand_tracks[track_id]["palm"]

            color = (0, 255, 0) if stable_label.lower() == "left" else (255, 0, 0)

            # Draw hand landmarks
            for lm in smoothed:
                x = int(lm[0] * frame.shape[1])
                y = int(lm[1] * frame.shape[0])
                cv2.circle(frame, (x, y), 4, color, -1)

            # Draw hand connections
            for c1, c2 in HAND_CONNECTIONS:
                x1l = int(smoothed[c1][0] * frame.shape[1])
                y1l = int(smoothed[c1][1] * frame.shape[0])
                x2l = int(smoothed[c2][0] * frame.shape[1])
                y2l = int(smoothed[c2][1] * frame.shape[0])
                cv2.line(frame, (x1l, y1l), (x2l, y2l), color, 2)

            # Draw hand bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, (palm_x, palm_y), 6, color, -1)
            cv2.putText(
                frame,
                f"{stable_label} ({score:.2f})",
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2
            )

            # Check for target box hit (alarm condition)
            if self.target_box is not None:
                tx1, ty1, tx2, ty2 = self.target_box

                for lm in smoothed:
                    lx = int(lm[0] * frame.shape[1])
                    ly = int(lm[1] * frame.shape[0])
                    if tx1 <= lx <= tx2 and ty1 <= ly <= ty2:
                        hit_target = True
                        break

            # Check if hand is inside trigger box
            if self.use_trigger_boxes:
                if self.check_hand_in_trigger_box(smoothed, frame.shape):
                    hand_in_trigger = True

            # ========== WRONG LOCATION DETECTION ==========
            if hasattr(self, 'all_detection_boxes') and self.all_detection_boxes:
                for box_info in self.all_detection_boxes:
                    bx1, by1, bx2, by2 = box_info['bbox']
                    class_name = box_info['class_name']

                    for lm in smoothed:
                        lx = int(lm[0] * frame.shape[1])
                        ly = int(lm[1] * frame.shape[0])
                        if bx1 <= lx <= bx2 and by1 <= ly <= by2:
                            # Check if this is the target box
                            if self.target_box is not None:
                                tx1, ty1, tx2, ty2 = self.target_box
                                if not (abs(bx1 - tx1) < 50 and abs(by1 - ty1) < 50):
                                    hand_in_wrong_location = True
                                    wrong_location_name = class_name
                                    print(f"⚠ WRONG LOCATION DETECTED: Hand on {class_name}")
                            else:
                                hand_in_wrong_location = True
                                wrong_location_name = class_name
                            break
            # =============================================

        # ========== TARGET BOX OK LOGIC ==========
        current_time = time.perf_counter()

        if hit_target:
            self.target_enter_time = current_time if self.target_enter_time is None else self.target_enter_time
            self.warning_active = False

            cv2.putText(
                frame,
                "OK: HAND INSIDE TARGET",
                (10, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )
        else:
            self.target_enter_time = None
            self.warning_active = False

        # ========== WRONG LOCATION FEEDBACK ==========
        if hand_in_wrong_location and not hit_target:
            if self.wrong_location_enter_time is None:
                self.wrong_location_enter_time = current_time
                self.status_signal.emit(f"Hand on wrong location: {wrong_location_name}")
                print(f"[WRONG LOCATION] Timer started for: {wrong_location_name}")

            elapsed_in_wrong = current_time - self.wrong_location_enter_time

            if self.wrong_location_delay_sec > 0:
                remain = max(0.0, self.wrong_location_delay_sec - elapsed_in_wrong)
                cv2.putText(
                    frame,
                    f"{remain:.1f}s",
                    (10, h - 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 165, 255),
                    2
                )

            if elapsed_in_wrong >= self.wrong_location_delay_sec:
                if not self.error_sent:
                    self.send_tcp_message_async("error")
                    self.error_sent = True
                    print(
                        f"📤 [TCP] error (hand stayed on wrong location for {self.wrong_location_delay_sec:.1f}s: {wrong_location_name})")

                self.play_wrong_location_sound_async()
                cv2.putText(
                    frame,
                    f"WRONG LOCATION! Hand on {wrong_location_name}",
                    (10, h - 110),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )
        else:

            if self.wrong_location_enter_time is not None:
                self.wrong_location_enter_time = None
                self.clear_error_start_time = current_time

            if self.clear_error_start_time is not None:
                elapsed_clear = current_time - self.clear_error_start_time

                if elapsed_clear >= self.clear_error_delay_sec:
                    self.send_tcp_message_async("clear_error")
                    self.error_sent = False
                    self.clear_error_start_time = None

                    print("📤 [TCP] clear_error (after 50ms delay)")

        # ========== UI OK / NG / IDLE STATUS ==========
        current_time = time.perf_counter()

        # ===== NG（wrong location）=====
        if hand_in_wrong_location and not hit_target:
            if self.ng_enter_time is None:
                self.ng_enter_time = current_time

            elapsed_ng = current_time - self.ng_enter_time

            if elapsed_ng >= self.ui_delay_sec:
                self._emit_ui_status("ng", wrong_location_name or "")
            else:
                # 還沒到1秒 → 不顯示
                self._emit_ui_status("idle")

            # reset OK timer
            self.ok_enter_time = None

        # ===== OK（target）=====
        elif hit_target:
            if self.ok_enter_time is None:
                self.ok_enter_time = current_time

            elapsed_ok = current_time - self.ok_enter_time

            if elapsed_ok >= self.ui_delay_sec:
                self._emit_ui_status("ok")
            else:
                self._emit_ui_status("idle")

            # reset NG timer
            self.ng_enter_time = None

        # ===== IDLE =====
        else:
            self.ok_enter_time = None
            self.ng_enter_time = None
            self._emit_ui_status("idle")

        # ========== DRAW ALL DETECTION BOXES (for wrong location visual) ==========
        if hasattr(self, 'all_detection_boxes') and self.all_detection_boxes:
            with self.all_boxes_lock:
                for box_info in self.all_detection_boxes:
                    x1, y1, x2, y2 = box_info['bbox']
                    class_name = box_info['class_name']
                    confidence = box_info['confidence']

                    if 'cover' in class_name.lower():
                        color = (255, 100, 100)
                    elif 'base' in class_name.lower():
                        color = (100, 255, 100)
                    elif 'pcb' in class_name.lower():
                        color = (100, 100, 255)
                    else:
                        color = (200, 200, 200)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    label = f"{class_name}: {confidence:.2f}"
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(y1 - 5, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        1
                    )

        # ========== TRIGGER BOX LOGIC ==========
        if self.use_trigger_boxes:
            if self.trigger_box is None:
                self.init_trigger_box(frame.shape)

            frame = self.draw_trigger_box(frame, hand_in_trigger)
            self.update_trigger_logic(hand_in_trigger, current_time)

        return frame

    def play_wrong_location_sound_async(self):
        """Non-blocking wrong location sound"""

        def _play():
            try:
                winsound.Beep(1500, 50)
                winsound.Beep(1500, 50)
            except:
                pass

        threading.Thread(target=_play, daemon=True).start()

    def send_tcp_message_async(self, message):
        """Non-blocking TCP message"""

        def _send():
            try:
                from ui.components.pipeline_runner import PipelineRunner
                if PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected():
                    PipelineRunner._heartbeat_manager.send_data(f"{message}\n")
                else:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.5)
                    sock.connect(('127.0.0.1', 8888))
                    sock.send(f"{message}\n".encode())
                    sock.close()
                print(f"📤 [TCP] {message}")
            except Exception as e:
                pass

        threading.Thread(target=_send, daemon=True).start()

    def _emit_ui_status(self, status, ng_name=""):
        """
        Emit UI-only status signals without spamming repeated emits.
        status: idle / ok / ng
        """
        try:
            if status == "ok":
                if self._last_ui_status != "ok":
                    self.ok_status_signal.emit()
                self._last_ui_status = "ok"
                self._last_ng_name = ""

            elif status == "ng":
                if self._last_ui_status != "ng" or self._last_ng_name != ng_name:
                    self.ng_status_signal.emit(ng_name or "")
                self._last_ui_status = "ng"
                self._last_ng_name = ng_name or ""

            else:
                if self._last_ui_status != "idle":
                    self.idle_status_signal.emit()
                self._last_ui_status = "idle"
                self._last_ng_name = ""

        except Exception as e:
            print(f"[Orbbec] UI status emit error: {e}")

    def run(self):
        try:
            self.setup_orbbec_pipeline()
            self.load_orbbec_homography()
            self.hand_landmarker = create_hand_landmarker()
            self.start_timestamp = time.perf_counter()
            frame_count = 0

            while self.running:
                frames = self.pipeline.wait_for_frames(100)
                if frames is None:
                    continue

                color_frame = frames.get_color_frame()
                if color_frame is None:
                    continue

                frame_bgr = self.convert_orbbec_color_frame_to_bgr(color_frame)
                if frame_bgr is None:
                    continue

                display_frame = frame_bgr.copy()
                self.latest_frame = frame_bgr.copy()

                frame_count += 1

                if self.frame_counter % self.process_every_n == 0:
                    try:
                        rgb_for_mp = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_for_mp)
                        timestamp_ms = int((time.perf_counter() - self.start_timestamp) * 1000)

                        self.last_result = self.hand_landmarker.detect_for_video(
                            mp_image,
                            timestamp_ms
                        )
                    except Exception as e:
                        self.status_signal.emit(f"MediaPipe error: {e}")

                display_frame = self.draw_hands_and_target(display_frame, self.last_result)

                elapsed = time.perf_counter() - self.start_timestamp
                live_fps = frame_count / elapsed if elapsed > 0 else 0.0

                # cv2.putText(
                #     display_frame,
                #     "Source: Orbbec SDK",
                #     (10, 30),
                #     cv2.FONT_HERSHEY_SIMPLEX,
                #     0.7,
                #     (0, 255, 255),
                #     2
                # )
                #
                # cv2.putText(
                #     display_frame,
                #     f"FPS: {live_fps:.1f}",
                #     (10, 60),
                #     cv2.FONT_HERSHEY_SIMPLEX,
                #     0.6,
                #     (0, 255, 255),
                #     2
                # )
                #
                # cv2.putText(
                #     display_frame,
                #     "Press R = new target | C = capture",
                #     (10, 90),
                #     cv2.FONT_HERSHEY_SIMPLEX,
                #     0.6,
                #     (0, 255, 255),
                #     2
                # )

                if self.request_capture and self.latest_frame is not None:
                    filename = f"capture_{self.capture_index:03d}.png"
                    cv2.imwrite(filename, self.latest_frame)
                    self.status_signal.emit(f"Saved image: {filename}")
                    self.capture_index += 1
                    self.request_capture = False

                self.frame_signal.emit(display_frame)

                self.frame_counter += 1
                if self.frame_counter % 30 == 0:
                    gc.collect()

        except Exception as e:
            self.error_signal.emit(f"Thread error: {str(e)}")

        finally:
            try:
                if self.pipeline is not None:
                    self.pipeline.stop()
            except Exception:
                pass

            try:
                if self.hand_landmarker is not None:
                    self.hand_landmarker.close()
            except Exception:
                pass

            self.status_signal.emit("Thread stopped")

    def clear_all_detection_boxes(self):
        """Clear all detection boxes"""
        with self.all_boxes_lock:
            self.all_detection_boxes = []

    def set_all_detection_boxes(self, predictions):
        """Set all detected objects for display"""
        with self.all_boxes_lock:
            self.all_detection_boxes = []
            for pred in predictions:
                bbox = pred.get('bbox', [])
                class_name = pred.get('class_name', 'unknown')
                confidence = pred.get('confidence', 0)

                # Apply homography to each box
                if self.orbbec_homography is not None:
                    try:
                        mapped_bbox = self.map_bbox_with_homography(bbox, self.orbbec_homography)
                        x1, y1, x2, y2 = mapped_bbox
                    except Exception as e:
                        print(f"Homography failed for {class_name}: {e}")
                        x1, y1, x2, y2 = bbox[:4]
                else:
                    x1, y1, x2, y2 = bbox[:4]

                self.all_detection_boxes.append({
                    'bbox': (int(x1), int(y1), int(x2), int(y2)),
                    'class_name': class_name,
                    'confidence': confidence,
                    'is_target': False
                })

    def draw_all_detection_boxes(self, frame):
        """Draw all detection boxes with different colors"""
        with self.all_boxes_lock:
            for box_info in self.all_detection_boxes:
                x1, y1, x2, y2 = box_info['bbox']
                class_name = box_info['class_name']
                confidence = box_info['confidence']

                # Different colors for different objects
                # You can customize based on class_name
                if 'screw' in class_name.lower():
                    color = (255, 100, 100)  # Red
                elif 'bracket' in class_name.lower():
                    color = (100, 255, 100)  # Green
                elif 'connector' in class_name.lower():
                    color = (100, 100, 255)  # Blue
                else:
                    color = (200, 200, 200)  # Gray

                # Draw box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Draw label
                label = f"{class_name}: {confidence:.2f}"
                cv2.putText(frame, label, (x1, max(y1 - 5, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        return frame

    def check_hand_in_wrong_location(self, hand_landmarks_smoothed, frame_shape):
        """Check if hand is in ANY detection box that is NOT the target"""
        if not self.all_detection_boxes:
            return None, None

        h, w = frame_shape[:2]

        for lm in hand_landmarks_smoothed:
            lx = int(lm[0] * w)
            ly = int(lm[1] * h)

            for box_info in self.all_detection_boxes:
                x1, y1, x2, y2 = box_info['bbox']
                class_name = box_info['class_name']

                if x1 <= lx <= x2 and y1 <= ly <= y2:
                    # Check if this is the target box
                    if self.target_box and self.is_same_box((x1, y1, x2, y2), self.target_box):
                        return 'target', class_name
                    else:
                        return 'wrong', class_name

        return None, None

    def is_same_box(self, box1, box2, tolerance=20):
        """Check if two boxes are roughly the same"""
        x1a, y1a, x2a, y2a = box1
        x1b, y1b, x2b, y2b = box2
        return (abs(x1a - x1b) < tolerance and abs(y1a - y1b) < tolerance and
                abs(x2a - x2b) < tolerance and abs(y2a - y2b) < tolerance)

    def play_warning_sound(self, is_wrong_location):
        """Play different sounds for wrong location"""
        try:
            current_time = time.perf_counter()
            if current_time - self.last_beep_time >= self.beep_interval_sec:
                if is_wrong_location:
                    # Wrong location: lower frequency, shorter, two beeps
                    winsound.Beep(1500, 200)
                    time.sleep(0.1)
                    winsound.Beep(1500, 200)
                else:
                    # Correct location: higher frequency, longer
                    winsound.Beep(2500, 300)
                self.last_beep_time = current_time
        except Exception as e:
            self.status_signal.emit(f"Warning sound error: {e}")