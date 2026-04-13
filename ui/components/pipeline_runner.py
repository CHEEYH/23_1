# ui/components/pipeline_runner.py

import json
import os
import socket
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from ui.components.mes_client import MESClient  # Add this import

from PySide6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, QPushButton,
    QFrame, QHBoxLayout, QGridLayout, QSplitter, QWidget, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from ui.components.heartbeat_manager import HeartbeatManager
from ui.components.dialogs import Calibration  # Import the Calibration class
from config_manager import config_manager
from camera.orbbec_camera_thread import OrbbecCameraThread

# Try to import camera module
CAMERA_AVAILABLE = False
try:
    from camera.camera import AutoCaptureFlow

    CAMERA_AVAILABLE = True
except ImportError:
    print("WARNING: Camera module not available")


# ── Tech HMI Style Helpers ────────────────────────────────────────────────
_DIALOG_BG   = "QDialog { background-color: #060C14; }"
_BODY_BG     = "background-color: #060C14;"

def _tech_dialog(dialog, color="#00AAFF", size=None):
    """Make dialog frameless with tech border and body bg."""
    dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
    if size: dialog.setFixedSize(*size)
    border_col = {"#00AAFF":"#00AAFF","#FFAA00":"#FFAA00","#00FF88":"#00FF88","#FF3344":"#FF3344"}.get(color,"#00AAFF")
    dialog.setStyleSheet(f"QDialog {{ background-color: #060C14; border: 1px solid {border_col}33; }}")

def _tech_header(text, step_badge=None, color="#00AAFF", dlg_id=""):
    """Return a styled QLabel header widget config dict."""
    badge = f"[{step_badge}]  " if step_badge else ""
    return badge + text  # caller creates QLabel with this text + stylesheet

def _ss_hdr(color="#00AAFF", bg="#050D18", size=22):
    bd_b = {"#00AAFF":"#00AAFF","#FFAA00":"#FFAA00","#00FF88":"#00FF88","#FF3344":"#FF3344"}.get(color,"#00AAFF")
    return (f"font-size:{size}px;font-weight:900;color:{color};"
            f"background-color:{bg};border-bottom:2px solid {bd_b};"
            f"border-left:4px solid {bd_b};padding:14px 18px;"
            f"letter-spacing:2px;font-family:Consolas;border-radius:0px;")

def _ss_panel_header(color="#00AAFF"):
    return (f"font-size:11px;font-weight:900;color:#AACCEE;"
            f"padding:8px 12px;background-color:#050D18;"
            f"border-bottom:1px solid #0E2A40;letter-spacing:3px;font-family:Consolas;")

def _ss_inforow(color="#00AAFF44"):
    return (f"background-color:#030810;border-left:3px solid {color};"
            f"padding:5px 10px;font-family:Consolas;font-size:13px;color:#AACCEE;")

def _ss_btn(color, bg, bd, size=17):
    hover = {"#00FF88":"#052A18","#FFAA00":"#221400","#FF3344":"#220810","#00AAFF":"#082030"}.get(color,"#0A1A0A")
    return (f"font-size:{size}px;font-weight:900;padding:12px 20px;"
            f"background-color:{bg};color:{color};"
            f"border:1px solid {bd};border-bottom:5px solid #020508;"
            f"border-left:3px solid {color};border-radius:0px;"
            f"font-family:Consolas;letter-spacing:2px;"
            f"QPushButton:hover{{background-color:{hover};color:#FFFFFF;border-color:{color};}}"
            f"QPushButton:pressed{{border-bottom:2px solid #020508;padding-top:3px;}}")

def _step_badge(step_num, total, color="#00AAFF"):
    return (f"font-size:11px;font-weight:900;color:{color};"
            f"background-color:#030810;border:1px solid {color}44;"
            f"padding:3px 12px;letter-spacing:3px;font-family:Consolas;")

def _dlg_id_style():
    return "font-size:9px;color:#0A2A3A;letter-spacing:3px;font-family:Consolas;background:transparent;"

def _ss_screw_cell():
    return ("background-color:#050D18;padding:10px 14px;"
            "border:1px solid #0E2A40;")

class PipelineRunner:
    _api_client = None
    _heartbeat_manager = None
    _heartbeat_reference_count = 0
    _calibration = None

    _screw_socket = None
    _screw_connected = False

    @staticmethod
    def get_orbbec_thread():
        try:
            from PySide6.QtWidgets import QApplication

            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'orbbec_thread') and widget.orbbec_thread:
                    return widget.orbbec_thread

                if hasattr(widget, 'main_page') and hasattr(widget.main_page, 'orbbec_thread'):
                    if widget.main_page.orbbec_thread:
                        return widget.main_page.orbbec_thread
        except Exception as e:
            print(f"[PipelineRunner] ⚠️ Cannot find Orbbec thread: {e}")

        return None

    @staticmethod
    def set_orbbec_trigger(thread, handler, state="idle"):
        if not thread:
            return

        try:
            thread.start_pipeline_signal.disconnect()
        except:
            pass

        try:
            thread.confirm_qr_signal.disconnect()
        except:
            pass

        thread.set_trigger_state(state)
        thread.trigger_was_used = False
        thread.trigger_enter_time = None
        thread.use_trigger_boxes = True

        if handler:
            thread.start_pipeline_signal.connect(handler)

    @staticmethod
    def init_api_client():
        try:
            base_url = config_manager.get_mes_api_url()
            timeout = config_manager.get_mes_api_timeout()
            print(f"🔌 Initializing MES API client with URL: {base_url}")
            from ui.components.mes_client import MESClient
            PipelineRunner._api_client = MESClient(base_url)
            PipelineRunner._api_client.timeout = timeout
            print(f"✅ MES API client initialized")
            try:
                if PipelineRunner._api_client.test_connection():
                    print(f"   Successfully connected to MES API")
                    inventory = PipelineRunner._api_client.get_all_inventory()
                    print(f"   Current inventory: {inventory}")
                else:
                    print(f"   ⚠️ Could not connect to MES API at {base_url}")
            except Exception as e:
                print(f"   ⚠️ Connection test failed: {e}")
            return PipelineRunner._api_client
        except Exception as e:
            print(f"❌ Failed to initialize API client: {e}")
            import traceback
            traceback.print_exc()
            PipelineRunner._api_client = None
            return None

    @staticmethod
    def _init_heartbeat_manager():
        if PipelineRunner._heartbeat_manager is None:
            PipelineRunner._heartbeat_manager = HeartbeatManager()
        PipelineRunner._heartbeat_reference_count += 1
        PipelineRunner._ensure_heartbeat_connected()

    @staticmethod
    def _ensure_heartbeat_connected():
        if PipelineRunner._heartbeat_manager and not PipelineRunner._heartbeat_manager.is_connected():
            server_ip = PipelineRunner._get_server_address()
            server_port = PipelineRunner._get_server_port()
            success, message = PipelineRunner._heartbeat_manager.connect(server_ip, server_port)
            if success:
                print(f"✅ Heartbeat started (interval: 5s) for PipelineRunner")
            else:
                print(f"❌ Heartbeat failed: {message}")

    @staticmethod
    def _get_server_address():
        try:
            if hasattr(config_manager, 'get_tcp_server'):
                return config_manager.get_tcp_server()
        except:
            pass
        return "127.0.0.1"

    @staticmethod
    def _get_server_port():
        try:
            if hasattr(config_manager, 'get_tcp_port'):
                return config_manager.get_tcp_port()
        except:
            pass
        return 8888

    @staticmethod
    def _load_calibration(recipe_name: str = None):
        if PipelineRunner._calibration is None:
            PipelineRunner._calibration = Calibration()
            calibration_path = "C:\\Users\\PC_AI_DS\\Pictures\\LaserCalibration\\calibration.json"
            if os.path.exists(calibration_path):
                success, message = PipelineRunner._calibration.load_calibration(calibration_path)
                if success:
                    print(f"✅ PipelineRunner loaded calibration from: {calibration_path}")
                else:
                    print(f"⚠️ PipelineRunner failed to load calibration: {message}")
                    PipelineRunner._calibration = Calibration()
            else:
                print(f"⚠️ Calibration file not found at: {calibration_path}")
                PipelineRunner._calibration = Calibration()
        return PipelineRunner._calibration

    @staticmethod
    def verify_calibration():
        calibration = PipelineRunner._load_calibration()
        if calibration and calibration.is_calibrated:
            print("\n" + "=" * 50)
            print("✅ CALIBRATION VERIFICATION")
            print("=" * 50)
            return True
        else:
            print("\n" + "=" * 50)
            print("❌ CALIBRATION NOT LOADED")
            print("=" * 50)
            return False

    @staticmethod
    def _convert_to_world_coordinates(calibration, pixel_corners):
        world_corners = []
        if not calibration or not calibration.is_calibrated:
            return pixel_corners
        for corner in pixel_corners:
            try:
                world_point = calibration.pixel_to_world(corner)
                if world_point:
                    world_corners.append(world_point)
                else:
                    world_corners.append(corner)
            except Exception as e:
                world_corners.append(corner)
        return world_corners

    @staticmethod
    def send_coordinates_to_server(predictions, calibration=None):
        if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
            PipelineRunner._ensure_heartbeat_connected()
            if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
                return False
        try:
            if not predictions:
                return False
            best_prediction = max(predictions, key=lambda p: p.get('confidence', 0))
            bbox = best_prediction.get('bbox', [0, 0, 0, 0])
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox[:4]
                if calibration and calibration.is_calibrated:
                    pixel_corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                    world_corners = PipelineRunner._convert_to_world_coordinates(calibration, pixel_corners)
                    coord_line = (f"{world_corners[0][0]:.2f}_{world_corners[0][1]:.2f},"
                                  f"{world_corners[1][0]:.2f}_{world_corners[1][1]:.2f},"
                                  f"{world_corners[2][0]:.2f}_{world_corners[2][1]:.2f},"
                                  f"{world_corners[3][0]:.2f}_{world_corners[3][1]:.2f}")
                else:
                    coord_line = (f"{x1:.2f}_{y1:.2f},{x2:.2f}_{y1:.2f},{x2:.2f}_{y2:.2f},{x1:.2f}_{y2:.2f}")
                success = PipelineRunner._heartbeat_manager.send_data(coord_line + "\n")
                return success
            return False
        except Exception as e:
            print(f"❌ Error sending coordinates: {e}")
            return False

    @staticmethod
    def _send_latest_coordinates_from_folder(recipe_name: str, folder_name: str, block_id: str) -> tuple:
        try:
            recipe_folder = config_manager.get_recipe_folder(recipe_name)
            if not recipe_folder:
                return False, ""
            target_folder = os.path.join(recipe_folder, folder_name, f"Block_{block_id}")
            if not os.path.exists(target_folder):
                return False, ""
            import glob
            json_files = glob.glob(os.path.join(target_folder, "*.json"))
            if not json_files:
                return False, ""
            latest_json = max(json_files, key=os.path.getmtime)
            with open(latest_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            coord_parts = []
            if isinstance(data, list):
                for point in data:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        coord_parts.append(f"{float(point[0]):.2f}_{float(point[1]):.2f}")
                    elif isinstance(point, dict):
                        x = point.get("x")
                        y = point.get("y")
                        if x is not None and y is not None:
                            coord_parts.append(f"{float(x):.2f}_{float(y):.2f}")
            coord_string = ",".join(coord_parts)
            if not coord_string:
                return False, ""
            if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
                PipelineRunner._ensure_heartbeat_connected()
            if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
                return False, coord_string
            success = PipelineRunner._heartbeat_manager.send_data(coord_string + "\n")
            return success, coord_string
        except Exception as e:
            print(f"❌ Error sending coordinates: {e}")
            return False, ""

    @staticmethod
    def _show_video_dialog(video_path: str, parent_widget=None, title: str = "Video") -> bool:
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QWidget, QHBoxLayout, QSplitter
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget

            dialog = QDialog(parent_widget)
            dialog.setWindowTitle(title)
            dialog.showFullScreen()
            dialog.setStyleSheet("QDialog { background-color: #030810; }")

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(0, 0, 8, 8)
            layout.setSpacing(8)

            # Get Orbbec thread and take over trigger for THIS dialog
            orbbec_thread = PipelineRunner.get_orbbec_thread()
            _video_hand_triggered = {"done": False}

            # Header
            vid_hdr = QWidget()
            vid_hdr.setFixedHeight(56)
            vid_hdr.setStyleSheet("background:#050D18;border-bottom:2px solid #FFAA00;")
            vid_hdr_row = QHBoxLayout(vid_hdr)
            vid_hdr_row.setContentsMargins(14, 0, 14, 0)
            vid_hdr_row.setSpacing(10)

            # vid_badge = QLabel("VIDEO")
            # vid_badge.setStyleSheet(
            #     "font-size:11px;font-weight:900;color:#FFAA00;"
            #     "background:#030810;border:1px solid #FFAA0044;"
            #     "padding:3px 10px;letter-spacing:3px;font-family:Consolas;"
            # )

            vid_title = QLabel(title.upper())
            vid_title.setStyleSheet(
                "font-size:26px;font-weight:900;color:#FFFFFF;"
                "letter-spacing:2px;font-family:Consolas;background:transparent;"
            )

            # vid_hdr_row.addWidget(vid_badge)
            vid_hdr_row.addWidget(vid_title)
            vid_hdr_row.addStretch()
            layout.addWidget(vid_hdr)

            # If video file not found
            if not os.path.exists(video_path):
                content_split = QSplitter(Qt.Horizontal)
                content_split.setStyleSheet("""
                    QSplitter::handle {
                        background-color: #0E2A40;
                        width: 2px;
                    }
                """)

                left_panel = QWidget()
                left_layout = QVBoxLayout(left_panel)
                left_layout.setContentsMargins(8, 8, 8, 8)

                error_label = QLabel(f"❌ Video not found:\n{video_path}")
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("""
                    QLabel {
                        font-size: 18px;
                        color: #FF3344;
                        background-color: #1A0508;
                        border: 1px solid #661020;
                        border-left: 3px solid #FF3344;
                        padding: 20px;
                        border-radius: 2px;
                    }
                """)
                left_layout.addWidget(error_label)

                right_panel = QWidget()
                right_panel.setStyleSheet("background-color: #030810; border: 1px solid #0E2A40;")

                content_split.addWidget(left_panel)
                content_split.addWidget(right_panel)
                content_split.setSizes([1100, 500])

                layout.addWidget(content_split, stretch=1)

                close_btn = QPushButton("✓  Continue")
                close_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 17px; font-weight: 800;
                        padding: 16px 32px;
                        background-color: #031A10; color: #00FF88;
                        border: 1px solid #0A5030; border-bottom: 5px solid #051008;
                        border-left: 3px solid #00FF88; border-radius: 2px;
                        min-width: 240px; font-family: Consolas; letter-spacing: 1px;
                    }
                    QPushButton:hover { background-color: #052A18; color: #FFFFFF; border-color: #00FF88; }
                    QPushButton:pressed { border-bottom: 2px solid #051008; padding-top: 3px; }
                """)

                def close_missing_video():
                    if _video_hand_triggered["done"]:
                        return
                    _video_hand_triggered["done"] = True
                    dialog.accept()

                def on_video_hand_trigger_missing():
                    try:
                        if _video_hand_triggered["done"]:
                            return
                        print("[SCREW VIDEO] Hand detected in trigger zone (missing video page)")
                        close_missing_video()
                    except Exception as e:
                        print(f"[SCREW VIDEO] Trigger error (missing video): {e}")

                close_btn.clicked.connect(close_missing_video)
                layout.addWidget(close_btn, alignment=Qt.AlignCenter)

                PipelineRunner.set_orbbec_trigger(orbbec_thread, on_video_hand_trigger_missing, state="idle")

                def restore_trigger_missing(_=None):
                    try:
                        PipelineRunner.set_orbbec_trigger(orbbec_thread, None, state="idle")
                    except Exception as e:
                        print(f"[SCREW VIDEO] Restore trigger error (missing video): {e}")

                dialog.finished.connect(restore_trigger_missing)

                return dialog.exec() == QDialog.Accepted

            # Main split area: LEFT = video, RIGHT = blank
            content_split = QSplitter(Qt.Horizontal)
            content_split.setStyleSheet("""
                QSplitter::handle {
                    background-color: #0E2A40;
                    width: 2px;
                }
            """)

            # Left panel - video
            left_panel = QWidget()
            left_panel.setStyleSheet("background-color: #030810;")
            left_layout = QVBoxLayout(left_panel)
            left_layout.setContentsMargins(8, 8, 8, 8)
            left_layout.setSpacing(0)

            video_widget = QVideoWidget()
            video_widget.setStyleSheet("background-color: #000000; border: 1px solid #0E2A40;")
            left_layout.addWidget(video_widget)

            # Right panel - blank
            right_panel = QWidget()
            right_panel.setStyleSheet("background-color: #030810; border: 1px solid #0E2A40;")

            content_split.addWidget(left_panel)
            content_split.addWidget(right_panel)
            content_split.setSizes([1100, 500])

            layout.addWidget(content_split, stretch=1)

            # Bottom button
            close_btn = QPushButton("✓ Continue")
            close_btn.setStyleSheet("""
                QPushButton {
                    font-size: 17px; font-weight: 800;
                    padding: 16px 32px;
                    background-color: #031A10; color: #00FF88;
                    border: 1px solid #0A5030; border-bottom: 5px solid #051008;
                    border-left: 3px solid #00FF88; border-radius: 2px;
                    min-width: 240px; font-family: Consolas; letter-spacing: 1px;
                }
                QPushButton:hover { background-color: #052A18; color: #FFFFFF; border-color: #00FF88; }
                QPushButton:pressed { border-bottom: 2px solid #051008; padding-top: 3px; }
            """)
            layout.addWidget(close_btn, alignment=Qt.AlignCenter)

            player = QMediaPlayer(dialog)
            audio = QAudioOutput(dialog)
            player.setAudioOutput(audio)
            player.setVideoOutput(video_widget)
            player.setSource(QUrl.fromLocalFile(video_path))
            audio.setVolume(0.0)

            def loop_video(status):
                from PySide6.QtMultimedia import QMediaPlayer
                if status == QMediaPlayer.EndOfMedia:
                    player.stop()
                    player.setPosition(0)
                    player.play()

            player.mediaStatusChanged.connect(loop_video)
            dialog._video_player = player
            dialog._video_audio = audio
            player.play()

            def close_video():
                if _video_hand_triggered["done"]:
                    return
                _video_hand_triggered["done"] = True
                try:
                    player.stop()
                except Exception:
                    pass
                PipelineRunner.send_screw_stop_to_server()
                dialog.accept()

            def on_video_hand_trigger():
                try:
                    if _video_hand_triggered["done"]:
                        return
                    print("[SCREW VIDEO] Hand detected in trigger zone!")
                    close_video()
                except Exception as e:
                    print(f"[SCREW VIDEO] Trigger error: {e}")

            close_btn.clicked.connect(close_video)

            def restore_trigger(_=None):
                try:
                    player.stop()
                except Exception:
                    pass

                try:
                    PipelineRunner.set_orbbec_trigger(orbbec_thread, None, state="idle")
                    print("[SCREW VIDEO] Trigger restored/cleared")
                except Exception as e:
                    print(f"[SCREW VIDEO] Restore trigger error: {e}")

            PipelineRunner.set_orbbec_trigger(orbbec_thread, on_video_hand_trigger, state="idle")
            dialog.finished.connect(restore_trigger)

            return dialog.exec() == QDialog.Accepted

        except Exception as e:
            print(f"❌ Error showing video dialog: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(parent_widget, "Video Error", f"Cannot play video:\n{str(e)}")
            return False

    @staticmethod
    def continue_skipped_steps(recipe_name: str, job_data: Dict, parent_widget, pending_callback=None) -> bool:
        if PipelineRunner._api_client is None:
            PipelineRunner.init_api_client()
        PipelineRunner._init_heartbeat_manager()
        calibration = PipelineRunner._load_calibration(recipe_name)
        print(f"🔄 Continuing job: {job_data.get('job_id', 'Unknown')}")
        try:
            config_manager.set_current_recipe(recipe_name)
            flow_data = PipelineRunner.get_pipeline_from_file(recipe_name)
            if not flow_data:
                QMessageBox.warning(parent_widget, "⚠️ No Pipeline Found", f"Recipe '{recipe_name}' has no saved pipeline")
                return False
            execution_order = PipelineRunner.get_execution_order(flow_data)
            if not execution_order:
                QMessageBox.warning(parent_widget, "⚠️ Empty Pipeline", "Pipeline has no executable blocks")
                return False
            skipped_steps_info = [s for s in job_data.get('skipped_steps', []) if isinstance(s, dict)]
            if not skipped_steps_info:
                QMessageBox.information(parent_widget, "No Skipped Steps", "This job has no skipped steps to continue.")
                return True
            updated_job = job_data.copy()
            updated_job['continue_time'] = datetime.now().isoformat()
            completed_steps = job_data.get('completed_steps', []).copy()
            remaining_skipped_steps = []
            steps_completed_now = []
            total_skipped = len(skipped_steps_info)
            for idx, skip_info in enumerate(skipped_steps_info):
                step_num = skip_info.get('step')
                if step_num > len(execution_order):
                    continue
                block_data = execution_order[step_num - 1]
                block_name = block_data.get('name', 'Unknown')
                if block_name == "Assembly":
                    result, info = PipelineRunner._execute_assembly_block_operator(block_data, step_num, len(execution_order), parent_widget)
                    if result == "completed":
                        if step_num not in completed_steps:
                            completed_steps.append(step_num)
                        steps_completed_now.append(step_num)
                    elif result == "skipped":
                        remaining_skipped_steps.append(skip_info)
                        tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"
                        QMessageBox.information(parent_widget, "⏭ Step Still Skipped", f"Step {step_num} still cannot be completed.\nMissing parts: {', '.join(info.get('missing_parts', []))}\n📡 TCP: {tcp_status}")
                    elif result == "waiting":
                        if 'waiting_steps' not in updated_job:
                            updated_job['waiting_steps'] = []
                        updated_job['waiting_steps'].append({'step': step_num, 'waiting_for': info.get('missing_parts', [])})
                        break
                    else:
                        return False
                elif block_name == "Screw":
                    success = PipelineRunner._execute_screw_block(block_data, step_num, len(execution_order), parent_widget)
                    if success:
                        if step_num not in completed_steps:
                            completed_steps.append(step_num)
                        steps_completed_now.append(step_num)
                    else:
                        return False
                elif block_name == "Camera":
                    try:
                        from ui.components.block_functions import open_realsense_camera
                        open_realsense_camera()
                        if step_num not in completed_steps:
                            completed_steps.append(step_num)
                        steps_completed_now.append(step_num)
                    except Exception as e:
                        reply = QMessageBox.question(parent_widget, "Camera Error", f"Cannot open camera: {str(e)}\n\nSkip this step?", QMessageBox.Yes | QMessageBox.No)
                        if reply == QMessageBox.Yes:
                            remaining_skipped_steps.append(skip_info)
                        else:
                            return False
            updated_job['completed_steps'] = completed_steps
            updated_job['skipped_steps'] = remaining_skipped_steps
            updated_job['end_time'] = datetime.now().isoformat()
            total_steps = updated_job.get('total_steps', len(execution_order))
            if len(completed_steps) >= total_steps:
                updated_job['status'] = 'complete'
            elif remaining_skipped_steps:
                updated_job['status'] = 'partial'
            elif updated_job.get('waiting_steps'):
                updated_job['status'] = 'waiting'
            else:
                updated_job['status'] = 'complete'
            if pending_callback:
                PipelineRunner.save_pending_job(recipe_name, updated_job)
            if updated_job['status'] == 'complete':
                PipelineRunner._notify_main_page_refresh_mes(parent_widget)
            return updated_job['status'] == 'complete'
        except Exception as e:
            print(f"❌ Error in continue_skipped_steps: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            PipelineRunner.cleanup()

    @staticmethod
    def get_pipeline_from_file(recipe_name: str) -> Optional[Dict]:
        if not recipe_name or recipe_name in ("-- Select Recipe --", "-- Select Production Task --"):
            return None
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return None
        flow_file = os.path.join(recipe_folder, "flows", "pipeline_flow.json")
        if not os.path.exists(flow_file):
            return None
        try:
            with open(flow_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"ERROR: Failed to load pipeline: {str(e)}")
            return None

    @staticmethod
    def get_execution_order(flow_data: Dict) -> List[Dict]:
        if not flow_data or 'blocks' not in flow_data:
            return []
        blocks = flow_data['blocks']
        connections = flow_data.get('connections', [])
        if not blocks:
            return []
        incoming = {i: [] for i in range(len(blocks))}
        outgoing = {i: [] for i in range(len(blocks))}
        for conn in connections:
            from_idx = conn.get('from_block')
            to_idx = conn.get('to_block')
            if from_idx is not None and to_idx is not None:
                if from_idx in outgoing and to_idx in incoming:
                    outgoing[from_idx].append(to_idx)
                    incoming[to_idx].append(from_idx)
        start_blocks = [i for i in range(len(blocks)) if len(incoming[i]) == 0]
        execution_order = []
        visited = set()
        def dfs(idx):
            if idx in visited:
                return
            visited.add(idx)
            execution_order.append(blocks[idx])
            for next_idx in outgoing[idx]:
                dfs(next_idx)
        for start_idx in start_blocks:
            dfs(start_idx)
        for i in range(len(blocks)):
            if i not in visited:
                execution_order.append(blocks[i])
        if not connections and len(execution_order) > 1:
            execution_order.sort(key=lambda b: b.get('y', 0))
        return execution_order

    @staticmethod
    def validate_pipeline(flow_data: Dict, recipe_name: str) -> Tuple[bool, str]:
        if not flow_data:
            return False, "No pipeline data found"
        if not flow_data.get('blocks'):
            return False, "Pipeline has no blocks"
        blocks = flow_data.get('blocks', [])
        has_end_block = any(block.get('name') == 'End' for block in blocks)
        if not has_end_block:
            return True, "Pipeline has no End block (will run all blocks)"
        return True, "Pipeline validated successfully"

    @staticmethod
    def get_pipeline_summary(recipe_name: str) -> Dict:
        flow_data = PipelineRunner.get_pipeline_from_file(recipe_name)
        if not flow_data:
            return {"error": "No pipeline found"}
        blocks = flow_data.get('blocks', [])
        connections = flow_data.get('connections', [])
        block_counts = {}
        for block in blocks:
            name = block.get('name', 'Unknown')
            block_counts[name] = block_counts.get(name, 0) + 1
        execution_order = PipelineRunner.get_execution_order(flow_data)
        return {
            "recipe": recipe_name,
            "total_blocks": len(blocks),
            "total_connections": len(connections),
            "block_counts": block_counts,
            "execution_order": [b.get('name') for b in execution_order],
            "has_end_block": any(b.get('name') == 'End' for b in blocks),
            "last_saved": flow_data.get('saved_at', 'Unknown')
        }

    @staticmethod
    def run_pipeline(recipe_name, parent_widget=None, execution_order=None):
        if execution_order is None:
            if hasattr(parent_widget, 'get_execution_order'):
                execution_order = parent_widget.get_execution_order()
            else:
                return False
        if not execution_order:
            return False
        for i, block in enumerate(execution_order):
            step_number = i + 1
            total_blocks = len(execution_order)
            if block.name == "Assembly":
                if hasattr(parent_widget, 'execute_assembly_block'):
                    parent_widget.execute_assembly_block(block, step_number, total_blocks)
            elif block.name == "Screw":
                if hasattr(parent_widget, 'execute_screw_block'):
                    parent_widget.execute_screw_block(block, step_number, total_blocks)
            elif block.name in ("Camera", "End"):
                if block.action:
                    block.action()
        return True

    @staticmethod
    def execute_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        block_name = block_data.get('name', 'Unknown')
        if block_name == "Assembly":
            return PipelineRunner._execute_assembly_block(block_data, step_number, total_steps, parent_widget)
        elif block_name == "Screw":
            return PipelineRunner._execute_screw_block(block_data, step_number, total_steps, parent_widget)
        else:
            return PipelineRunner._execute_generic_block(block_data, step_number, total_steps, parent_widget)

    @staticmethod
    def run_pipeline_operator_mode(recipe_name: str, parent_widget, pending_callback=None) -> bool:
        print(f"DEBUG: Starting operator pipeline for recipe: {recipe_name}")
        if PipelineRunner._api_client is None:
            PipelineRunner.init_api_client()
        job_id = None
        mes_job_details = {}
        if PipelineRunner._api_client:
            try:
                mes_job_details = PipelineRunner._api_client.get_job_details()
                if mes_job_details:
                    job_id = mes_job_details.get('workOrder')
            except Exception as e:
                print(f"❌ Error getting job details from MES: {e}")
                job_id = None
                mes_job_details = {}
        if not job_id:
            job_id = f"JOB_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        PipelineRunner._init_heartbeat_manager()
        calibration = PipelineRunner._load_calibration(recipe_name)
        try:
            config_manager.set_current_recipe(recipe_name)
            flow_data = PipelineRunner.get_pipeline_from_file(recipe_name)
            if not flow_data:
                QMessageBox.warning(parent_widget, "⚠️ No Pipeline Found", f"Recipe '{recipe_name}' has no saved pipeline")
                return False
            execution_order = PipelineRunner.get_execution_order(flow_data)
            if not execution_order:
                QMessageBox.warning(parent_widget, "⚠️ Empty Pipeline", "Pipeline has no executable blocks")
                return False
            job_data = {
                'job_id': job_id, 'recipe': recipe_name,
                'start_time': datetime.now().isoformat(),
                'completed_steps': [], 'skipped_steps': [], 'waiting_steps': [],
                'total_steps': len(execution_order),
                'tcp_connected': PipelineRunner._heartbeat_manager.is_connected() if PipelineRunner._heartbeat_manager else False,
                'calibration_loaded': calibration.is_calibrated if calibration else False,
                'mes_job_id': job_id if job_id and not job_id.startswith('JOB_') else None,
                'mes_job_details': mes_job_details,
                'product_code': mes_job_details.get('product_code') if mes_job_details else None,
                'work_order': mes_job_details.get('workOrder') if mes_job_details else None
            }
            for i, block_data in enumerate(execution_order):
                step_num = i + 1
                block_name = block_data.get('name', 'Unknown')
                if block_name == "Assembly":
                    result, info = PipelineRunner._execute_assembly_block_operator(block_data, step_num, job_data['total_steps'], parent_widget)
                    if result == "completed":
                        job_data['completed_steps'].append(step_num)
                    elif result == "skipped":
                        job_data['skipped_steps'].append({'step': step_num, 'reason': info.get('reason', 'Missing parts'), 'missing_parts': info.get('missing_parts', [])})
                    elif result == "waiting":
                        job_data['waiting_steps'].append({'step': step_num, 'waiting_for': info.get('missing_parts', [])})
                        break
                    else:
                        return False
                elif block_name == "Screw":
                    success = PipelineRunner._execute_screw_block(block_data, step_num, job_data['total_steps'], parent_widget)
                    if success:
                        job_data['completed_steps'].append(step_num)
                    else:
                        return False
                elif block_name == "Camera":
                    try:
                        from ui.components.block_functions import open_realsense_camera
                        open_realsense_camera()
                        job_data['completed_steps'].append(step_num)
                    except Exception as e:
                        reply = QMessageBox.question(parent_widget, "Camera Error", f"Cannot open camera: {str(e)}\n\nSkip this step?", QMessageBox.Yes | QMessageBox.No)
                        if reply == QMessageBox.Yes:
                            job_data['skipped_steps'].append({'step': step_num, 'reason': 'camera_error'})
                        else:
                            return False
                elif block_name == "End":
                    job_data['completed_steps'].append(step_num)
            job_data['end_time'] = datetime.now().isoformat()
            if job_data['skipped_steps'] and job_data['completed_steps']:
                job_data['status'] = 'partial'
            elif not job_data['skipped_steps'] and job_data['completed_steps']:
                job_data['status'] = 'complete'
            elif job_data['waiting_steps']:
                job_data['status'] = 'waiting'
            else:
                job_data['status'] = 'incomplete'
            if job_data.get('job_id') and not str(job_data['job_id']).startswith('JOB_'):
                try:
                    from complete_mes import stop_latest_workorder
                    result = stop_latest_workorder(job_data['job_id'], recipe_name)
                    if result:
                        PipelineRunner._notify_main_page_refresh_mes(parent_widget)
                except Exception as e:
                    print(f"❌ Failed to mark job complete in MES: {e}")
            if pending_callback and (job_data['skipped_steps'] or job_data['waiting_steps']):
                pending_callback(job_data)
            tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"
            if job_data['skipped_steps']:
                skip_summary = "\n".join([f"  Step {s['step']}: {s['reason']}" for s in job_data['skipped_steps']])
                QMessageBox.information(parent_widget, "✅ Assembly Complete",
                    f"Process execution completed!\nJob ID: {job_data['job_id']}\nCompleted: {len(job_data['completed_steps'])}\nSkipped: {len(job_data['skipped_steps'])}\n\n{skip_summary}")
            elif job_data['waiting_steps']:
                QMessageBox.information(parent_widget, "⏳ Waiting for Parts",
                    f"Process paused.\nJob ID: {job_data['job_id']}\nCompleted: {len(job_data['completed_steps'])}/{job_data['total_steps']}\n📡 TCP: {tcp_status}")
            else:
                # ── TECH SUCCESS DIALOG ────────────────────────────────────
                success_dialog = QDialog(parent_widget)
                success_dialog.setWindowTitle("Assembly Complete")
                success_dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
                success_dialog.setFixedSize(600, 460)
                success_dialog.setStyleSheet("QDialog { background-color: #030810; border: 1px solid #00FF8844; }")
                suc_layout = QVBoxLayout(success_dialog)
                suc_layout.setContentsMargins(0, 0, 0, 0)
                suc_layout.setSpacing(0)

                orbbec_thread = PipelineRunner.get_orbbec_thread()
                complete_trigger_done = {"done": False}

                # Header bar
                suc_hdr = QWidget()
                suc_hdr.setFixedHeight(70)
                suc_hdr.setStyleSheet("background:#031A10;")
                suc_hdr_row = QHBoxLayout(suc_hdr)
                suc_hdr_row.setContentsMargins(14, 0, 14, 0)
                suc_hdr_row.setSpacing(12)

                suc_badge = QLabel("COMPLETE")
                suc_badge.setStyleSheet(
                    "font-size:14px;font-weight:900;color:#00FF88;background:#021008;"
                    "border:1px solid #00FF8844;padding:4px 14px;letter-spacing:3px;font-family:Consolas;"
                )

                suc_title = QLabel("ASSEMBLY COMPLETE")
                suc_title.setStyleSheet(
                    "font-size:22px;font-weight:900;color:#00FF88;"
                    "letter-spacing:3px;font-family:Consolas;background:transparent;"
                )

                suc_badge.hide()
                suc_hdr_row.addWidget(suc_title)
                suc_hdr_row.addStretch()
                suc_layout.addWidget(suc_hdr)

                suc_sep = QWidget()
                suc_sep.setFixedHeight(2)
                suc_sep.setStyleSheet("background:#00FF88;")
                suc_layout.addWidget(suc_sep)

                tick_label = QLabel("✓")
                tick_label.setAlignment(Qt.AlignCenter)
                tick_label.setFixedHeight(150)
                tick_label.setStyleSheet("font-size:110px;color:#00FF88;background:#031A10;font-weight:900;")
                suc_layout.addWidget(tick_label)

                tick_div = QWidget()
                tick_div.setFixedHeight(1)
                tick_div.setStyleSheet("background:#0E2A40;")
                suc_layout.addWidget(tick_div)

                job_id_str = job_data.get("job_id", "-")
                steps_str = f"{len(job_data['completed_steps'])}/{job_data['total_steps']}"
                tcp_str = "CONNECTED" if (
                            PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected()) else "DISCONNECTED"
                tcp_color = "#00FF88" if "CONNECTED" in tcp_str else "#FF3344"

                for sk, sv, sc in [
                    ("STEPS", steps_str + " COMPLETED", "#00FF88"),
                    ("JOB ID", job_id_str, "#AACCEE"),
                    ("TCP", tcp_str, tcp_color)
                ]:
                    rw = QWidget()
                    rw.setFixedHeight(64)
                    rw.setStyleSheet(
                        "background:#030810;border-bottom:1px solid #0E2A40;border-left:3px solid #00FF8844;")
                    rwl = QHBoxLayout(rw)
                    rwl.setContentsMargins(16, 0, 16, 0)
                    rwl.setSpacing(16)

                    lk = QLabel(sk)
                    lk.setStyleSheet(
                        "font-size:20px;color:#1A5A2A;letter-spacing:2px;"
                        "font-family:Consolas;background:transparent;min-width:120px;"
                    )

                    lv = QLabel(sv)
                    lv.setStyleSheet(
                        f"font-size:16px;color:{sc};font-weight:900;font-family:Consolas;background:transparent;"
                    )

                    rwl.addWidget(lk)
                    rwl.addWidget(lv)
                    rwl.addStretch()
                    suc_layout.addWidget(rw)

                ok_btn = QPushButton("▶  CONTINUE")
                ok_btn.setFixedHeight(70)
                ok_btn.setStyleSheet(
                    "font-size:20px;font-weight:900;background:#031A10;color:#00FF88;"
                    "border:none;border-top:2px solid #00FF88;font-family:Consolas;letter-spacing:3px;"
                    "QPushButton:hover{background:#052A18;color:#FFFFFF;}"
                )

                def on_complete_continue():
                    if complete_trigger_done["done"]:
                        return
                    complete_trigger_done["done"] = True
                    success_dialog.accept()

                def on_complete_hand_trigger():
                    try:
                        if complete_trigger_done["done"]:
                            return
                        print("[ASSEMBLY COMPLETE] Hand detected in trigger zone!")
                        on_complete_continue()
                    except Exception as e:
                        print(f"[ASSEMBLY COMPLETE] Trigger error: {e}")

                def _cleanup_complete_dialog(*_):
                    try:
                        PipelineRunner.set_orbbec_trigger(orbbec_thread, None, state="idle")
                        print("[ASSEMBLY COMPLETE] Trigger cleared")
                    except Exception as e:
                        print(f"[ASSEMBLY COMPLETE] Cleanup trigger error: {e}")

                ok_btn.clicked.connect(on_complete_continue)
                suc_layout.addWidget(ok_btn)

                PipelineRunner.set_orbbec_trigger(orbbec_thread, on_complete_hand_trigger, state="idle")
                success_dialog.finished.connect(_cleanup_complete_dialog)

                success_dialog.exec()

            return True

        except Exception as e:
            print(f"❌ Error in pipeline execution: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
                PipelineRunner.cleanup(force_disconnect=True)


    @staticmethod
    def _extract_part_from_product_name(product_name: str) -> str:
        if not product_name:
            return ""
        product_name = product_name.strip()
        import re
        match = re.match(r'^\d+_(.+)$', product_name)
        if match:
            return match.group(1).strip()
        parts = product_name.split('_')
        if len(parts) >= 2:
            last_part = parts[-1].strip()
            if last_part:
                return last_part
        match = re.search(r'\b([A-F])\b$', product_name)
        if match:
            return match.group(1)
        if len(product_name) == 1 and product_name.isalpha():
            return product_name
        words = product_name.split()
        for word in words:
            if len(word) == 1 and word.isalpha() and word in ['A', 'B', 'C', 'D', 'E', 'F']:
                return word
        match = re.search(r'\b([A-Z][0-9]+)\b$', product_name)
        if match:
            return match.group(1)
        return product_name

    @staticmethod
    def _execute_assembly_block_operator(block_data: Dict, step_num: int, total_steps: int, parent_widget) -> Tuple[str, Dict]:
        assembly_data = block_data.get('assembly_data', {})
        selections = {}
        total_assembly_steps = 0
        if 'selections' in assembly_data and isinstance(assembly_data['selections'], dict):
            selections_data = assembly_data['selections']
            step_keys = [k for k in selections_data.keys() if k.isdigit()]
            if step_keys:
                selections = selections_data
                total_assembly_steps = len(step_keys)
            else:
                if 'selections' in selections_data:
                    selections = selections_data.get('selections', {})
                    total_assembly_steps = selections_data.get('total_steps', 0)
        if not selections:
            step_keys = [k for k in assembly_data.keys() if k.isdigit()]
            if step_keys:
                selections = {k: assembly_data[k] for k in step_keys}
                total_assembly_steps = len(step_keys)
        if total_assembly_steps == 0:
            total_assembly_steps = assembly_data.get('total_steps', 0)
        if total_assembly_steps == 0 or not selections:
            QMessageBox.warning(parent_widget, "⚠️ No Configuration", "Assembly Block has no steps configured!")
            return "cancelled", {}
        if PipelineRunner._api_client is None:
            PipelineRunner.init_api_client()
        skipped_steps = []
        missing_parts_list = []
        for assembly_step in range(1, total_assembly_steps + 1):
            step_key = str(assembly_step)
            if step_key not in selections:
                continue
            selection = dict(selections[step_key])
            selection['uploaded_video_path'] = assembly_data.get('uploaded_video_path', '')
            product_data = selection.get('product_data', {})
            product_name = product_data.get('name', f'Step {assembly_step}')
            part_needed = PipelineRunner._extract_part_from_product_name(product_name)
            try:
                if PipelineRunner._api_client:
                    current_stock = PipelineRunner._api_client.get_inventory(part_needed)
                else:
                    current_stock = 999
            except Exception as e:
                current_stock = 999
            if current_stock <= 0:
                reply = PipelineRunner._ask_operator_about_missing_part(assembly_step, product_name, part_needed, current_stock, parent_widget)
                if reply == "skip":
                    skipped_steps.append(assembly_step)
                    if part_needed:
                        missing_parts_list.append(part_needed)
                    continue
                elif reply == "wait":
                    return "waiting", {'missing_parts': missing_parts_list + ([part_needed] if part_needed else []), 'step': assembly_step}
                elif reply == "cancel":
                    return "cancelled", {}
            step_success = PipelineRunner._execute_assembly_step_like_dialog(assembly_step, total_assembly_steps, step_num, total_steps, selection, parent_widget)
            if step_success:
                try:
                    PipelineRunner._api_client.deduct_inventory(part_needed, 1)
                except Exception as e:
                    print(f"❌ Error deducting inventory: {e}")
            else:
                return "cancelled", {}
        if skipped_steps:
            return "skipped", {'reason': 'Missing parts', 'missing_parts': list(set(missing_parts_list)), 'skipped_steps': skipped_steps}
        return "completed", {}

    @staticmethod
    def _ask_operator_about_missing_part(step_num: int, product_name: str, part_needed: str, current_stock: int, parent_widget) -> str:
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_num} - Missing Part")
        dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dialog.setFixedSize(560, 440)
        dialog.setStyleSheet("QDialog { background-color: #030810; border: 1px solid #FFAA0066; }")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        miss_hdr = QWidget()
        miss_hdr.setFixedHeight(56)
        miss_hdr.setStyleSheet("background:#050D18;border-bottom:2px solid #FFAA00;")
        miss_hdr_row = QHBoxLayout(miss_hdr); miss_hdr_row.setContentsMargins(14,0,14,0); miss_hdr_row.setSpacing(10)
        miss_badge = QLabel(f"STEP {step_num}")
        miss_badge.setStyleSheet("font-size:11px;font-weight:900;color:#FFAA00;background:#030810;border:1px solid #FFAA0044;padding:3px 10px;letter-spacing:3px;font-family:Consolas;")
        miss_title = QLabel("MISSING PART")
        miss_title.setStyleSheet("font-size:18px;font-weight:900;color:#FFFFFF;letter-spacing:3px;font-family:Consolas;background:transparent;")
        miss_hdr_row.addWidget(miss_badge); miss_hdr_row.addWidget(miss_title); miss_hdr_row.addStretch()
        layout.addWidget(miss_hdr)

        # Warning icon
        warning_label = QLabel("⚠")
        warning_label.setFixedHeight(70)
        warning_label.setStyleSheet("font-size:44px;color:#FFAA00;background:#050D18;border-bottom:1px solid #0E2A40;")
        warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(warning_label)

        # Data rows
        for row_lbl, row_val, row_color, row_bg in [
            ("PRODUCT", product_name,  "#FFFFFF",  "#030810"),
            ("MES PART", part_needed,  "#FF3344",  "#1A0508"),
            ("STOCK QTY", str(current_stock), "#FF3344", "#1A0508"),
        ]:
            rw = QWidget()
            left_accent = "#FFAA00" if row_color == "#FFFFFF" else "#FF3344"
            rw.setStyleSheet(f"background:{row_bg};border-bottom:1px solid #0E2A40;border-left:3px solid {left_accent};")
            rwl = QHBoxLayout(rw); rwl.setContentsMargins(14,10,14,10); rwl.setSpacing(12)
            lk = QLabel(row_lbl); lk.setStyleSheet("font-size:10px;color:#553300;letter-spacing:3px;font-family:Consolas;background:transparent;min-width:80px;")
            lv = QLabel(row_val); lv.setStyleSheet(f"font-size:18px;color:{row_color};font-weight:900;font-family:Consolas;background:transparent;")
            lv.setWordWrap(True)
            rwl.addWidget(lk); rwl.addWidget(lv); rwl.addStretch()
            layout.addWidget(rw)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setContentsMargins(20, 0, 20, 0)

        skip_btn = QPushButton("⏭  SKIP")
        skip_btn.setFixedHeight(54)
        skip_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: 800;
                background-color: #1A1000; color: #FFAA00;
                border: 1px solid #553300; border-bottom: 5px solid #331A00;
                border-left: 3px solid #FFAA00; border-radius: 2px;
                font-family: Consolas; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #221400; color: #FFFFFF; border-color: #FFAA00; }
            QPushButton:pressed { border-bottom: 2px solid #331A00; padding-top: 3px; }
        """)

        wait_btn = QPushButton("⏳  WAIT")
        wait_btn.setFixedHeight(54)
        wait_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: 800;
                background-color: #041828; color: #00AAFF;
                border: 1px solid #1A5A80; border-bottom: 5px solid #0A2A50;
                border-left: 3px solid #00AAFF; border-radius: 2px;
                font-family: Consolas; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #082030; color: #FFFFFF; border-color: #00AAFF; }
            QPushButton:pressed { border-bottom: 2px solid #0A2A50; padding-top: 3px; }
        """)

        cancel_btn = QPushButton("✕  CANCEL")
        cancel_btn.setFixedHeight(54)
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: 800;
                background-color: #1A0508; color: #FF3344;
                border: 1px solid #661020; border-bottom: 5px solid #440010;
                border-left: 3px solid #FF3344; border-radius: 2px;
                font-family: Consolas; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #220810; color: #FFFFFF; border-color: #FF3344; }
            QPushButton:pressed { border-bottom: 2px solid #440010; padding-top: 3px; }
        """)

        skip_btn.clicked.connect(lambda: dialog.done(1))
        wait_btn.clicked.connect(lambda: dialog.done(2))
        cancel_btn.clicked.connect(lambda: dialog.done(3))

        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(wait_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        result = dialog.exec()
        if result == 1: return "skip"
        elif result == 2: return "wait"
        else: return "cancel"

    @staticmethod
    def _execute_assembly_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        assembly_data = block_data.get('assembly_data', {})
        selections = {}
        total_assembly_steps = 0
        if 'selections' in assembly_data and isinstance(assembly_data['selections'], dict):
            selections_data = assembly_data['selections']
            step_keys = [k for k in selections_data.keys() if k.isdigit()]
            if step_keys:
                selections = selections_data
                total_assembly_steps = len(step_keys)
            else:
                if 'selections' in selections_data:
                    selections = selections_data.get('selections', {})
                    total_assembly_steps = selections_data.get('total_steps', 0)
        if not selections:
            step_keys = [k for k in assembly_data.keys() if k.isdigit()]
            if step_keys:
                selections = {k: assembly_data[k] for k in step_keys}
                total_assembly_steps = len(step_keys)
        if total_assembly_steps == 0:
            total_assembly_steps = assembly_data.get('total_steps', 0)
        if total_assembly_steps == 0 or not selections:
            QMessageBox.warning(parent_widget, "⚠️ No Configuration", "This Assembly block has no assembly steps configured!")
            return False
        for step_num in range(1, total_assembly_steps + 1):
            step_key = str(step_num)
            if step_key in selections:
                selection = dict(selections[step_key])
                selection['uploaded_video_path'] = assembly_data.get('uploaded_video_path', '')
                step_success = PipelineRunner._execute_assembly_step_like_dialog(step_num, total_assembly_steps, selection, parent_widget)
                if not step_success:
                    break
        return True

    @staticmethod
    def cleanup(force_disconnect=True, keep_orbbec=False):
        """Cleanup resources - can selectively keep Orbbec alive"""

        if keep_orbbec:
            print("[PipelineRunner] Partial cleanup - keeping Orbbec alive")
            # Only cleanup TCP/heartbeat, not Orbbec
            if PipelineRunner._heartbeat_manager:
                PipelineRunner._heartbeat_manager.disconnect()
                PipelineRunner._heartbeat_manager = None
        else:
            # Full cleanup including Orbbec
            if PipelineRunner._heartbeat_manager:
                PipelineRunner._heartbeat_manager.disconnect()
                PipelineRunner._heartbeat_manager = None

            print("[PipelineRunner] Skipping Orbbec stop (always-on mode)")

    @staticmethod
    def remove_pending_job(recipe_name: str, job_id: str):
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return
        pending_file = os.path.join(recipe_folder, 'pending_jobs.json')
        existing = []
        if os.path.exists(pending_file):
            try:
                with open(pending_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        existing = [j for j in existing if j.get('job_id') != job_id]
        try:
            with open(pending_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving pending jobs: {e}")

    @staticmethod
    def _execute_screw_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        PipelineRunner._init_heartbeat_manager()
        # PipelineRunner.send_screw_start_to_server()
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_number}: Screw Operation")
        dialog.showFullScreen()
        dialog.setStyleSheet("QDialog { background-color: #060C14; }")

        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        recipe_name = config_manager.current_recipe
        config = block_data.get('config')
        video_path = ""
        if isinstance(config, dict):
            video_path = config.get("uploaded_video_path", "") or ""

        try:
            block_id = PipelineRunner._resolve_block_id(block_data)
        except Exception as e:
            QMessageBox.warning(parent_widget, "⚠️ Missing Block ID",
                                f"Screw block does not contain a valid block id.\n\n{str(e)}")
            return False

        first_send_success, first_coord_string = PipelineRunner._send_latest_coordinates_from_folder(recipe_name,
                                                                                                     "ScrewBoxesData",
                                                                                                     block_id)

        orbbec_thread = PipelineRunner.get_orbbec_thread()
        screw_trigger_done = {"done": False}

        # ── TECH HEADER BAR ──────────────────────────────────────────────
        hdr_bar = QWidget()
        hdr_bar.setFixedHeight(80)
        hdr_bar.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0A1828,stop:0.5 #060C14,stop:1 #050D18);"
            "border-bottom:2px solid #00AAFF;")
        hdr_row = QHBoxLayout(hdr_bar)
        hdr_row.setContentsMargins(24, 0, 24, 0)
        hdr_row.setSpacing(20)
        step_badge = QLabel(f"STEP {step_number}/{total_steps}")  # No spaces around slash
        step_badge.setStyleSheet(
            "font-size:16px;font-weight:900;color:#00AAFF;background:#030810;border:1px solid #00AAFF44;padding:4px 14px;letter-spacing:2px;font-family:Consolas;")
        step_badge.setFixedHeight(24)  # Match assembly height
        step_badge.setContentsMargins(0, 0, 0, 0)
        hdr_title = QLabel("SCREW OPERATION")
        hdr_title.setStyleSheet(
            "font-size:28px;font-weight:900;color:#FFFFFF;"
            "letter-spacing:6px;font-family:Consolas;background:transparent;")
        hdr_row.addWidget(step_badge)
        hdr_row.addWidget(hdr_title)
        hdr_row.addStretch()
        layout.addWidget(hdr_bar)

        # cyan separator line
        sep = QWidget(); sep.setFixedHeight(2)
        sep.setStyleSheet("background:#00AAFF;")
        layout.addWidget(sep)

        if config:
            if isinstance(config, dict):
                screw_count = config.get('count', 'N/A')
                screw_type = config.get('type', 'N/A')
                torque = config.get('torque', 'N/A')
                screw_length = config.get('length', 'N/A')
            else:
                screw_count = screw_type = torque = screw_length = "N/A"
                if isinstance(config, str):
                    for line in config.strip().split('\n'):
                        ll = line.lower()
                        if 'count:' in ll:
                            screw_count = line.split(':')[-1].strip()
                        elif 'type:' in ll:
                            screw_type = line.split(':')[-1].strip()
                        elif 'torque:' in ll:
                            torque = line.split(':')[-1].strip()
                        elif 'length:' in ll:
                            screw_length = line.split(':')[-1].strip()

            # ── Data grid: 4 big cells ─────────────────────────────────
            data_panel = QWidget()
            data_panel.setStyleSheet(
                "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                "stop:0 #071018,stop:1 #060C14);"
                "border-bottom:1px solid #0E2A40;")
            data_grid = QGridLayout(data_panel)
            data_grid.setSpacing(1)
            data_grid.setContentsMargins(0, 0, 0, 0)

            screw_data_pairs = [
                ("SCREW COUNT", str(screw_count), "pcs"),
                ("SCREW TYPE",  str(screw_type),  ""),
                ("SCREW LENGTH",str(screw_length), "mm"),
                ("TORQUE",      str(torque),       "Nm"),
            ]

            for i, (lbl, val, unit) in enumerate(screw_data_pairs):
                cell = QWidget()
                is_right = (i % 2 == 1)
                cell.setStyleSheet(
                    f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                    f"stop:0 #0A1828,stop:1 #060C14);"
                    f"border-right:{'0' if is_right else '1'}px solid #0E2A40;"
                    f"border-bottom:1px solid #0E2A40;"
                    f"border-left:{'3px solid #00AAFF44' if not is_right else 'none'};")
                cl = QVBoxLayout(cell)
                cl.setContentsMargins(28, 20, 28, 20)
                cl.setSpacing(8)

                lw = QLabel(lbl)
                lw.setStyleSheet(
                    "font-size:22px;color:#2A5A8A;letter-spacing:4px;"
                    "font-family:Consolas;font-weight:900;background:transparent;")

                val_row = QWidget(); val_row.setStyleSheet("background:transparent;")
                vrl = QHBoxLayout(val_row)
                vrl.setContentsMargins(0, 0, 0, 0); vrl.setSpacing(10)
                vw = QLabel(val)
                vw.setStyleSheet(
                    "font-size:52px;color:#00AAFF;font-weight:900;"
                    "font-family:Consolas;letter-spacing:2px;background:transparent;")
                uw = QLabel(unit)
                uw.setStyleSheet(
                    "font-size:20px;color:#1A4A6A;font-weight:900;"
                    "font-family:Consolas;background:transparent;"
                    "padding-top:24px;")
                vrl.addWidget(vw); vrl.addWidget(uw); vrl.addStretch()

                cl.addWidget(lw)
                cl.addWidget(val_row)
                data_grid.addWidget(cell, i // 2, i % 2)

            layout.addWidget(data_panel)

        else:
            warning_frame = QFrame()
            warning_frame.setStyleSheet(
                "QFrame { border:1px solid #661020; border-left:3px solid #FF3344; "
                "border-radius:0px; background:#1A0508; padding:30px; margin:12px; }")
            warning_layout = QVBoxLayout(warning_frame)
            warning_label = QLabel("⚠  NO CONFIGURATION FOUND")
            warning_label.setStyleSheet(
                "font-size:24px;font-weight:900;color:#FF3344;font-family:Consolas;letter-spacing:3px;")
            warning_label.setAlignment(Qt.AlignCenter)
            warning_layout.addWidget(warning_label)
            layout.addWidget(warning_frame)

        # # ── Instructions panel ────────────────────────────────────────────
        # instr_panel = QWidget()
        # instr_panel.setStyleSheet(
        #     "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        #     "stop:0 #060C14,stop:1 #040A10);"
        #     "border-top:1px solid #0E2A40;")
        # instr_layout = QVBoxLayout(instr_panel)
        # instr_layout.setContentsMargins(32, 24, 32, 24)
        # instr_layout.setSpacing(16)
        #
        # instr_title = QLabel("OPERATOR INSTRUCTIONS")
        # instr_title.setStyleSheet(
        #     "font-size:12px;font-weight:900;color:#2A5A8A;"
        #     "letter-spacing:5px;font-family:Consolas;"
        #     "border-bottom:1px solid #0E2A40;padding-bottom:10px;background:transparent;")
        # instr_layout.addWidget(instr_title)
        #
        # steps_data = [
        #     ("01", "Prepare tool or screwdriver"),
        #     ("02", "Position at target locations"),
        #     ("03", "Apply specified torque"),
        #     ("04", "Verify tightness on all screws"),
        #     ("05", "Check final alignment"),
        # ]
        # for num, text in steps_data:
        #     row = QWidget(); row.setStyleSheet("background:transparent;")
        #     rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(16)
        #     num_lbl = QLabel(num)
        #     num_lbl.setFixedWidth(52)
        #     num_lbl.setStyleSheet(
        #         "font-size:18px;font-weight:900;color:#00AAFF55;"
        #         "font-family:Consolas;background:transparent;")
        #     dot_lbl = QLabel("·")
        #     dot_lbl.setStyleSheet(
        #         "font-size:18px;color:#1A3A5C;font-family:Consolas;background:transparent;")
        #     dot_lbl.setFixedWidth(16)
        #     txt_lbl = QLabel(text)
        #     txt_lbl.setStyleSheet(
        #         "font-size:20px;color:#AACCEE;font-family:Consolas;background:transparent;")
        #     rl.addWidget(num_lbl); rl.addWidget(dot_lbl); rl.addWidget(txt_lbl); rl.addStretch()
        #     instr_layout.addWidget(row)
        #
        # layout.addWidget(instr_panel, 1)
        # ── Vertical spacer (fills space between data grid and footer) ────
        layout.addStretch(1)

        # ── Button footer ─────────────────────────────────────────────────
        btn_footer = QWidget()
        btn_footer.setFixedHeight(100)
        btn_footer.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #0A1828,stop:1 #060C14);"
            "border-top:2px solid #00AAFF33;")
        btn_row = QHBoxLayout(btn_footer)
        btn_row.setContentsMargins(24, 16, 24, 16)
        btn_row.setSpacing(16)

        cancel_btn = QPushButton("✕  CANCEL")
        cancel_btn.setFixedHeight(66)
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 22px; font-weight: 900;
                background: transparent;
                color: #FF3344;
                border: 1px solid #FF334455;
                border-radius: 2px;
                min-width: 200px;
                font-family: Consolas; letter-spacing: 2px;
            }
            QPushButton:hover {
                background: #1A0508;
                border: 1px solid #FF3344;
                color: #FFFFFF;
            }
            QPushButton:pressed { background: #220810; }
        """)

        ok_btn = QPushButton("✓  OK  —  CONTINUE")
        ok_btn.setFixedHeight(66)
        ok_btn.setStyleSheet("""
            QPushButton {
                font-size: 22px; font-weight: 900;
                background-color: #031A10;
                color: #00FF88;
                border: none;
                border-top: 2px solid #00FF88;
                border-radius: 0px;
                min-width: 320px;
                font-family: Consolas; letter-spacing: 3px;
            }
            QPushButton:hover { background-color: #052A18; color: #FFFFFF; }
            QPushButton:pressed { background-color: #021008; }
        """)

        def on_cancel():
            if screw_trigger_done["done"]:
                return
            screw_trigger_done["done"] = True
            dialog.reject()

        cancel_btn.clicked.connect(on_cancel)

        def on_ok_continue():
            if screw_trigger_done["done"]:
                return

            screw_trigger_done["done"] = True

            second_send_success, second_coord_string = PipelineRunner._send_latest_coordinates_from_folder(
                recipe_name,
                "ScrewBoxesData2",
                block_id
            )

            PipelineRunner.send_screw_start_to_server()

            dialog.accept()
            if video_path and os.path.exists(video_path):
                PipelineRunner._show_video_dialog(
                    video_path=video_path,
                    parent_widget=parent_widget,
                    title="SCREW ASSEMBLY RESULT"
                )

        ok_btn.clicked.connect(on_ok_continue)
        def on_screw_hand_trigger():
            try:
                if screw_trigger_done["done"]:
                    return
                print("[SCREW OPERATION] Hand detected in trigger zone!")
                on_ok_continue()
            except Exception as e:
                print(f"[SCREW OPERATION] Trigger error: {e}")

        PipelineRunner.set_orbbec_trigger(orbbec_thread, on_screw_hand_trigger, state="idle")

        def _cleanup_screw_dialog(*_):
            try:
                main_page = None
                for w in QApplication.topLevelWidgets():
                    if hasattr(w, "main_page"):
                        main_page = w.main_page
                        break
                    if w.__class__.__name__ == "MainPage":
                        main_page = w
                        break

                if main_page and hasattr(main_page, "on_orbbec_start_trigger"):
                    PipelineRunner.set_orbbec_trigger(
                        orbbec_thread,
                        main_page.on_orbbec_start_trigger,
                        state="idle"
                    )
                    print("[SCREW OPERATION] Trigger restored to MainPage")
                else:
                    PipelineRunner.set_orbbec_trigger(orbbec_thread, None, state="idle")
                    print("[SCREW OPERATION] Trigger cleared")
            except Exception as e:
                print(f"[SCREW OPERATION] Cleanup trigger error: {e}")

        dialog.finished.connect(_cleanup_screw_dialog)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addWidget(btn_footer)

        result = dialog.exec()
        return result == QDialog.Accepted

    @staticmethod
    def _resolve_block_id(block_data: Dict) -> str:
        candidates = []
        if isinstance(block_data, dict):
            candidates.extend([block_data.get("id"), block_data.get("block_id"), block_data.get("block_number"), block_data.get("index")])
            for key in ("config", "screw_data", "capture_info"):
                sub = block_data.get(key)
                if isinstance(sub, dict):
                    candidates.extend([sub.get("id"), sub.get("block_id"), sub.get("block_number"), sub.get("index")])
        for value in candidates:
            if value is not None and str(value).strip() != "":
                return str(value)
        raise ValueError("Cannot resolve block id from block_data")

    @staticmethod
    def _execute_generic_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        block_name = block_data.get('name', 'Unknown')
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_number}: {block_name}")
        dialog.showFullScreen()
        dialog.setStyleSheet("QDialog { background-color: #030810; }")

        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        gen_hdr = QWidget(); gen_hdr.setFixedHeight(60)
        gen_hdr.setStyleSheet("background:#050D18;border-bottom:2px solid #00AAFF;")
        gen_hdr_row = QHBoxLayout(gen_hdr); gen_hdr_row.setContentsMargins(14,0,14,0); gen_hdr_row.setSpacing(10)
        gen_badge = QLabel(f"STEP {step_number}/{total_steps}")
        gen_badge.setStyleSheet("font-size:11px;font-weight:900;color:#00AAFF;background:#030810;border:1px solid #00AAFF44;padding:3px 10px;letter-spacing:3px;font-family:Consolas;")
        gen_title = QLabel(block_name.upper())
        gen_title.setStyleSheet("font-size:18px;font-weight:900;color:#FFFFFF;letter-spacing:3px;font-family:Consolas;background:transparent;")
        gen_hdr_row.addWidget(gen_badge); gen_hdr_row.addWidget(gen_title); gen_hdr_row.addStretch()
        layout.addWidget(gen_hdr)

        info_label = QLabel(f"Executing: {block_name}\n\nStep {step_number} of {total_steps}")
        info_label.setStyleSheet("font-size:20px;color:#CCDDEE;padding:28px 20px;background:#050D18;border:none;border-left:3px solid #00AAFF;font-family:Consolas;")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        ok_btn = QPushButton("▶  CONTINUE")
        ok_btn.setFixedHeight(58)
        ok_btn.setStyleSheet("""
            QPushButton {
                font-size: 18px; font-weight: 800;
                background-color: #031A10; color: #00FF88;
                border: 1px solid #0A5030; border-bottom: 5px solid #051008;
                border-left: 3px solid #00FF88; border-radius: 2px;
                margin-top: 12px; font-family: Consolas; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #052A18; color: #FFFFFF; border-color: #00FF88; }
            QPushButton:pressed { border-bottom: 2px solid #051008; padding-top: 3px; }
        """)
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)

        return dialog.exec() == QDialog.Accepted

    @staticmethod
    def get_pending_jobs(recipe_name: str) -> List[Dict]:
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return []
        pending_file = os.path.join(recipe_folder, 'pending_jobs.json')
        if os.path.exists(pending_file):
            try:
                with open(pending_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    @staticmethod
    def save_pending_job(recipe_name: str, job_data: Dict):
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return
        pending_file = os.path.join(recipe_folder, 'pending_jobs.json')
        existing = []
        if os.path.exists(pending_file):
            try:
                with open(pending_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        status = job_data.get('status', '')
        job_id = job_data.get('job_id')
        completed_steps = job_data.get('completed_steps', [])
        total_steps = job_data.get('total_steps', 0)
        existing = [j for j in existing if j.get('job_id') != job_id]
        if status != 'complete' and len(completed_steps) < total_steps:
            existing.append(job_data)
        if len(existing) > 100:
            existing = existing[-100:]
        try:
            with open(pending_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving pending job: {e}")

    @staticmethod
    def clean_completed_jobs(recipe_name: str):
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return
        pending_file = os.path.join(recipe_folder, 'pending_jobs.json')
        if not os.path.exists(pending_file):
            return
        try:
            with open(pending_file, 'r', encoding='utf-8') as f:
                jobs = json.load(f)
            incomplete_jobs = [j for j in jobs if j.get('status', '') in ['partial', 'waiting', 'pending']]
            with open(pending_file, 'w', encoding='utf-8') as f:
                json.dump(incomplete_jobs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error cleaning completed jobs: {e}")

    @staticmethod
    def _execute_assembly_step_like_dialog(step_num: int, assembly_total: int, pipeline_step: int, pipeline_total: int,
                                           selection: Dict, parent_widget) -> bool:
        from datetime import datetime
        import os
        import shutil
        import cv2
        import numpy as np
        from PySide6.QtWidgets import QApplication, QProgressBar
        from PySide6.QtCore import QTimer, QSize
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtMultimediaWidgets import QVideoWidget
        from camera.orbbec_manager import OrbbecManager

        PipelineRunner._init_heartbeat_manager()
        calibration = PipelineRunner._load_calibration(config_manager.current_recipe)

        product_data = selection.get('product_data', {})
        product_name = product_data.get('name', f'Product {step_num}')
        product_id = selection.get('product_id', product_data.get('id', f'product_{step_num}'))
        uploaded_video_path = selection.get('uploaded_video_path', '')
        capture_runner = None

        # Find reference image
        reference_image_path = product_data.get('image_path')
        if not reference_image_path or not os.path.exists(reference_image_path):
            recipe_folder = config_manager.get_recipe_folder(config_manager.current_recipe)
            if recipe_folder:
                annotation_folder = os.path.join(recipe_folder, "Annotation")
                if os.path.exists(annotation_folder):
                    import glob
                    for ext in ['bmp', 'png', 'jpg', 'jpeg']:
                        p = os.path.join(annotation_folder, f"{product_name}.{ext}")
                        if os.path.exists(p):
                            reference_image_path = p
                            break
                    if not reference_image_path or not os.path.exists(reference_image_path):
                        for ext in ['bmp', 'png', 'jpg', 'jpeg']:
                            matches = glob.glob(os.path.join(annotation_folder, f"*{product_name}*.{ext}"))
                            if matches:
                                reference_image_path = sorted(matches, key=os.path.getmtime, reverse=True)[0]
                                break

        if reference_image_path and not os.path.isabs(reference_image_path):
            recipe_folder = config_manager.get_recipe_folder(config_manager.current_recipe)
            if recipe_folder:
                candidate = os.path.join(recipe_folder, reference_image_path)
                if os.path.exists(candidate):
                    reference_image_path = candidate

        block_id = None
        capture_info = selection.get('capture_info', {})
        block_id = capture_info.get('block_id')
        if not block_id:
            import re
            if reference_image_path and 'Block_' in reference_image_path:
                match = re.search(r'Block_(\d+)', reference_image_path)
                if match:
                    block_id = match.group(1)
        if not block_id:
            block_id = '1'

        recipe_name = config_manager.current_recipe
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        capture_folder = os.path.join(recipe_folder, "Capture")
        os.makedirs(capture_folder, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Image_{timestamp}.bmp"
        new_capture_path = os.path.join(capture_folder, filename)

        # Orbbec manager / shared thread
        manager = OrbbecManager.get_instance()
        orbbec_thread = manager.get_thread(recipe_name)

        # Find YOLO model
        model_path = None
        class_id = None
        recipe_path = config_manager.get_recipe_folder(recipe_name)
        if recipe_path:
            yolo_model_folder = os.path.join(recipe_path, "yolo_model")
            if os.path.exists(yolo_model_folder):
                import glob
                best_files = glob.glob(os.path.join(yolo_model_folder, "**", "weights", "best.pt"), recursive=True)
                if best_files:
                    model_path = sorted(best_files, key=os.path.getmtime, reverse=True)[0]
                    try:
                        from ultralytics import YOLO
                        temp_model = YOLO(model_path)
                        if hasattr(temp_model, 'names'):
                            for cid, name in temp_model.names.items():
                                if product_name.lower() == name.lower():
                                    class_id = cid
                                    break
                            if class_id is None:
                                for cid, name in temp_model.names.items():
                                    if product_name.lower() in name.lower() or name.lower() in product_name.lower():
                                        class_id = cid
                                        break
                            if class_id is None and '_' in product_name:
                                lp = product_name.split('_')[-1]
                                for cid, name in temp_model.names.items():
                                    if lp.lower() == name.lower() or lp.lower() in name.lower():
                                        class_id = cid
                                        break
                        del temp_model
                    except Exception as e:
                        print(f"DEBUG: Error getting class mapping: {e}")

        # ── CREATE TECH DIALOG ────────────────────────────────────────────
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_num}/{pipeline_total}: {product_name}")
        dialog.showFullScreen()
        dialog.setStyleSheet("QDialog { background-color: #030810; }")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tech header bar
        hdr_bar = QWidget()
        hdr_bar.setFixedHeight(80)
        hdr_bar.setStyleSheet("background-color:#050D18;border-bottom:2px solid #00AAFF;")
        hdr_row = QHBoxLayout(hdr_bar)
        hdr_row.setContentsMargins(14, 0, 14, 0)
        hdr_row.setSpacing(12)
        asm_step_badge = QLabel(f"STEP {pipeline_step}/{pipeline_total}")
        asm_step_badge.setStyleSheet(
            "font-size:16px;font-weight:900;color:#00AAFF;background:#030810;border:1px solid #00AAFF44;padding:4px 14px;letter-spacing:2px;font-family:Consolas;")
        asm_step_badge.setFixedHeight(24)
        asm_step_badge.setContentsMargins(0, 0, 0, 0)
        asm_title = QLabel(product_name.upper())
        asm_title.setStyleSheet(
            "font-size:26px;font-weight:900;color:#FFFFFF;letter-spacing:2px;font-family:Consolas;background:transparent;")
        hdr_row.addWidget(asm_step_badge)
        hdr_row.addWidget(asm_title)
        hdr_row.addStretch()
        layout.addWidget(hdr_bar)

        # Cyan separator line
        sep_line = QWidget()
        sep_line.setFixedHeight(2)
        sep_line.setStyleSheet("background:#00AAFF;")
        layout.addWidget(sep_line)

        splitter_wrap = QWidget()
        splitter_wrap.setStyleSheet("background:#030810;")
        sw_layout = QVBoxLayout(splitter_wrap)
        sw_layout.setContentsMargins(0, 0, 0, 0)
        sw_layout.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #0E2A40; width:2px; }")
        sw_layout.addWidget(splitter)

        # LEFT: Product image
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #060C14;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        ref_header = QWidget()
        ref_header.setFixedHeight(44)
        ref_header.setStyleSheet("background:#050D18;border-bottom:1px solid #0E2A40;border-right:1px solid #0E2A40;")
        rh_row = QHBoxLayout(ref_header)
        rh_row.setContentsMargins(10, 0, 10, 0)
        rh_row.setSpacing(8)
        rh_dot = QLabel("●")
        rh_dot.setStyleSheet("font-size:14px;color:#00AAFF;background:transparent;")
        rh_lbl = QLabel("PRODUCT IMAGE")
        rh_lbl.setStyleSheet(
            "font-size:16px;font-weight:900;color:#AACCEE;letter-spacing:3px;font-family:Consolas;background:transparent;")
        rh_row.addWidget(rh_dot)
        rh_row.addWidget(rh_lbl)
        rh_row.addStretch()
        left_layout.addWidget(ref_header)

        ref_image_label = QLabel()
        ref_image_label.setAlignment(Qt.AlignCenter)
        ref_image_label.setMinimumHeight(450)
        ref_image_label.setStyleSheet("QLabel { border:none; background-color:#030810; padding:4px; }")
        if reference_image_path and os.path.exists(reference_image_path):
            pixmap = QPixmap(reference_image_path)
            if not pixmap.isNull():
                ref_image_label.setPixmap(pixmap.scaled(550, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            ref_image_label.setText(f"⚠ Product image not found\n\n{product_name}")
            ref_image_label.setStyleSheet(
                "color: #FFAA00; font-size: 18px; font-family: Consolas; background-color: #0A0800; border: 1px solid #553300; border-left: 3px solid #FFAA00; padding: 20px;")
        left_layout.addWidget(ref_image_label, stretch=1)

        # RIGHT: Detection
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #060C14;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        det_panel_hdr = QWidget()
        det_panel_hdr.setFixedHeight(44)
        det_panel_hdr.setStyleSheet("background:#050D18;border-bottom:1px solid #0E2A40;")
        dph_row = QHBoxLayout(det_panel_hdr)
        dph_row.setContentsMargins(10, 0, 10, 0)
        dph_row.setSpacing(8)
        dph_dot = QLabel("●")
        dph_dot.setStyleSheet("font-size:14px;color:#FF3344;background:transparent;")
        detection_header = QLabel("DETECTION RESULT")
        detection_header.setStyleSheet(
            "font-size:16px;font-weight:900;color:#AACCEE;letter-spacing:3px;font-family:Consolas;background:transparent;")
        dph_row.addWidget(dph_dot)
        dph_row.addWidget(detection_header)
        dph_row.addStretch()
        right_layout.addWidget(det_panel_hdr)

        detection_container = QWidget()
        detection_container.setMinimumHeight(300)
        detection_container.setStyleSheet("QWidget { border: none; background-color: #030810; }")
        detection_container_layout = QVBoxLayout(detection_container)

        loading_widget = QWidget()
        loading_widget.setStyleSheet("background-color: transparent;")
        loading_layout = QVBoxLayout(loading_widget)

        loading_label = QLabel()
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setMinimumHeight(200)
        loading_label.setText("⏳ Processing...")
        loading_label.setStyleSheet("""
            QLabel {
                font-size: 22px; color: #00AAFF; font-weight: 800;
                font-family: Consolas; letter-spacing: 2px;
                background-color: transparent;
            }
        """)

        dot_count = 0
        loading_timer = QTimer()

        def update_loading_text():
            nonlocal dot_count
            dot_count = (dot_count + 1) % 4
            loading_label.setText(f"⏳ Processing{'.' * dot_count}")

        loading_timer.timeout.connect(update_loading_text)
        loading_timer.start(500)
        loading_layout.addWidget(loading_label)

        loading_message = QLabel("Capturing image and running AI detection...")
        loading_message.setAlignment(Qt.AlignCenter)
        loading_message.setStyleSheet(
            "font-size: 16px; color: #7AAAD4; margin-top: 20px; font-family: Consolas; background-color: transparent;")
        loading_layout.addWidget(loading_message)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 0)
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1A3A5C; border-radius: 0px;
                text-align: center; height: 6px; max-width: 320px;
                background-color: #050D18;
            }
            QProgressBar::chunk { background-color: #00AAFF; border-radius: 0px; }
        """)
        loading_layout.addWidget(progress_bar, alignment=Qt.AlignCenter)
        detection_container_layout.addWidget(loading_widget)

        detection_label = QLabel()
        detection_label.setAlignment(Qt.AlignCenter)
        detection_label.setVisible(False)
        detection_label.setStyleSheet("background-color: transparent;")
        detection_label.setFixedSize(1280, 720)
        detection_container_layout.addWidget(detection_label)
        right_layout.addWidget(detection_container, stretch=1)

        # Hidden labels kept for logic compatibility
        cal_status_label = QLabel()
        cal_status_label.hide()
        detection_status = QLabel("STATUS: Initializing camera...")
        detection_status.hide()
        detection_result = QLabel("DETECTED: --")
        detection_result.hide()
        confidence_label = QLabel("CONFIDENCE: --")
        confidence_label.hide()
        coord_status_label = QLabel("COORDINATES: Not sent")
        coord_status_label.hide()
        info_frame = QFrame()
        info_frame.hide()

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([550, 550])
        layout.addWidget(splitter_wrap, stretch=1)

        # Buttons
        button_layout = QHBoxLayout()

        cancel_btn = QPushButton("✕  CANCEL")
        cancel_btn.setFixedHeight(58)
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: 800;
                background-color: #1A0508; color: #FF3344;
                border: 1px solid #661020; border-bottom: 5px solid #440010;
                border-left: 3px solid #FF3344; border-radius: 2px;
                min-width: 160px; font-family: Consolas; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #220810; color: #FFFFFF; border-color: #FF3344; }
            QPushButton:pressed { border-bottom: 2px solid #440010; padding-top: 3px; }
        """)

        def cleanup_capture_runner():
            nonlocal capture_runner
            if capture_runner is not None:
                try:
                    if hasattr(capture_runner, "stop"):
                        capture_runner.stop()
                    elif hasattr(capture_runner, "close"):
                        capture_runner.close()
                except Exception as e:
                    print(f"⚠️ Error cleaning capture runner: {e}")
                capture_runner = None

        def on_cancel():
            stop_orbbec_live_view()
            cleanup_capture_runner()
            dialog.reject()

        cancel_btn.clicked.connect(on_cancel)

        retry_btn = QPushButton("↺  RETRY")
        retry_btn.setFixedHeight(58)
        retry_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: 800;
                background-color: #1A1000; color: #FFAA00;
                border: 1px solid #553300; border-bottom: 5px solid #331A00;
                border-left: 3px solid #FFAA00; border-radius: 2px;
                min-width: 200px; font-family: Consolas; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #221400; color: #FFFFFF; border-color: #FFAA00; }
            QPushButton:pressed { border-bottom: 2px solid #331A00; padding-top: 3px; }
        """)
        retry_btn.setEnabled(False)

        verify_btn = QPushButton("✓  VERIFY & CONTINUE")
        verify_btn.setFixedHeight(58)
        verify_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: 800;
                background-color: #0A1C0A; color: #2A4A2A;
                border: 1px solid #1A3A1A; border-bottom: 5px solid #050A05;
                border-left: 3px solid #1A3A1A; border-radius: 2px;
                min-width: 220px; font-family: Consolas; letter-spacing: 1px;
            }
            QPushButton:enabled {
                background-color: #031A10; color: #00FF88;
                border-color: #0A5030; border-left: 3px solid #00FF88;
            }
            QPushButton:enabled:hover { background-color: #052A18; color: #FFFFFF; border-color: #00FF88; }
            QPushButton:enabled:pressed { border-bottom: 2px solid #0A5030; padding-top: 3px; }
        """)
        verify_btn.setEnabled(False)

        btn_wrap = QWidget()
        btn_wrap.setFixedHeight(66)
        btn_wrap.setStyleSheet("background:#030810;border-top:1px solid #0E2A40;")
        bwl = QHBoxLayout(btn_wrap)
        bwl.setContentsMargins(10, 8, 10, 8)
        bwl.setSpacing(8)
        bwl.addWidget(cancel_btn)
        bwl.addStretch()
        bwl.addWidget(retry_btn)
        bwl.addWidget(verify_btn)
        layout.addWidget(btn_wrap)

        # State variables
        captured_image_path = None
        detection_results = None
        output_path = None
        processing_complete = False
        predictions_for_sending = []
        target_detected_successfully = False
        auto_retry_count = 0
        max_auto_retry = 1
        manual_retry_count = 0

        def show_results():
            nonlocal processing_complete
            QApplication.processEvents()
            loading_widget.setVisible(False)
            detection_label.setVisible(True)
            processing_complete = True
            if loading_timer.isActive():
                loading_timer.stop()

        def has_target_class(detections, target_class_id):
            try:
                if len(detections.boxes) == 0:
                    return False
                if target_class_id is None:
                    return len(detections.boxes) > 0
                boxes = detections.boxes
                class_ids = boxes.cls.cpu().numpy() if hasattr(boxes.cls, 'cpu') else boxes.cls
                return any(int(cid) == int(target_class_id) for cid in class_ids)
            except Exception:
                return False

        def update_detection_pixmap(pixmap):
            if pixmap.isNull():
                return
            target_size = detection_container.size() - QSize(20, 20)
            if target_size.width() < 100 or target_size.height() < 100:
                target_size = QSize(700, 450)
            detection_label.setPixmap(pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        def _set_detection_header(text, color, bg):
            detection_header.setText(text)
            detection_header.setStyleSheet(
                f"font-size:16px;font-weight:900;color:{color};letter-spacing:3px;font-family:Consolas;background:transparent;")
            dph_dot.setStyleSheet(f"font-size:14px;color:{color};background:transparent;")

        def update_orbbec_view(frame):
            if frame is None:
                return

            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]

                qimg = QImage(
                    rgb.data,
                    w,
                    h,
                    rgb.strides[0],
                    QImage.Format_RGB888
                ).copy()

                pixmap = QPixmap.fromImage(qimg)
                if pixmap.isNull():
                    return

                # ✅ 直接用 Orbbec 原始 size（最顺）
                scaled = pixmap.scaled(
                    1280, 720,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation
                )

                detection_label.setPixmap(scaled)
                detection_label.setAlignment(Qt.AlignCenter)

            except Exception as e:
                detection_status.setText(f"❌ Live error: {str(e)[:60]}")

        def on_pipeline_trigger_from_orbbec():
            print("[Assembly Step] Pipeline trigger received from hand gesture!")
            if verify_btn.isEnabled():
                QTimer.singleShot(100, verify_btn.click)
            else:
                print("[Assembly Step] Verify button not enabled, cannot auto-trigger")

        def start_orbbec_live_view():
            nonlocal orbbec_thread

            try:
                orbbec_thread = manager.get_thread(recipe_name)
                manager.attach_live_view(update_orbbec_view)

                # ✅ Show cached frame immediately so UI does not wait for next frame_signal
                if (
                        orbbec_thread is not None
                        and hasattr(orbbec_thread, "latest_frame")
                        and orbbec_thread.latest_frame is not None
                ):
                    try:
                        cached_frame = orbbec_thread.latest_frame.copy()
                        update_orbbec_view(cached_frame)
                        print("[Assembly Step] ✅ Displayed cached Orbbec frame immediately")
                    except Exception as e:
                        print(f"[Assembly Step] ⚠️ Failed to display cached frame: {e}")

                manager.set_handler(on_pipeline_trigger_from_orbbec)

                print("[Assembly Step] ✅ Using OrbbecManager")
            except Exception as e:
                print(f"[Assembly Step] ❌ Failed to connect Orbbec: {e}")
                detection_status.setText(f"❌ Failed to connect Orbbec: {str(e)[:60]}")

        def stop_orbbec_live_view():
            try:
                manager.clear_boxes()
            except Exception:
                pass

            try:
                manager.detach_live_view(update_orbbec_view)
            except Exception:
                pass

            try:
                manager.set_handler(None)
            except Exception:
                pass

        def start_detection_capture(status_text="STATUS: Opening camera."):
            nonlocal capture_runner

            detection_status.setText(status_text)
            detection_status.setStyleSheet(
                "font-size:12px;color:#FFAA00;font-weight:900;font-family:Consolas;padding:0px 10px;background:#030810;border-bottom:1px solid #0E2A40;")
            detection_header.setText("DETECTION RESULT")
            detection_header.setStyleSheet(
                "font-size:16px;font-weight:900;color:#AACCEE;letter-spacing:3px;font-family:Consolas;background:transparent;")
            dph_dot.setStyleSheet("font-size:14px;color:#FF3344;background:transparent;")
            detection_result.setText("DETECTED: --")
            confidence_label.setText("CONFIDENCE: --")
            coord_status_label.setText("COORDINATES: Not sent")
            coord_status_label.setStyleSheet(
                "font-size:12px;color:#7AAAD4;padding:0px 10px;background:#030810;font-family:Consolas;")

            detection_label.clear()
            detection_label.setText("")
            detection_label.setVisible(True)

            loading_widget.setVisible(False)

            verify_btn.setEnabled(False)
            retry_btn.setEnabled(False)

            start_orbbec_live_view()

            if not loading_timer.isActive():
                loading_timer.start(500)

            QApplication.processEvents()

            if CAMERA_AVAILABLE:
                from camera.camera import AutoCaptureFlow
                capture_runner = AutoCaptureFlow(callback=on_capture_finished)
            else:
                detection_status.setText("❌ Camera unavailable")
                detection_label.setText("❌ Camera module not available")
                show_results()

        def on_capture_finished(success, message, image_path):
            nonlocal captured_image_path, detection_results, output_path
            nonlocal predictions_for_sending, target_detected_successfully, auto_retry_count

            QApplication.processEvents()

            if not success or not image_path:
                detection_label.setText(f"❌ Capture failed: {message}")
                detection_status.setText(f"❌ {message}")
                detection_status.setStyleSheet(
                    "font-size: 14px; color: #FF3344; font-weight: 800; font-family: Consolas; padding: 4px 10px;")
                show_results()
                verify_btn.setEnabled(False)
                retry_btn.setEnabled(True)
                return

            try:
                detection_status.setText("STATUS: Running AI detection.")
                QApplication.processEvents()

                shutil.copy2(image_path, new_capture_path)
                if os.path.exists(image_path):
                    os.remove(image_path)

                captured_image_path = new_capture_path

                if not model_path or not os.path.exists(model_path):
                    _set_detection_header("⚠  NO YOLO MODEL", "#FFAA00", "#1A1000")
                    detection_status.setText("⚠ No model found in yolo_model folder")
                    detection_status.setStyleSheet(
                        "font-size:12px;color:#FFAA00;font-weight:900;font-family:Consolas;padding:0px 10px;background:#030810;border-bottom:1px solid #0E2A40;")
                    show_results()
                    retry_btn.setEnabled(True)
                    verify_btn.setEnabled(False)
                    return

                from ultralytics import YOLO

                frame = cv2.imread(new_capture_path)
                model = YOLO(model_path)
                results = model(frame, conf=0.25)
                detections = results[0]

                all_predictions = []
                if len(detections.boxes) > 0:
                    boxes = detections.boxes
                    for i in range(len(boxes)):
                        xyxy = boxes.xyxy[i].cpu().numpy() if hasattr(boxes.xyxy, 'cpu') else boxes.xyxy[i]
                        class_id_val = int(boxes.cls[i].cpu().numpy() if hasattr(boxes.cls, 'cpu') else boxes.cls[i])
                        conf_val = float(boxes.conf[i].cpu().numpy() if hasattr(boxes.conf, 'cpu') else boxes.conf[i])
                        class_name = detections.names.get(class_id_val, f"class_{class_id_val}")
                        all_predictions.append({
                            'bbox': xyxy.tolist() if hasattr(xyxy, 'tolist') else xyxy,
                            'class_id': class_id_val,
                            'class_name': class_name,
                            'confidence': conf_val
                        })

                print(f"\n🎯 TARGET PRODUCT NAME: '{product_name}'")
                print(f"📦 Detected classes: {[p['class_name'] for p in all_predictions]}")

                target_predictions = []
                other_predictions = []

                def clean_name(name: str) -> str:
                    import re
                    name = re.sub(r'^\d+_', '', name)
                    name = re.sub(r'^[A-Z0-9\.]+_', '', name)
                    return name.lower().strip()

                for pred in all_predictions:
                    pred_clean = clean_name(pred['class_name'])
                    target_clean = clean_name(product_name)

                    if pred_clean == target_clean:
                        target_predictions.append(pred)
                        print(f"   ✅ MATCH! -> target")
                    else:
                        other_predictions.append(pred)
                        print(f"   ❌ OTHER")

                best_target = None
                if target_predictions:
                    best_target = max(target_predictions, key=lambda p: p.get('confidence', 0))

                try:
                    best_bbox = best_target.get('bbox', None) if best_target else None
                    manager.set_boxes(
                        target=best_bbox,
                        others=other_predictions if best_target else None
                    )

                    if best_bbox:
                        print(f"[TARGET] {product_name} at {best_bbox}")

                    if best_target and other_predictions:
                        for obj in other_predictions:
                            print(f"[OTHER] {obj['class_name']} at {obj['bbox']}")
                except Exception as e:
                    print(f"[Orbbec] ❌ box update error: {e}")

                target_found = best_target is not None
                target_detected_successfully = target_found

                if not target_found and manager.thread is not None:
                    try:
                        manager.clear_boxes()
                    except Exception as e:
                        print(f"❌ Failed to clear Orbbec target bbox: {e}")

                annotated_frame = detections.plot()
                output_path = os.path.join(capture_folder, f"Step_{step_num}_{timestamp}_detected.jpg")
                cv2.imwrite(output_path, annotated_frame)

                if len(detections.boxes) > 0:
                    boxes = detections.boxes
                    confidences = boxes.conf.cpu().numpy() if hasattr(boxes.conf, 'cpu') else boxes.conf
                    class_counts = {}

                    if hasattr(detections, 'names') and hasattr(boxes, 'cls'):
                        cids = boxes.cls.cpu().numpy() if hasattr(boxes.cls, 'cpu') else boxes.cls
                        for cid in cids:
                            cn = detections.names.get(int(cid), f"class_{int(cid)}")
                            class_counts[cn] = class_counts.get(cn, 0) + 1

                    avg_confidence = np.mean(confidences) * 100 if len(confidences) > 0 else 0
                    detection_result.setText(f"DETECTED: {', '.join([f'{k}:{v}' for k, v in class_counts.items()])}")
                    confidence_label.setText(f"CONFIDENCE: {avg_confidence:.1f}%")
                    detection_results = {
                        'image_path': output_path,
                        'objects': class_counts,
                        'count': len(boxes),
                        'confidence': float(avg_confidence),
                        'class_id': class_id,
                        'target_found': target_found
                    }
                else:
                    detection_result.setText("DETECTED: None")
                    confidence_label.setText("CONFIDENCE: N/A")
                    detection_results = {
                        'image_path': output_path,
                        'objects': {},
                        'count': 0,
                        'confidence': 0,
                        'class_id': class_id,
                        'target_found': False
                    }

                if target_found:
                    _set_detection_header("✓  TARGET DETECTED", "#00FF88", "#031A10")
                    detection_status.setText("✓ Target class detected")
                    detection_status.setStyleSheet(
                        "font-size: 14px; color: #00FF88; font-weight: 800; font-family: Consolas; padding: 4px 10px;")

                    if predictions_for_sending:
                        coord_status_label.setText("COORDINATES: Sending.")
                        coord_status_label.setStyleSheet(
                            "font-size: 13px; color: #FFAA00; padding: 6px 10px; background-color: #1A1000; border-radius: 0px; font-weight: 800; font-family: Consolas;")
                        QApplication.processEvents()
                        success_sent = PipelineRunner.send_coordinates_to_server(predictions_for_sending, calibration)
                        if success_sent:
                            coord_status_label.setText("COORDINATES: Sent ✓")
                            coord_status_label.setStyleSheet(
                                "font-size: 13px; color: #00FF88; padding: 6px 10px; background-color: #031A10; border-radius: 0px; font-weight: 800; font-family: Consolas;")
                        else:
                            coord_status_label.setText("COORDINATES: Send failed ✕")
                            coord_status_label.setStyleSheet(
                                "font-size: 13px; color: #FF3344; padding: 6px 10px; background-color: #1A0508; border-radius: 0px; font-weight: 800; font-family: Consolas;")

                    show_results()
                    verify_btn.setEnabled(True)
                    retry_btn.setEnabled(False)
                    return

                if auto_retry_count < max_auto_retry:
                    auto_retry_count += 1
                    target_detected_successfully = False
                    _set_detection_header("↺  AUTO RETRYING", "#FFAA00", "#1A1000")
                    detection_status.setText(f"⚠ Target not found, retrying. ({auto_retry_count}/{max_auto_retry})")
                    detection_status.setStyleSheet(
                        "font-size:12px;color:#FFAA00;font-weight:900;font-family:Consolas;padding:0px 10px;background:#030810;border-bottom:1px solid #0E2A40;")
                    coord_status_label.setText("COORDINATES: Not sent")
                    coord_status_label.setStyleSheet(
                        "font-size:12px;color:#7AAAD4;padding:0px 10px;background:#030810;font-family:Consolas;")
                    QApplication.processEvents()
                    detection_label.clear()
                    verify_btn.setEnabled(False)
                    retry_btn.setEnabled(False)
                    cleanup_capture_runner()
                    start_detection_capture("↺ Auto retry.")
                    return

                _set_detection_header("✕  NO TARGET DETECTED", "#FF3344", "#1A0508")
                detection_status.setText("✕ Target not detected after auto retry")
                detection_status.setStyleSheet(
                    "font-size: 14px; color: #FF3344; font-weight: 800; font-family: Consolas; padding: 4px 10px;")
                coord_status_label.setText("COORDINATES: Not sent")
                coord_status_label.setStyleSheet(
                    "font-size: 13px; color: #FF3344; padding: 6px 10px; background-color: #1A0508; border-radius: 0px; font-weight: 800; font-family: Consolas;")
                show_results()
                verify_btn.setEnabled(False)
                retry_btn.setEnabled(True)

            except Exception as e:
                _set_detection_header("✕  DETECTION ERROR", "#FF3344", "#1A0508")
                detection_status.setText(f"✕ Error: {str(e)[:50]}")
                detection_status.setStyleSheet(
                    "font-size: 14px; color: #FF3344; font-weight: 800; font-family: Consolas; padding: 4px 10px;")
                coord_status_label.setText("COORDINATES: Not sent")
                coord_status_label.setStyleSheet(
                    "font-size: 13px; color: #FF3344; padding: 6px 10px; background-color: #1A0508; border-radius: 0px; font-weight: 800; font-family: Consolas;")
                show_results()
                verify_btn.setEnabled(False)
                retry_btn.setEnabled(True)
                import traceback
                traceback.print_exc()

        start_detection_capture()

        def on_retry_detection():
            nonlocal manual_retry_count, target_detected_successfully, auto_retry_count
            nonlocal predictions_for_sending, detection_results, output_path, captured_image_path

            cleanup_capture_runner()

            try:
                manager.clear_boxes()
                if manager.thread is not None:
                    manager.thread.trigger_was_used = False
                    manager.thread.trigger_enter_time = None
            except Exception as e:
                print(f"❌ Failed to clear Orbbec target bbox on retry: {e}")

            manual_retry_count += 1
            auto_retry_count = 0
            target_detected_successfully = False
            predictions_for_sending = []
            detection_results = output_path = captured_image_path = None

            verify_btn.setEnabled(False)
            retry_btn.setEnabled(False)

            detection_label.clear()
            start_detection_capture(f"↺ Manual retry. ({manual_retry_count})")

        def on_verify():
            print("🔍 [DEBUG] on_verify START")

            nonlocal captured_image_path, detection_results, output_path, target_detected_successfully, orbbec_thread

            if not target_detected_successfully:
                QMessageBox.warning(parent_widget, "⚠️ Target Not Detected",
                                    "Cannot continue because target class was not detected.\nPlease cancel and try again.")
                return

            if captured_image_path and os.path.exists(captured_image_path):
                selection['pipeline_capture_path'] = captured_image_path
            if output_path and os.path.exists(output_path):
                selection['pipeline_detection_path'] = output_path
            if detection_results:
                selection['pipeline_detection_results'] = detection_results

            coordinates_sent = False
            coord_string = ""
            try:
                recipe_folder_local = config_manager.get_recipe_folder(recipe_name)
                boxes_folder = os.path.join(recipe_folder_local, "BoxesData", f"Block_{block_id}")
                if os.path.exists(boxes_folder):
                    import glob
                    json_files = glob.glob(os.path.join(boxes_folder, "box_world_*.json"))
                    if json_files:
                        latest_json = max(json_files, key=os.path.getmtime)
                        with open(latest_json, 'r') as f:
                            box_data = json.load(f)
                        coord_parts = [f"{p[0]:.2f}_{p[1]:.2f}" for p in box_data if len(p) >= 2]
                        if coord_parts:
                            coord_string = ",".join(coord_parts)
                            if PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected():
                                success = PipelineRunner._heartbeat_manager.send_data(coord_string + "\n")
                                if success:
                                    coordinates_sent = True
            except Exception as e:
                print(f"❌ Error sending box coordinates: {e}")

            try:
                manager.clear_boxes()
                if manager.thread is not None:
                    manager.thread.trigger_was_used = False
                    manager.thread.trigger_enter_time = None
            except Exception as e:
                print(f"⚠️ Error resetting camera state: {e}")
            print("✅ [DEBUG] Closing main detection dialog")
            main_dialog_ref = dialog
            main_dialog_ref.accept()

            QApplication.processEvents()

            image_to_show = None
            try:
                import glob
                recipe_folder_local = config_manager.get_recipe_folder(recipe_name)
                block_capture_folder = os.path.join(recipe_folder_local, "Capture", f"Block_{block_id}")
                all_files = []
                for ext in ['bmp', 'png', 'jpg', 'jpeg']:
                    all_files.extend(glob.glob(os.path.join(block_capture_folder, f"*.{ext}")))
                if all_files:
                    image_to_show = sorted(all_files, key=os.path.getmtime, reverse=True)[0]
            except Exception:
                pass

            if image_to_show and os.path.exists(image_to_show):
                saved_image_dialog = QDialog()
                saved_image_dialog.setWindowTitle(f"Assembly Result")
                saved_image_dialog.showFullScreen()
                saved_image_dialog.setStyleSheet("QDialog { background-color: #060C14; }")

                saved_layout = QVBoxLayout(saved_image_dialog)
                saved_layout.setContentsMargins(16, 16, 16, 16)
                saved_layout.setSpacing(12)

                saved_header_widget = QWidget()
                saved_header_widget.setFixedHeight(80)
                saved_header_widget.setStyleSheet("background:#050D18;border-bottom:2px solid #00AAFF;")
                saved_header_layout = QHBoxLayout(saved_header_widget)
                saved_header_layout.setContentsMargins(14, 0, 14, 0)

                step_badge = QLabel(f"ASSEMBLY RESULT")
                step_badge.setStyleSheet("""
                    font-size: 20px; font-weight: 800; color: #FFFFFF;
                    letter-spacing: 2px; font-family: Consolas; background: transparent;
                """)

                # hand_detection_status = QLabel("✋ HAND DETECTION: WAITING")
                # hand_detection_status.setStyleSheet("""
                #     font-size: 11px; font-weight: 900; color: #FFAA00;
                #     background-color: #1A1000; border: 1px solid #FFAA0044;
                #     padding: 4px 12px; letter-spacing: 1px; font-family: Consolas;
                # """)

                saved_header_layout.addWidget(step_badge)
                saved_header_layout.addStretch()
                # saved_header_layout.addWidget(hand_detection_status)
                saved_layout.addWidget(saved_header_widget)

                has_video = uploaded_video_path and os.path.exists(uploaded_video_path)

                cached_pixmap = None
                pixmap = QPixmap(image_to_show)
                if not pixmap.isNull():
                    cached_pixmap = pixmap.scaled(700, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                if has_video:
                    splitter_result = QSplitter(Qt.Horizontal)
                    splitter_result.setHandleWidth(2)
                    splitter_result.setStyleSheet("QSplitter::handle { background-color: #1A3A5C; }")

                    left_result_widget = QWidget()
                    left_result_widget.setStyleSheet("background-color: #060C14;")
                    left_result_layout = QVBoxLayout(left_result_widget)
                    left_result_layout.setContentsMargins(8, 8, 8, 8)

                    image_title = QLabel("ASSEMBLY IMAGE")
                    image_title.setAlignment(Qt.AlignCenter)
                    image_title.setStyleSheet(
                        "font-size:10px;font-weight:900;color:#2A5A7A;background:#050D18;border-bottom:1px solid #0E2A40;padding:8px 12px;font-family:Consolas;letter-spacing:3px;")
                    left_result_layout.addWidget(image_title)

                    image_frame = QFrame()
                    image_frame.setMinimumSize(600, 500)
                    image_frame.setStyleSheet(
                        "QFrame { border: 1px solid #1A3A5C; border-left: 3px solid #00AAFF; border-radius: 0px; background-color: #030810; }")
                    image_frame_layout = QVBoxLayout(image_frame)
                    image_frame_layout.setContentsMargins(8, 8, 8, 8)

                    saved_image_label = QLabel()
                    saved_image_label.setAlignment(Qt.AlignCenter)
                    saved_image_label.setMinimumSize(560, 460)
                    saved_image_label.setStyleSheet("background-color: #030810; border: none;")
                    if cached_pixmap:
                        saved_image_label.setPixmap(cached_pixmap)
                    else:
                        saved_image_label.setText("❌ Cannot load image")
                    image_frame_layout.addWidget(saved_image_label, 1)
                    left_result_layout.addWidget(image_frame, 1)

                    right_result_widget = QWidget()
                    right_result_widget.setStyleSheet("background-color: #060C14;")
                    right_result_layout = QVBoxLayout(right_result_widget)
                    right_result_layout.setContentsMargins(8, 8, 8, 8)

                    video_title = QLabel("UPLOADED VIDEO")
                    video_title.setAlignment(Qt.AlignCenter)
                    video_title.setStyleSheet(
                        "font-size:10px;font-weight:900;color:#2A5A7A;background:#050D18;border-bottom:1px solid #0E2A40;padding:8px 12px;font-family:Consolas;letter-spacing:3px;")
                    right_result_layout.addWidget(video_title)

                    video_frame = QFrame()
                    video_frame.setMinimumSize(760, 560)
                    video_frame.setStyleSheet(
                        "QFrame { border: 1px solid #1A3A5C; border-left: 3px solid #00FF88; border-radius: 0px; background-color: #030810; }")
                    video_frame_layout = QVBoxLayout(video_frame)
                    video_frame_layout.setContentsMargins(8, 8, 8, 8)

                    video_widget = QVideoWidget()
                    video_widget.setMinimumSize(720, 520)
                    video_widget.setStyleSheet("background-color: #030810;")
                    video_info = QLabel(os.path.basename(uploaded_video_path))
                    video_info.setAlignment(Qt.AlignCenter)
                    video_info.setStyleSheet(
                        "font-size: 13px; color: #7AAAD4; padding: 6px 10px; background-color: #050D18; border-radius: 0px; font-family: Consolas;")
                    video_frame_layout.addWidget(video_widget, 1)
                    video_frame_layout.addWidget(video_info, 0)
                    right_result_layout.addWidget(video_frame, 1)

                    splitter_result.addWidget(left_result_widget)
                    splitter_result.addWidget(right_result_widget)
                    splitter_result.setSizes([620, 800])
                    saved_layout.addWidget(splitter_result, 1)

                    def load_video_deferred():
                        player = QMediaPlayer(saved_image_dialog)
                        audio = QAudioOutput(saved_image_dialog)
                        player.setAudioOutput(audio)
                        player.setVideoOutput(video_widget)
                        player.setSource(QUrl.fromLocalFile(uploaded_video_path))
                        audio.setVolume(0.0)

                        def loop_uploaded_video(status):
                            from PySide6.QtMultimedia import QMediaPlayer
                            if status == QMediaPlayer.EndOfMedia:
                                player.setPosition(0)
                                player.play()

                        player.mediaStatusChanged.connect(loop_uploaded_video)
                        player.play()
                        saved_image_dialog.video_player = player

                    QTimer.singleShot(100, load_video_deferred)

                else:
                    saved_image_label = QLabel()
                    saved_image_label.setAlignment(Qt.AlignCenter)
                    saved_image_label.setMinimumHeight(400)
                    saved_image_label.setStyleSheet(
                        "border: 1px solid #1A3A5C; border-left: 3px solid #00AAFF; border-radius: 0px; background-color: #030810; padding: 10px;")
                    if cached_pixmap:
                        saved_image_label.setPixmap(cached_pixmap)
                    else:
                        saved_image_label.setText("❌ Cannot load image")
                    saved_layout.addWidget(saved_image_label)

                if coordinates_sent:
                    coord_display = QLabel(f"COORDINATES SENT:\n{coord_string}")
                    coord_display.setStyleSheet(
                        "font-size: 13px; color: #00AAFF; padding: 10px 14px; background-color: #050D18; border: 1px solid #1A3A5C; border-left: 3px solid #00AAFF; border-radius: 0px; margin: 5px; font-family: Consolas;")
                    coord_display.setWordWrap(True)
                    saved_layout.addWidget(coord_display)

                btn_container = QWidget()
                btn_container.setFixedHeight(100)
                btn_container.setStyleSheet("background: transparent;")
                btn_layout = QHBoxLayout(btn_container)
                btn_layout.setContentsMargins(20, 10, 20, 10)

                close_btn = QPushButton("▶  CONTINUE")
                close_btn.setFixedHeight(66)
                close_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 20px; font-weight: 800;
                        background-color: #031A10; color: #00FF88;
                        border: 1px solid #0A5030; border-bottom: 5px solid #051008;
                        border-left: 3px solid #00FF88; border-radius: 2px;
                        min-width: 320px; font-family: Consolas; letter-spacing: 2px;
                    }
                    QPushButton:hover { background-color: #052A18; color: #FFFFFF; border-color: #00FF88; }
                    QPushButton:pressed { border-bottom: 2px solid #051008; padding-top: 3px; }
                """)

                # hand_instruction = QLabel("✋ PLACE HAND IN BOTTOM-RIGHT CORNER TO CONTINUE")
                # hand_instruction.setStyleSheet("""
                #     font-size: 14px; color: #FFAA00; font-weight: 800;
                #     font-family: Consolas; letter-spacing: 1px;
                #     background-color: #1A1000; border: 1px solid #FFAA0044;
                #     padding: 8px 20px; border-radius: 2px;
                # """)

                # btn_layout.addWidget(hand_instruction)
                btn_layout.addStretch()
                btn_layout.addWidget(close_btn)
                saved_layout.addWidget(btn_container)

                trigger_processed = False

                def on_result_page_hand_trigger():
                    nonlocal trigger_processed
                    if trigger_processed:
                        return
                    trigger_processed = True

                    print("[ASSEMBLY RESULT] Hand detected in trigger zone!")

                    if close_btn.isEnabled():
                        QTimer.singleShot(500, close_btn.click)

                try:
                    manager.detach_live_view(update_orbbec_view)
                except Exception:
                    pass

                try:
                    if parent_widget and hasattr(parent_widget, "ignore_orbbec_start_trigger"):
                        parent_widget.ignore_orbbec_start_trigger = True
                        print("[ASSEMBLY RESULT] MainPage start trigger temporarily disabled")
                except Exception as e:
                    print(f"[ASSEMBLY RESULT] Failed to disable MainPage start trigger: {e}")

                try:
                    manager.set_handler(on_result_page_hand_trigger)
                    print("[ASSEMBLY RESULT] ✅ Reusing camera + trigger OK")
                except Exception as e:
                    print(f"❌ Failed to reuse camera thread: {e}")

                def on_continue_clicked():
                    print("🔘 [DEBUG] CONTINUE button clicked")
                    try:
                        manager.set_handler(None)
                    except Exception:
                        pass

                    try:
                        if parent_widget and hasattr(parent_widget, "ignore_orbbec_start_trigger"):
                            parent_widget.ignore_orbbec_start_trigger = False
                            print("[ASSEMBLY RESULT] MainPage start trigger restored")
                    except Exception as e:
                        print(f"[ASSEMBLY RESULT] Failed to restore MainPage start trigger: {e}")

                    saved_image_dialog.accept()

                close_btn.clicked.connect(on_continue_clicked)

                print("📱 [DEBUG] Showing result page (reusing camera thread)")
                saved_image_dialog.exec()
                print("📱 [DEBUG] Result page exec() returned")
            else:
                print("⚠️ [DEBUG] No image found, continuing without result page")
                QMessageBox.warning(parent_widget, "⚠️ Image Not Found",
                                    f"No image found in Step {step_num}.\nCapture folder: {capture_folder}")

            print("🔍 [DEBUG] on_verify END")

        retry_btn.clicked.connect(on_retry_detection)
        verify_btn.clicked.connect(on_verify)

        def _cleanup_dialog(*_):
            try:
                manager.clear_boxes()
            except Exception:
                pass

            try:
                manager.detach_live_view(update_orbbec_view)
            except Exception:
                pass

            try:
                manager.set_handler(None)
            except Exception:
                pass

            try:
                if parent_widget and hasattr(parent_widget, "ignore_orbbec_start_trigger"):
                    parent_widget.ignore_orbbec_start_trigger = False
                    print("[ASSEMBLY RESULT] MainPage start trigger restored in cleanup")
            except Exception as e:
                print(f"[ASSEMBLY RESULT] Cleanup restore failed: {e}")

        dialog.finished.connect(_cleanup_dialog)

        try:
            result = dialog.exec()
            if PipelineRunner._heartbeat_manager is not None:
                PipelineRunner._heartbeat_reference_count -= 1
            return result == QDialog.Accepted
        except Exception as e:
            if PipelineRunner._heartbeat_manager is not None:
                PipelineRunner._heartbeat_reference_count -= 1
            raise e
        finally:
            if loading_timer.isActive():
                loading_timer.stop()
            cleanup_capture_runner()

    @staticmethod
    def _notify_main_page_refresh_mes(parent_widget, force=False):
        try:
            if not parent_widget: return
            if force:
                if hasattr(parent_widget, "fetch_mes_recipe_once"):
                    parent_widget.fetch_mes_recipe_once(force=True)
                    return
            if hasattr(parent_widget, "try_fetch_mes_recipe"):
                parent_widget.try_fetch_mes_recipe()
            elif hasattr(parent_widget, "fetch_mes_recipe_once"):
                parent_widget.fetch_mes_recipe_once()
        except Exception as e:
            print(f"⚠️ Failed to notify MainPage to refresh MES: {e}")

    @staticmethod
    def send_recipe_to_screw_server(recipe_name: str) -> bool:
        try:
            server = config_manager.config_data.get('tcp_screw', {}).get('server', '127.0.0.1')
            port = config_manager.config_data.get('tcp_screw', {}).get('port', 5001)

            # Check if already connected
            if PipelineRunner._screw_socket is None:
                print(f"📤 Creating persistent connection to {server}:{port}")
                PipelineRunner._screw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                PipelineRunner._screw_socket.settimeout(5)
                PipelineRunner._screw_socket.connect((server, port))
                PipelineRunner._screw_connected = True
                print(f"✅ Persistent connection established (will stay open)")

            # Send data (connection stays open)
            message = recipe_name + "\n"
            PipelineRunner._screw_socket.sendall(message.encode('utf-8'))
            print(f"✅ Recipe name sent: {recipe_name}")
            return True

        except Exception as e:
            print(f"❌ Failed to send: {e}")
            # Mark as disconnected on error
            PipelineRunner._screw_connected = False
            PipelineRunner._screw_socket = None
            return False

    @staticmethod
    def close_screw_connection():
        """Close the persistent connection (call on app exit)"""
        if PipelineRunner._screw_socket is not None:
            try:
                PipelineRunner._screw_socket.close()
                print(f"✅ Screw server connection closed")
            except Exception as e:
                print(f"⚠️ Error closing: {e}")
            finally:
                PipelineRunner._screw_socket = None
                PipelineRunner._screw_connected = False

    @staticmethod
    def send_screw_start_to_server() -> bool:
        """Send 'screw_start' command to TCP screw server on port 5001"""
        try:
            server = config_manager.config_data.get('tcp_screw', {}).get('server', '127.0.0.1')
            port = config_manager.config_data.get('tcp_screw', {}).get('port', 5001)

            # Check if already connected
            if PipelineRunner._screw_socket is None:
                print(f"📤 Creating persistent connection to {server}:{port}")
                PipelineRunner._screw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                PipelineRunner._screw_socket.settimeout(5)
                PipelineRunner._screw_socket.connect((server, port))
                PipelineRunner._screw_connected = True
                print(f"✅ Persistent connection established")

            # Send screw_start command
            PipelineRunner._screw_socket.sendall(b"screw_start\n")
            print(f"✅ Screw start command sent")
            return True

        except Exception as e:
            print(f"❌ Failed to send screw start: {e}")
            PipelineRunner._screw_socket = None
            return False

    @staticmethod
    def send_screw_stop_to_server() -> bool:
        """Send 'screw_stop' command to TCP screw server on port 5001"""
        try:
            server = config_manager.config_data.get('tcp_screw', {}).get('server', '127.0.0.1')
            port = config_manager.config_data.get('tcp_screw', {}).get('port', 5001)

            # Check if already connected
            if PipelineRunner._screw_socket is None:
                print(f"📤 Creating persistent connection to {server}:{port}")
                PipelineRunner._screw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                PipelineRunner._screw_socket.settimeout(5)
                PipelineRunner._screw_socket.connect((server, port))
                PipelineRunner._screw_connected = True
                print(f"✅ Persistent connection established")

            # Send screw_stop command
            PipelineRunner._screw_socket.sendall(b"screw_stop\n")
            print(f"✅ Screw stop command sent")
            return True

        except Exception as e:
            print(f"❌ Failed to send screw stop: {e}")
            PipelineRunner._screw_socket = None
            return False
