# orbbec_debug_window.py
import sys
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QPushButton, QHBoxLayout, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont

from camera.orbbec_camera_thread import OrbbecCameraThread


class OrbbecDebugWindow(QMainWindow):
    """临时调试窗口 - 显示 Orbbec 摄像头画面和 trigger box"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWindowTitle("Orbbec Camera Debug - Trigger Box Test")
        self.setMinimumSize(900, 700)

        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a2e;
            }
            QLabel {
                color: #00FF88;
                font-family: Consolas;
            }
            QPushButton {
                background-color: #0f3460;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #16213e;
            }
            QPushButton:disabled {
                background-color: #2c2c3e;
                color: #666;
            }
        """)

        # 创建中央窗口
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 标题
        title = QLabel("🔴 ORBBEC CAMERA DEBUG VIEW")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #00AAFF;
            padding: 15px;
            background-color: #0d1117;
            border-radius: 10px;
        """)
        layout.addWidget(title)

        # 摄像头画面显示区域
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumHeight(500)
        self.video_label.setStyleSheet("""
            background-color: #000000;
            border: 3px solid #00AAFF;
            border-radius: 8px;
        """)
        self.video_label.setText("等待 Orbbec 摄像头连接...")
        layout.addWidget(self.video_label, stretch=1)

        # 状态信息面板
        info_panel = QFrame()
        info_panel.setStyleSheet("""
            QFrame {
                background-color: #0d1117;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        info_layout = QVBoxLayout(info_panel)

        # 状态信息
        self.status_label = QLabel("📡 状态: 初始化中...")
        self.status_label.setStyleSheet("font-size: 14px; color: #FFAA00;")
        info_layout.addWidget(self.status_label)

        self.trigger_state_label = QLabel("🎯 Trigger 状态: idle")
        self.trigger_state_label.setStyleSheet("font-size: 14px; color: #00AAFF;")
        info_layout.addWidget(self.trigger_state_label)

        self.trigger_box_label = QLabel("📦 Trigger Box 位置: 未初始化")
        self.trigger_box_label.setStyleSheet("font-size: 12px; color: #7AAAD4;")
        info_layout.addWidget(self.trigger_box_label)

        self.frame_info_label = QLabel("📐 画面尺寸: 等待中")
        self.frame_info_label.setStyleSheet("font-size: 12px; color: #7AAAD4;")
        info_layout.addWidget(self.frame_info_label)

        layout.addWidget(info_panel)

        # 按钮区域
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton("▶ 启动摄像头")
        self.start_btn.clicked.connect(self.start_camera)
        button_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止摄像头")
        self.stop_btn.clicked.connect(self.stop_camera)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)

        self.reset_btn = QPushButton("🔄 重置 Trigger")
        self.reset_btn.clicked.connect(self.reset_trigger)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)

        # 提示信息
        tip_label = QLabel(
            "💡 提示:\n"
            "• 橙色/青色框 = Trigger Box (把手放进去保持1秒)\n"
            "• 黄色框 = Target Box (AI 检测到的目标位置)\n"
            "• 手部骨架会显示在画面上\n"
            "• 保持手在 Trigger Box 内 1 秒会触发信号"
        )
        tip_label.setStyleSheet("""
            font-size: 12px;
            color: #888;
            background-color: #0d1117;
            padding: 10px;
            border-radius: 8px;
            margin-top: 5px;
        """)
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        # Orbbec 线程
        self.orbbec_thread = None

        # FPS 计时
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps_info)
        self.frame_count = 0
        self.last_fps_update = 0

    def start_camera(self):
        """启动 Orbbec 摄像头"""
        try:
            print("\n" + "=" * 50)
            print("启动 Orbbec 摄像头...")
            print("=" * 50)

            self.orbbec_thread = OrbbecCameraThread()

            # 连接信号
            self.orbbec_thread.frame_signal.connect(self.update_video_display)
            self.orbbec_thread.status_signal.connect(self.update_status)
            self.orbbec_thread.error_signal.connect(self.update_error)

            # 连接 trigger 信号
            self.orbbec_thread.start_pipeline_signal.connect(self.on_start_trigger)
            self.orbbec_thread.confirm_qr_signal.connect(self.on_confirm_trigger)

            # 启动线程
            self.orbbec_thread.start()

            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)

            # 启动 FPS 计时器
            self.fps_timer.start(1000)
            self.last_fps_update = 0
            self.frame_count = 0

        except Exception as e:
            print(f"❌ 启动失败: {e}")
            self.status_label.setText(f"❌ 启动失败: {str(e)[:50]}")

    def stop_camera(self):
        """停止 Orbbec 摄像头"""
        if self.orbbec_thread:
            self.orbbec_thread.stop()
            self.orbbec_thread = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("📡 状态: 已停止")
        self.video_label.setText("摄像头已停止")
        self.fps_timer.stop()

    def reset_trigger(self):
        """重置 trigger 状态"""
        if self.orbbec_thread:
            self.orbbec_thread.set_trigger_state("idle")
            self.orbbec_thread.trigger_was_used = False
            self.orbbec_thread.trigger_enter_time = None
            self.status_label.setText("🔄 Trigger 已重置")
            print("[Debug] Trigger reset")

    def update_video_display(self, frame):
        """更新视频显示"""
        if frame is None:
            return

        self.frame_count += 1

        try:
            # 转换 BGR 到 RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w

            # 创建 QImage
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)

            # 缩放以适应 label
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.video_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.video_label.setPixmap(scaled)

            # 更新画面尺寸信息
            if self.frame_count % 30 == 0:
                self.frame_info_label.setText(f"📐 画面尺寸: {w}x{h}")

        except Exception as e:
            print(f"显示错误: {e}")

    def update_status(self, message):
        """更新状态信息"""
        self.status_label.setText(f"📡 状态: {message}")

        # 同时更新 trigger 状态显示
        if self.orbbec_thread:
            state = self.orbbec_thread.trigger_state
            state_colors = {
                "idle": "#FFAA00",
                "waiting_qr": "#00AAFF",
                "confirmed": "#00FF88"
            }
            color = state_colors.get(state, "#FFFFFF")
            self.trigger_state_label.setStyleSheet(f"font-size: 14px; color: {color};")
            self.trigger_state_label.setText(f"🎯 Trigger 状态: {state}")

            if self.orbbec_thread.trigger_box:
                x1, y1, x2, y2 = self.orbbec_thread.trigger_box
                self.trigger_box_label.setText(f"📦 Trigger Box: ({x1},{y1}) -> ({x2},{y2})")

    def update_error(self, error):
        """更新错误信息"""
        self.status_label.setText(f"❌ 错误: {error[:50]}")
        print(f"[Orbbec Error] {error}")

    def update_fps_info(self):
        """更新 FPS 信息"""
        # 可以在这里添加 FPS 显示
        pass

    def on_start_trigger(self):
        """Start trigger 被触发"""
        print("\n" + "=" * 50)
        print("🎉 START TRIGGER 被触发!")
        print("   这将打开 QR 扫描弹窗")
        print("=" * 50)

        # 闪烁提示
        self.status_label.setText("🎉 START TRIGGER 触发成功!")
        self.status_label.setStyleSheet("font-size: 14px; color: #00FF88;")

        # 3秒后恢复
        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet("font-size: 14px; color: #FFAA00;"))

    def on_confirm_trigger(self):
        """Confirm trigger 被触发"""
        print("\n" + "=" * 50)
        print("🎉 CONFIRM TRIGGER 被触发!")
        print("   这将确认 QR 并启动 Pipeline")
        print("=" * 50)

        # 闪烁提示
        self.status_label.setText("🎉 CONFIRM TRIGGER 触发成功!")
        self.status_label.setStyleSheet("font-size: 14px; color: #00FF88;")

        # 3秒后恢复
        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet("font-size: 14px; color: #FFAA00;"))

    def closeEvent(self, event):
        """关闭窗口时清理"""
        self.stop_camera()
        event.accept()

    def keyPressEvent(self, event):
        """键盘快捷键控制 trigger box 位置"""
        if not self.orbbec_thread:
            print("[Debug] No Orbbec thread, cannot move trigger box")
            return

        # 检查是否有 trigger_position 属性
        if not hasattr(self.orbbec_thread, 'trigger_position'):
            print("[Debug] Orbbec thread has no trigger_position attribute")
            return

        step = 0.05  # 每次移动 5%

        if event.key() == Qt.Key_Left:
            new_x = max(0.05, self.orbbec_thread.trigger_position["relative_x"] - step)
            print(f"← Moving trigger box to X: {new_x}")
            self.orbbec_thread.set_trigger_box_position(
                new_x,
                self.orbbec_thread.trigger_position["relative_y"]
            )

        elif event.key() == Qt.Key_Right:
            new_x = min(0.95, self.orbbec_thread.trigger_position["relative_x"] + step)
            print(f"→ Moving trigger box to X: {new_x}")
            self.orbbec_thread.set_trigger_box_position(
                new_x,
                self.orbbec_thread.trigger_position["relative_y"]
            )

        elif event.key() == Qt.Key_Up:
            new_y = max(0.05, self.orbbec_thread.trigger_position["relative_y"] - step)
            print(f"↑ Moving trigger box to Y: {new_y}")
            self.orbbec_thread.set_trigger_box_position(
                self.orbbec_thread.trigger_position["relative_x"],
                new_y
            )

        elif event.key() == Qt.Key_Down:
            new_y = min(0.95, self.orbbec_thread.trigger_position["relative_y"] + step)
            print(f"↓ Moving trigger box to Y: {new_y}")
            self.orbbec_thread.set_trigger_box_position(
                self.orbbec_thread.trigger_position["relative_x"],
                new_y
            )

        elif event.key() == Qt.Key_Plus or event.key() == Qt.Key_Equal:
            new_size = min(200, self.orbbec_thread.trigger_position["size"] + 10)
            print(f"+ Increasing trigger box size to: {new_size}")
            self.orbbec_thread.set_trigger_box_position(
                self.orbbec_thread.trigger_position["relative_x"],
                self.orbbec_thread.trigger_position["relative_y"],
                new_size
            )

        elif event.key() == Qt.Key_Minus:
            new_size = max(60, self.orbbec_thread.trigger_position["size"] - 10)
            print(f"- Decreasing trigger box size to: {new_size}")
            self.orbbec_thread.set_trigger_box_position(
                self.orbbec_thread.trigger_position["relative_x"],
                self.orbbec_thread.trigger_position["relative_y"],
                new_size
            )


def main():
    app = QApplication(sys.argv)
    window = OrbbecDebugWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()