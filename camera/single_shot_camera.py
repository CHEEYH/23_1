# camera/single_shot_camera.py
import numpy as np
import pyrealsense2 as rs
from PySide6.QtCore import QThread, Signal

class SingleShotCameraThread(QThread):
    """Single shot camera thread"""
    frame_captured = Signal(np.ndarray)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        print("📸 Camera thread starting...")
        pipeline = None
        try:
            pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

            print("📸 Starting camera pipeline...")
            pipeline.start(config)

            # Wait for one frame (increase timeout)
            print("📸 Waiting for camera frame...")
            frames = pipeline.wait_for_frames(5000)  # 5 second timeout
            frame = frames.get_color_frame()

            if frame:
                img = np.asanyarray(frame.get_data())
                print(f"📸 Got camera frame, size: {img.shape}")
                self.frame_captured.emit(img)
            else:
                print("❌ Unable to get camera frame")
                self.error_occurred.emit("Unable to get camera frame")

        except RuntimeError as e:
            error_msg = f"RealSense Error: {str(e)}"
            print(f"❌ {error_msg}")
            self.error_occurred.emit(error_msg)
        except Exception as e:
            error_msg = f"Camera Error: {str(e)}"
            print(f"❌ {error_msg}")
            self.error_occurred.emit(error_msg)
        finally:
            print("📸 Cleaning up camera resources...")
            if pipeline:
                try:
                    pipeline.stop()
                except:
                    pass
            self.running = False
            print("📸 Camera thread ended")

    def stop(self):
        self.running = False
        if self.isRunning():
            self.quit()
            self.wait(2000)