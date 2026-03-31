import time
import gc
import math
import random
import cv2
import numpy as np
import mediapipe as mp
import winsound
import threading
import json
import os

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

        self.target_box = None
        self.target_box_size = 100
        self.warning_active = False
        self.request_new_target = False
        self.external_target_bbox = None
        self.target_lock = threading.Lock()
        self.use_external_target = True

        self.target_enter_time = None
        self.alarm_delay_sec = 1.0

        self.resolution_printed = False

        self.latest_frame = None
        self.request_capture = False
        self.capture_index = 0

        # sound control
        self.last_beep_time = 0.0
        self.beep_interval_sec = 0.5
        self.beep_frequency = 2500
        self.beep_duration_ms = 300

        self.current_recipe_name = "C1.1"
        self.orbbec_homography = None

    def stop(self):
        self.running = False
        self.wait(3000)
        if self.isRunning():
            self.terminate()

    def load_orbbec_homography(self):
        try:
            homography_path = os.path.join("recipes", self.current_recipe_name, "orbbec_homography.json")

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
        self.load_orbbec_homography()

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

                # load homography if not loaded yet
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

    def play_alarm_sound(self):
        try:
            current_time = time.perf_counter()
            if current_time - self.last_beep_time >= self.beep_interval_sec:
                winsound.Beep(self.beep_frequency, self.beep_duration_ms)
                self.last_beep_time = current_time
        except Exception as e:
            self.status_signal.emit(f"Alarm sound error: {e}")

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

        with self.target_lock:
            external_bbox = self.external_target_bbox

        if external_bbox is not None and self.use_external_target:
            x1, y1, x2, y2 = external_bbox

            # clamp 到畫面範圍內
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))

            if x2 > x1 and y2 > y1:
                self.target_box = (x1, y1, x2, y2)
                self.request_new_target = False
            else:
                self.target_box = None

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
            if self.target_box is None or self.request_new_target:
                box_size = self.target_box_size
                x1 = random.randint(20, max(21, w - box_size - 20))
                y1 = random.randint(20, max(21, h - box_size - 20))
                self.target_box = (x1, y1, x1 + box_size, y1 + box_size)
                self.request_new_target = False
                self.target_enter_time = None
                self.warning_active = False

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

            for lm in smoothed:
                x = int(lm[0] * frame.shape[1])
                y = int(lm[1] * frame.shape[0])
                cv2.circle(frame, (x, y), 4, color, -1)

            for c1, c2 in HAND_CONNECTIONS:
                x1l = int(smoothed[c1][0] * frame.shape[1])
                y1l = int(smoothed[c1][1] * frame.shape[0])
                x2l = int(smoothed[c2][0] * frame.shape[1])
                y2l = int(smoothed[c2][1] * frame.shape[0])
                cv2.line(frame, (x1l, y1l), (x2l, y2l), color, 2)

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

            for lm in smoothed:
                lx = int(lm[0] * frame.shape[1])
                ly = int(lm[1] * frame.shape[0])
                if tx1 <= lx <= tx2 and ty1 <= ly <= ty2:
                    hit_target = True
                    break

        current_time = time.perf_counter()

        if hit_target:
            if self.target_enter_time is None:
                self.target_enter_time = current_time

            elapsed_in_target = current_time - self.target_enter_time
            remain = max(0.0, self.alarm_delay_sec - elapsed_in_target)

            cv2.putText(
                frame,
                f"In target: {elapsed_in_target:.2f}s",
                (10, h - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

            if elapsed_in_target >= self.alarm_delay_sec:
                self.warning_active = True
                self.play_alarm_sound()

                cv2.putText(
                    frame,
                    "WARNING: HAND INSIDE TARGET",
                    (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2
                )
            else:
                self.warning_active = False
                cv2.putText(
                    frame,
                    f"Alarm in: {remain:.2f}s",
                    (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 255),
                    2
                )
        else:
            self.target_enter_time = None
            self.warning_active = False

        return frame

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

                cv2.putText(
                    display_frame,
                    "Source: Orbbec SDK",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2
                )

                cv2.putText(
                    display_frame,
                    f"FPS: {live_fps:.1f}",
                    (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2
                )

                cv2.putText(
                    display_frame,
                    "Press R = new target | C = capture",
                    (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2
                )

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