# camera/camera_thread.py
import numpy as np
import pyrealsense2 as rs
from PySide6.QtCore import QThread, Signal

class CameraThread(QThread):
    frame_ready = Signal(np.ndarray)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        self.running = True
        try:
            pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            pipeline.start(config)

            while self.running:
                frames = pipeline.wait_for_frames()
                frame = frames.get_color_frame()
                if frame:
                    self.frame_ready.emit(np.asanyarray(frame.get_data()))
        except Exception as e:
            print("Camera Error:", str(e))
            self.running = False
        finally:
            try:
                pipeline.stop()
            except:
                pass

    def stop(self):
        self.running = False
        self.quit()
        self.wait(1000)