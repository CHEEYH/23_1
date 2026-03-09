# ui/components/pipeline_runner.py

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from ui.components.mes_client import MESClient  # Add this import

from PySide6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QLabel, QPushButton,
    QFrame, QHBoxLayout, QGridLayout, QSplitter, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from ui.components.heartbeat_manager import HeartbeatManager
from ui.components.dialogs import Calibration  # Import the Calibration class
from config_manager import config_manager

# Try to import camera module
CAMERA_AVAILABLE = False
try:
    from camera.camera import AutoCaptureFlow

    CAMERA_AVAILABLE = True
except ImportError:
    print("WARNING: Camera module not available")


class PipelineRunner:
    """
    Shared pipeline execution module that can be used from any page.
    Contains all pipeline logic without UI dependencies.
    Supports operator mode with intelligent skipping.
    """
    _api_client = None
    # Add class-level heartbeat manager (shared across all pipeline runs)
    _heartbeat_manager = None
    _heartbeat_reference_count = 0
    _calibration = None  # Add calibration

    @staticmethod
    def init_api_client():
        """Initialize the MES API client from config"""
        try:
            # Try to get from config_manager
            base_url = config_manager.get_mes_api_url()
            timeout = config_manager.get_mes_api_timeout()

            print(f"🔌 Initializing MES API client with URL: {base_url}")

            # Import MESClient here to avoid circular imports
            from ui.components.mes_client import MESClient

            PipelineRunner._api_client = MESClient(base_url)
            PipelineRunner._api_client.timeout = timeout

            print(f"✅ MES API client initialized")

            # Test connection (don't fail if it doesn't work)
            try:
                if PipelineRunner._api_client.test_connection():
                    print(f"   Successfully connected to MES API")
                    inventory = PipelineRunner._api_client.get_all_inventory()
                    print(f"   Current inventory: {inventory}")
                else:
                    print(f"   ⚠️ Could not connect to MES API at {base_url}")
                    print(f"   Will continue with simulated inventory (all parts available)")
            except Exception as e:
                print(f"   ⚠️ Connection test failed: {e}")
                print(f"   Will continue with simulated inventory (all parts available)")

            return PipelineRunner._api_client

        except Exception as e:
            print(f"❌ Failed to initialize API client: {e}")
            import traceback
            traceback.print_exc()
            PipelineRunner._api_client = None
            print(f"   ⚠️ Continuing without MES API - all parts will be considered available")
            return None
    @staticmethod
    def _init_heartbeat_manager():
        """Initialize or reference the shared heartbeat manager"""
        if PipelineRunner._heartbeat_manager is None:
            PipelineRunner._heartbeat_manager = HeartbeatManager()
            # Optional: Add signal handlers if needed
            # PipelineRunner._heartbeat_manager.connection_status_changed.connect(...)
            # PipelineRunner._heartbeat_manager.heartbeat_sent.connect(...)

        PipelineRunner._heartbeat_reference_count += 1
        print(f"🔌 Heartbeat manager reference count: {PipelineRunner._heartbeat_reference_count}")

        # Try to connect if not already connected
        PipelineRunner._ensure_heartbeat_connected()

    @staticmethod
    def _ensure_heartbeat_connected():
        """Ensure heartbeat manager is connected"""
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
        """Get server IP address from config or return default"""
        try:
            if hasattr(config_manager, 'get_tcp_server'):
                return config_manager.get_tcp_server()
        except:
            pass
        return "127.0.0.1"  # Default

    @staticmethod
    def _get_server_port():
        """Get server port from config or return default"""
        try:
            if hasattr(config_manager, 'get_tcp_port'):
                return config_manager.get_tcp_port()
        except:
            pass
        return 8888  # Default

    @staticmethod
    def _load_calibration(recipe_name: str = None):
        if PipelineRunner._calibration is None:
            PipelineRunner._calibration = Calibration()

            # Use the fixed path from AssemblyDialog
            calibration_path = "C:\\Users\\PC_AI_DS\\Pictures\\LaserCalibration\\calibration.json"

            if os.path.exists(calibration_path):
                success, message = PipelineRunner._calibration.load_calibration(calibration_path)
                if success:
                    print(f"✅ PipelineRunner loaded calibration from: {calibration_path}")
                    print(f"   Calibration matrix: {PipelineRunner._calibration.calibration_matrix}")
                    print(f"   Pixel points: {len(PipelineRunner._calibration.pixel_points)}")
                    print(f"   World points: {len(PipelineRunner._calibration.world_points)}")
                else:
                    print(f"⚠️ PipelineRunner failed to load calibration: {message}")
                    # Create empty calibration object
                    PipelineRunner._calibration = Calibration()
            else:
                print(f"⚠️ Calibration file not found at: {calibration_path}")
                print(f"   Using pixel coordinates instead of world coordinates")
                # Create empty calibration object
                PipelineRunner._calibration = Calibration()

        return PipelineRunner._calibration

    @staticmethod
    def verify_calibration():
        """Verify calibration is loaded correctly"""
        calibration = PipelineRunner._load_calibration()

        if calibration and calibration.is_calibrated:
            print("\n" + "=" * 50)
            print("✅ CALIBRATION VERIFICATION")
            print("=" * 50)
            print(f"Calibration matrix:")
            print(calibration.calibration_matrix)
            print(f"\nPixel points: {len(calibration.pixel_points)}")
            print(f"World points: {len(calibration.world_points)}")

            # Test conversion of a sample point
            if calibration.pixel_points:
                test_pixel = calibration.pixel_points[0]
                test_world = calibration.pixel_to_world(test_pixel)
                print(f"\nSample conversion:")
                print(f"  Pixel: ({test_pixel[0]:.1f}, {test_pixel[1]:.1f})")
                print(f"  World: ({test_world[0]:.2f}, {test_world[1]:.2f})")
            print("=" * 50)
            return True
        else:
            print("\n" + "=" * 50)
            print("❌ CALIBRATION NOT LOADED")
            print("=" * 50)
            print("Using pixel coordinates instead of world coordinates")
            print("=" * 50)
            return False

    @staticmethod
    def _convert_to_world_coordinates(calibration, pixel_corners):
        """Helper method to convert pixel corners to world coordinates"""
        world_corners = []

        if not calibration or not calibration.is_calibrated:
            print(f"⚠️ Calibration not available, returning pixel coordinates")
            return pixel_corners

        for corner in pixel_corners:
            try:
                world_point = calibration.pixel_to_world(corner)
                if world_point:
                    world_corners.append(world_point)
                else:
                    print(f"⚠️ Failed to convert point {corner}, using pixel coordinates")
                    world_corners.append(corner)  # Fallback to pixel
            except Exception as e:
                print(f"⚠️ Error converting point {corner}: {e}")
                world_corners.append(corner)  # Fallback to pixel

        return world_corners

    # In pipeline_runner.py, replace the send_coordinates_to_server method:

    @staticmethod
    def send_coordinates_to_server(predictions, calibration=None):
        """Send ONLY the highest confidence object coordinates to server using heartbeat manager"""
        if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
            print("⚠️ Heartbeat manager not connected - attempting to reconnect...")
            PipelineRunner._ensure_heartbeat_connected()

            if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
                return False

        try:
            if not predictions:
                print("⚠️ No predictions to send")
                return False

            # Find the prediction with highest confidence
            # If confidence scores are tied, max() will return the first one encountered
            best_prediction = max(predictions, key=lambda p: p.get('confidence', 0))

            print(f"\n{'=' * 50}")
            print(f"🎯 Selected BEST object for transmission:")
            print(f"   Class: {best_prediction.get('class_name', 'unknown')}")
            print(f"   Class ID: {best_prediction.get('class_id', 'N/A')}")
            print(f"   Confidence: {best_prediction.get('confidence', 0):.3f}")
            print(f"{'=' * 50}")

            # Build coordinate string for the best object only
            bbox = best_prediction.get('bbox', [0, 0, 0, 0])
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox[:4]

                # Debug calibration status
                if calibration and calibration.is_calibrated:
                    print(f"📐 Using WORLD coordinates for best object")
                    print(f"   Calibration matrix: {calibration.calibration_matrix}")
                else:
                    print(f"📷 Using PIXEL coordinates for best object")

                # Convert based on calibration
                if calibration and calibration.is_calibrated:
                    # Convert to world coordinates
                    pixel_corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                    world_corners = PipelineRunner._convert_to_world_coordinates(
                        calibration,
                        pixel_corners
                    )

                    # Format with 2 decimal places
                    coord_line = (f"{world_corners[0][0]:.2f}_{world_corners[0][1]:.2f},"
                                  f"{world_corners[1][0]:.2f}_{world_corners[1][1]:.2f},"
                                  f"{world_corners[2][0]:.2f}_{world_corners[2][1]:.2f},"
                                  f"{world_corners[3][0]:.2f}_{world_corners[3][1]:.2f}")

                    # Debug conversion
                    print(
                        f"   Pixel: ({x1:.1f}, {y1:.1f}) -> World: ({world_corners[0][0]:.2f}, {world_corners[0][1]:.2f})")
                    print(
                        f"   Pixel: ({x2:.1f}, {y1:.1f}) -> World: ({world_corners[1][0]:.2f}, {world_corners[1][1]:.2f})")
                    print(
                        f"   Pixel: ({x2:.1f}, {y2:.1f}) -> World: ({world_corners[2][0]:.2f}, {world_corners[2][1]:.2f})")
                    print(
                        f"   Pixel: ({x1:.1f}, {y2:.1f}) -> World: ({world_corners[3][0]:.2f}, {world_corners[3][1]:.2f})")
                else:
                    # Send pixel coordinates
                    coord_line = (f"{x1:.2f}_{y1:.2f},"
                                  f"{x2:.2f}_{y1:.2f},"
                                  f"{x2:.2f}_{y2:.2f},"
                                  f"{x1:.2f}_{y2:.2f}")

                    print(
                        f"   Pixel coordinates: ({x1:.1f}, {y1:.1f}), ({x2:.1f}, {y1:.1f}), ({x2:.1f}, {y2:.1f}), ({x1:.1f}, {y2:.1f})")

                # Send using heartbeat manager
                message = coord_line + "\n"

                # Debug full message
                print(f"📤 Sending BEST object coordinates:\n{coord_line}")
                print(f"   Confidence: {best_prediction.get('confidence', 0):.3f}")
                print(f"   Class: {best_prediction.get('class_name', 'unknown')}")

                success = PipelineRunner._heartbeat_manager.send_data(message)

                if success:
                    print(f"✅ Sent best object coordinates via heartbeat")
                    print(f"{'=' * 50}\n")
                    return True
                else:
                    print("❌ Failed to send coordinates")
                    print(f"{'=' * 50}\n")
                    return False
            else:
                print("❌ Invalid bounding box format")
                return False

        except Exception as e:
            print(f"❌ Error sending coordinates from PipelineRunner: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def _send_latest_coordinates_from_folder(recipe_name: str, folder_name: str, block_id: str) -> tuple[bool, str]:
        """
        Read latest JSON coordinate file from:
            recipes/<recipe_name>/<folder_name>/Block_<block_id>
        and send it through heartbeat TCP.

        Returns:
            (success, coord_string)
        """
        try:
            if not recipe_name:
                print("⚠️ No recipe name provided for coordinate sending")
                return False, ""

            recipe_folder = config_manager.get_recipe_folder(recipe_name)
            if not recipe_folder:
                print(f"⚠️ Recipe folder not found for: {recipe_name}")
                return False, ""

            target_folder = os.path.join(recipe_folder, folder_name, f"Block_{block_id}")
            print(f"🔍 Looking for coordinates in: {target_folder}")

            if not os.path.exists(target_folder):
                print(f"⚠️ Folder does not exist: {target_folder}")
                return False, ""

            import glob
            json_files = glob.glob(os.path.join(target_folder, "*.json"))
            if not json_files:
                print(f"⚠️ No JSON files found in: {target_folder}")
                return False, ""

            latest_json = max(json_files, key=os.path.getmtime)
            print(f"📂 Using latest coordinate file: {latest_json}")

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
                print(f"⚠️ No valid coordinates parsed from: {latest_json}")
                return False, ""

            # Ensure heartbeat connected
            if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
                print("⚠️ Heartbeat not connected, attempting reconnect...")
                PipelineRunner._ensure_heartbeat_connected()

            if not PipelineRunner._heartbeat_manager or not PipelineRunner._heartbeat_manager.is_connected():
                print("❌ Heartbeat still not connected")
                return False, coord_string

            success = PipelineRunner._heartbeat_manager.send_data(coord_string + "\n")
            if success:
                print(f"✅ Sent coordinates from {folder_name}/Block_{block_id}: {coord_string}")
                return True, coord_string
            else:
                print(f"❌ Failed to send coordinates from {folder_name}/Block_{block_id}")
                return False, coord_string

        except Exception as e:
            print(f"❌ Error sending coordinates from {folder_name}/Block_{block_id}: {e}")
            import traceback
            traceback.print_exc()
            return False, ""

    @staticmethod
    def _show_video_dialog(video_path: str, parent_widget=None, title: str = "Video") -> bool:
        """Show fullscreen video dialog and wait until operator closes it."""
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget

            dialog = QDialog(parent_widget)
            dialog.setWindowTitle(title)
            dialog.showFullScreen()

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)

            header = QLabel("🎬 Screw Operation Video")
            header.setStyleSheet("""
                QLabel {
                    font-size: 20px;
                    font-weight: bold;
                    color: white;
                    background-color: #3498db;
                    padding: 15px;
                    border-radius: 8px;
                }
            """)
            header.setAlignment(Qt.AlignCenter)
            layout.addWidget(header)

            if not os.path.exists(video_path):
                error_label = QLabel(f"❌ Video not found:\n{video_path}")
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("""
                    QLabel {
                        font-size: 16px;
                        color: #e74c3c;
                        background-color: #ffebee;
                        padding: 20px;
                        border-radius: 8px;
                    }
                """)
                layout.addWidget(error_label)

                close_btn = QPushButton("Close")
                close_btn.clicked.connect(dialog.accept)
                layout.addWidget(close_btn, alignment=Qt.AlignCenter)
                return dialog.exec() == QDialog.Accepted

            video_widget = QVideoWidget()
            video_widget.setStyleSheet("background-color: black; border-radius: 8px;")
            layout.addWidget(video_widget, stretch=1)

            close_btn = QPushButton("✅ Close Video & Continue")
            close_btn.setStyleSheet("""
                QPushButton {
                    font-size: 16px;
                    padding: 12px 24px;
                    background-color: #2ecc71;
                    color: white;
                    border-radius: 8px;
                    font-weight: bold;
                    min-width: 220px;
                }
                QPushButton:hover {
                    background-color: #27ae60;
                }
            """)
            layout.addWidget(close_btn, alignment=Qt.AlignCenter)

            player = QMediaPlayer(dialog)
            audio = QAudioOutput(dialog)
            player.setAudioOutput(audio)
            player.setVideoOutput(video_widget)
            player.setSource(QUrl.fromLocalFile(video_path))
            audio.setVolume(1.0)
            player.play()

            def close_video():
                player.stop()
                dialog.accept()

            close_btn.clicked.connect(close_video)
            dialog.finished.connect(lambda _: player.stop())

            return dialog.exec() == QDialog.Accepted

        except Exception as e:
            print(f"❌ Error showing video dialog: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(parent_widget, "Video Error", f"Cannot play video:\n{str(e)}")
            return False

    @staticmethod
    def continue_skipped_steps(recipe_name: str, job_data: Dict, parent_widget,
                               pending_callback=None) -> bool:
        """
        Continue only the skipped steps from a previous job.
        If parts still missing, keep the same skipped entry (no duplicates).
        Now uses MES API for inventory and preserves MES job ID.
        """

        # ===== INITIALIZE API CLIENT =====
        if PipelineRunner._api_client is None:
            PipelineRunner.init_api_client()

        # ===== INITIALIZE HEARTBEAT MANAGER AND CALIBRATION =====
        PipelineRunner._init_heartbeat_manager()
        calibration = PipelineRunner._load_calibration(recipe_name)

        # Show connection status
        if PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected():
            print(
                f"✅ Continuing job with TCP heartbeat to {PipelineRunner._get_server_address()}:{PipelineRunner._get_server_port()}")
            if calibration and calibration.is_calibrated:
                print(f"📐 Using WORLD coordinates (calibration loaded)")
            else:
                print(f"📷 Using PIXEL coordinates (no calibration)")

        # Display job info being continued
        print(f"🔄 Continuing job: {job_data.get('job_id', 'Unknown')}")
        if job_data.get('mes_job_details'):
            print(f"📋 MES Job Details: {job_data.get('mes_job_details')}")

        try:
            # Set current recipe
            config_manager.set_current_recipe(recipe_name)

            # 1. Load pipeline
            flow_data = PipelineRunner.get_pipeline_from_file(recipe_name)
            if not flow_data:
                QMessageBox.warning(
                    parent_widget,
                    "⚠️ No Pipeline Found",
                    f"Recipe '{recipe_name}' has no saved pipeline"
                )
                return False

            # 2. Get execution order
            execution_order = PipelineRunner.get_execution_order(flow_data)
            if not execution_order:
                QMessageBox.warning(
                    parent_widget,
                    "⚠️ Empty Pipeline",
                    "Pipeline has no executable blocks"
                )
                return False

            # 3. Get skipped steps from job data
            skipped_steps_info = []
            for s in job_data.get('skipped_steps', []):
                if isinstance(s, dict):
                    skipped_steps_info.append(s)

            if not skipped_steps_info:
                QMessageBox.information(
                    parent_widget,
                    "No Skipped Steps",
                    "This job has no skipped steps to continue."
                )
                return True

            # 4. Create updated job record - PRESERVE ORIGINAL JOB ID AND MES DATA
            updated_job = job_data.copy()  # This preserves job_id and mes_job_details
            updated_job['continue_time'] = datetime.now().isoformat()
            updated_job[
                'tcp_connected'] = PipelineRunner._heartbeat_manager.is_connected() if PipelineRunner._heartbeat_manager else False
            updated_job['calibration_loaded'] = calibration.is_calibrated if calibration else False

            # Optional: Refresh MES details if needed (uncomment if you want fresh data)
            # if PipelineRunner._api_client:
            #     try:
            #         fresh_details = PipelineRunner._api_client.get_job_details()
            #         if fresh_details:
            #             updated_job['mes_job_details'] = fresh_details
            #             # Update job_id if title changed (unlikely but possible)
            #             if fresh_details.get('title'):
            #                 updated_job['job_id'] = fresh_details['title']
            #                 updated_job['job_title'] = fresh_details['title']
            #             if fresh_details.get('product_code'):
            #                 updated_job['product_code'] = fresh_details['product_code']
            #     except Exception as e:
            #         print(f"⚠️ Could not refresh MES details: {e}")

            # Keep existing completed steps
            completed_steps = job_data.get('completed_steps', []).copy()

            # 🔥 IMPORTANT: Create a new list for skipped steps that will remain
            # Start with empty, we'll add back only steps that are still skipped
            remaining_skipped_steps = []

            # Track which steps we successfully completed
            steps_completed_now = []

            # 5. Execute only the skipped steps
            total_skipped = len(skipped_steps_info)
            for idx, skip_info in enumerate(skipped_steps_info):
                step_num = skip_info.get('step')
                if step_num > len(execution_order):
                    # Keep invalid steps? Probably not
                    continue

                block_data = execution_order[step_num - 1]
                block_name = block_data.get('name', 'Unknown')

                print(f"DEBUG: Attempting skipped step {step_num}/{total_skipped}: {block_name}")

                # Check TCP connection status periodically
                if idx % 3 == 0:  # Every 3 steps
                    if PipelineRunner._heartbeat_manager and not PipelineRunner._heartbeat_manager.is_connected():
                        print("⚠️ TCP heartbeat disconnected - attempting to reconnect...")
                        PipelineRunner._ensure_heartbeat_connected()

                if block_name == "Assembly":
                    # Execute assembly block with operator mode
                    result, info = PipelineRunner._execute_assembly_block_operator(
                        block_data, step_num, len(execution_order),
                        parent_widget
                    )

                    if result == "completed":
                        # Step completed - add to completed steps
                        if step_num not in completed_steps:
                            completed_steps.append(step_num)
                        steps_completed_now.append(step_num)
                        print(f"DEBUG: Step {step_num} completed successfully")
                        # ✅ Do NOT add back to skipped steps

                    elif result == "skipped":
                        # Step still skipped - KEEP the original skipped entry
                        print(f"DEBUG: Step {step_num} still skipped - keeping original entry")
                        remaining_skipped_steps.append(skip_info)  # Keep original

                        # Show status update
                        tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and
                                                       PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"
                        QMessageBox.information(
                            parent_widget,
                            "⏭ Step Still Skipped",
                            f"Step {step_num} still cannot be completed.\n\n"
                            f"Missing parts: {', '.join(info.get('missing_parts', []))}\n\n"
                            f"This step will remain in skipped list.\n"
                            f"📡 TCP: {tcp_status}"
                        )

                    elif result == "waiting":
                        # User chose to wait - keep in waiting
                        if 'waiting_steps' not in updated_job:
                            updated_job['waiting_steps'] = []
                        updated_job['waiting_steps'].append({
                            'step': step_num,
                            'waiting_for': info.get('missing_parts', [])
                        })

                        # Show waiting message
                        tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and
                                                       PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"
                        QMessageBox.information(
                            parent_widget,
                            "⏳ Waiting for Parts",
                            f"Waiting for parts to continue Step {step_num}.\n\n"
                            f"Missing parts: {', '.join(info.get('missing_parts', []))}\n"
                            f"📡 TCP: {tcp_status}"
                        )
                        break
                    else:  # cancelled
                        print(f"DEBUG: Continue cancelled at step {step_num}")
                        return False

                elif block_name == "Screw":
                    success = PipelineRunner._execute_screw_block(
                        block_data, step_num, len(execution_order), parent_widget
                    )
                    if success:
                        if step_num not in completed_steps:
                            completed_steps.append(step_num)
                        steps_completed_now.append(step_num)
                        # ✅ Do NOT add back to skipped
                    else:
                        return False

                elif block_name == "Camera":
                    try:
                        from ui.components.block_functions import open_realsense_camera
                        open_realsense_camera()
                        if step_num not in completed_steps:
                            completed_steps.append(step_num)
                        steps_completed_now.append(step_num)
                        # ✅ Do NOT add back to skipped
                    except Exception as e:
                        print(f"DEBUG: Camera error: {e}")
                        reply = QMessageBox.question(
                            parent_widget,
                            "Camera Error",
                            f"Cannot open camera: {str(e)}\n\nSkip this step and continue?",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if reply == QMessageBox.Yes:
                            # Keep in skipped
                            remaining_skipped_steps.append(skip_info)
                        else:
                            return False

            # 6. Update the job with new lists
            updated_job['completed_steps'] = completed_steps
            updated_job['skipped_steps'] = remaining_skipped_steps  # Only steps still skipped

            # Remove any waiting_steps that might have been completed
            if 'waiting_steps' in updated_job:
                updated_job['waiting_steps'] = [
                    w for w in updated_job['waiting_steps']
                    if w.get('step') not in steps_completed_now
                ]

            # 7. Update status
            updated_job['end_time'] = datetime.now().isoformat()
            total_steps = updated_job.get('total_steps', len(execution_order))

            print(f"DEBUG: completed_steps: {completed_steps}")
            print(f"DEBUG: remaining skipped_steps: {[s.get('step') for s in remaining_skipped_steps]}")
            print(f"DEBUG: total_steps: {total_steps}")

            # Determine final status
            if len(completed_steps) >= total_steps:
                updated_job['status'] = 'complete'
                print(f"DEBUG: Job completed!")
            elif remaining_skipped_steps:
                updated_job['status'] = 'partial'
                print(f"DEBUG: Job still partial - {len(remaining_skipped_steps)} steps skipped")
            elif updated_job.get('waiting_steps'):
                updated_job['status'] = 'waiting'
            else:
                updated_job['status'] = 'complete'

            # 8. Save pending job (this will replace the old one)
            if pending_callback:
                PipelineRunner.save_pending_job(recipe_name, updated_job)

            # 9. Show result message with TCP status and MES info
            tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and
                                           PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"
            cal_status = "World Coordinates" if (calibration and calibration.is_calibrated) else "Pixel Coordinates"

            # Include MES job info in message
            mes_info = ""
            if updated_job.get('mes_job_details'):
                job_title = updated_job.get('work_order') or updated_job.get('mes_job_details', {}).get('workOrder', 'Unknown')
                product_code = updated_job.get('product_code') or updated_job.get('mes_job_details', {}).get(
                    'product_code')
                mes_info = f"\n📋 MES Job: {job_title}"
                if product_code:
                    mes_info += f"\n📦 Product: {product_code}"

            if updated_job['status'] == 'complete':
                completed_now_text = f"Completed now: Step {', '.join(map(str, steps_completed_now))}" if steps_completed_now else ""
                QMessageBox.information(
                    parent_widget,
                    "✅ Job Completed!",
                    f"All steps completed successfully!\n\n"
                    f"Job ID: {updated_job.get('job_id', 'Unknown')}{mes_info}\n"
                    f"{completed_now_text}\n"
                    f"Total steps: {total_steps}\n\n"
                    f"📡 TCP: {tcp_status}\n"
                    f"📐 Calibration: {cal_status}"
                )

                PipelineRunner._notify_main_page_refresh_mes(parent_widget)
            else:
                skipped_count = len(updated_job.get('skipped_steps', []))
                waiting_count = len(updated_job.get('waiting_steps', []))
                QMessageBox.information(
                    parent_widget,
                    "⏳ Partial",
                    f"Some steps still pending:\n\n"
                    f"Job ID: {updated_job.get('job_id', 'Unknown')}{mes_info}\n"
                    f"Completed: {len(completed_steps)}/{total_steps}\n"
                    f"Skipped: {skipped_count}\n"
                    f"Waiting: {waiting_count}\n\n"
                    f"Completed now: Step {', '.join(map(str, steps_completed_now))}\n\n"
                    f"📡 TCP: {tcp_status}\n"
                    f"📐 Calibration: {cal_status}\n\n"
                    f"Job saved for later continuation."
                )

            return updated_job['status'] == 'complete'

        except Exception as e:
            print(f"❌ Error in continue_skipped_steps: {e}")
            import traceback
            traceback.print_exc()

            # Show error message with TCP status
            tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and
                                           PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"

            QMessageBox.critical(
                parent_widget,
                "❌ Continuation Error",
                f"Error during job continuation:\n\n{str(e)}\n\n"
                f"📡 TCP: {tcp_status}"
            )
            return False

        finally:
            # ===== CLEAN UP HEARTBEAT MANAGER =====
            PipelineRunner.cleanup()
            print("🔌 Pipeline heartbeat manager cleaned up after continuation")

    # ================== Basic Pipeline Operations ==================

    @staticmethod
    def get_pipeline_from_file(recipe_name: str) -> Optional[Dict]:
        """Load pipeline from saved file for a specific recipe."""
        if not recipe_name or recipe_name == "-- Select Recipe --" or recipe_name == "-- Select Production Task --":
            return None

        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            print(f"DEBUG: Recipe folder not found for {recipe_name}")
            return None

        flows_folder = os.path.join(recipe_folder, "flows")
        flow_file = os.path.join(flows_folder, "pipeline_flow.json")

        if not os.path.exists(flow_file):
            print(f"DEBUG: Flow file not found: {flow_file}")
            return None

        try:
            with open(flow_file, 'r', encoding='utf-8') as f:
                flow_data = json.load(f)

            print(f"DEBUG: Loaded pipeline for {recipe_name}")
            return flow_data

        except Exception as e:
            print(f"ERROR: Failed to load pipeline: {str(e)}")
            return None

    @staticmethod
    def get_execution_order(flow_data: Dict) -> List[Dict]:
        """
        Get execution order from flow data.
        Similar to EditFlowPage.get_execution_order but works with dicts.
        """
        if not flow_data or 'blocks' not in flow_data:
            return []

        blocks = flow_data['blocks']
        connections = flow_data.get('connections', [])

        if not blocks:
            return []

        # Build adjacency list
        incoming = {i: [] for i in range(len(blocks))}
        outgoing = {i: [] for i in range(len(blocks))}

        for conn in connections:
            from_idx = conn.get('from_block')
            to_idx = conn.get('to_block')
            if from_idx is not None and to_idx is not None:
                if from_idx in outgoing and to_idx in incoming:
                    outgoing[from_idx].append(to_idx)
                    incoming[to_idx].append(from_idx)

        # Find start blocks (blocks without input connections)
        start_blocks = [i for i in range(len(blocks)) if len(incoming[i]) == 0]

        # Perform topological sort (DFS)
        execution_order = []
        visited = set()

        def dfs(idx):
            if idx in visited:
                return
            visited.add(idx)

            # Add current block
            execution_order.append(blocks[idx])

            # Visit all outgoing connections
            for next_idx in outgoing[idx]:
                dfs(next_idx)

        # Start DFS from each start block
        for start_idx in start_blocks:
            dfs(start_idx)

        # Add any unconnected blocks (fallback to Y position sorting)
        for i in range(len(blocks)):
            if i not in visited:
                execution_order.append(blocks[i])

        # Sort by Y position if no connections
        if not connections and len(execution_order) > 1:
            execution_order.sort(key=lambda b: b.get('y', 0))

        print(f"DEBUG: Execution order determined: {[b.get('name') for b in execution_order]}")
        return execution_order

    @staticmethod
    def validate_pipeline(flow_data: Dict, recipe_name: str) -> Tuple[bool, str]:
        """Validate pipeline before execution."""
        if not flow_data:
            return False, "No pipeline data found"

        if not flow_data.get('blocks'):
            return False, "Pipeline has no blocks"

        # Check for End block
        blocks = flow_data.get('blocks', [])
        has_end_block = any(block.get('name') == 'End' for block in blocks)

        if not has_end_block:
            return True, "Pipeline has no End block (will run all blocks)"

        return True, "Pipeline validated successfully"

    @staticmethod
    def get_pipeline_summary(recipe_name: str) -> Dict:
        """Get summary of pipeline for display."""
        flow_data = PipelineRunner.get_pipeline_from_file(recipe_name)
        if not flow_data:
            return {"error": "No pipeline found"}

        blocks = flow_data.get('blocks', [])
        connections = flow_data.get('connections', [])

        # Count block types
        block_counts = {}
        for block in blocks:
            name = block.get('name', 'Unknown')
            block_counts[name] = block_counts.get(name, 0) + 1

        # Get execution order
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

    # ================== Standard Pipeline Execution ==================

    @staticmethod
    def run_pipeline(recipe_name, parent_widget=None, execution_order=None):
        """Run pipeline with explicit execution order"""
        if execution_order is None:
            # If no order provided, try to get from parent
            if hasattr(parent_widget, 'get_execution_order'):
                execution_order = parent_widget.get_execution_order()
            else:
                print("❌ No execution order provided and cannot determine order")
                return False

        if not execution_order:
            print("❌ No blocks to execute")
            return False

        print(f"\n{'=' * 60}")
        print(f"🚀 Starting Pipeline Execution: {recipe_name}")
        print(f"📋 Execution Order: {len(execution_order)} blocks")
        print(f"{'=' * 60}")

        # Execute blocks in order
        for i, block in enumerate(execution_order):
            step_number = i + 1
            total_blocks = len(execution_order)

            print(f"\n▶ Step {step_number}/{total_blocks}: {block.name}")

            # Execute based on block type
            if block.name == "Assembly":
                if hasattr(parent_widget, 'execute_assembly_block'):
                    parent_widget.execute_assembly_block(block, step_number, total_blocks)
            elif block.name == "Screw":
                if hasattr(parent_widget, 'execute_screw_block'):
                    parent_widget.execute_screw_block(block, step_number, total_blocks)
            elif block.name == "Camera":
                if block.action:
                    block.action()
            elif block.name == "End":
                if block.action:
                    block.action()
            else:
                print(f"⚠️ Unknown block type: {block.name}")

        print(f"\n{'=' * 60}")
        print(f"✅ Pipeline Execution Complete")
        print(f"{'=' * 60}")

        return True

    @staticmethod
    def execute_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        """Execute a single block with appropriate dialog."""
        block_name = block_data.get('name', 'Unknown')

        print(f"DEBUG: Executing {block_name} (step {step_number}/{total_steps})")

        if block_name == "Assembly":
            return PipelineRunner._execute_assembly_block(block_data, step_number, total_steps, parent_widget)
        elif block_name == "Screw":
            return PipelineRunner._execute_screw_block(block_data, step_number, total_steps, parent_widget)
        else:
            return PipelineRunner._execute_generic_block(block_data, step_number, total_steps, parent_widget)

    # ================== Operator Mode Pipeline Execution ==================

    @staticmethod
    def run_pipeline_operator_mode(recipe_name: str, parent_widget,
                                   pending_callback=None) -> bool:
        """
        Operator mode pipeline execution - supports intelligent skipping of missing parts.
        Extracts part names from product names like "0_A", "1_B", etc.
        Now uses MES API for inventory and job ID from title field.
        """
        print(f"DEBUG: Starting operator pipeline for recipe: {recipe_name}")

        # ===== INITIALIZE API CLIENT =====
        if PipelineRunner._api_client is None:
            PipelineRunner.init_api_client()

        # ===== GET JOB DETAILS FROM MES API =====
        job_id = None
        mes_job_details = {}

        if PipelineRunner._api_client:
            try:
                # Get full job details from running endpoint
                # Endpoint: http://127.0.0.1:5000/api/GetPartNumberDetail/running
                mes_job_details = PipelineRunner._api_client.get_job_details()

                if mes_job_details:
                    # Extract job ID from title field
                    job_id = mes_job_details.get('workOrder')
                    print(f"✅ Got job ID from MES workOrder: {job_id}")
                    print(f"📋 Full job details: {mes_job_details}")

                    # You can also extract other useful fields
                    product_code = mes_job_details.get('product_code')
                    if product_code:
                        print(f"📦 Product code: {product_code}")
                else:
                    print(f"⚠️ No job details from MES, will generate local ID")

            except Exception as e:
                print(f"❌ Error getting job details from MES: {e}")
                import traceback
                traceback.print_exc()
                job_id = None
                mes_job_details = {}

        # Fallback to local generation if no MES job ID
        if not job_id:
            job_id = f"JOB_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print(f"📝 Generated local job ID: {job_id}")

        # ===== INITIALIZE HEARTBEAT MANAGER AND CALIBRATION =====
        PipelineRunner._init_heartbeat_manager()
        calibration = PipelineRunner._load_calibration(recipe_name)

        # Show connection status
        if PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected():
            print(f"✅ Pipeline running with TCP heartbeat")

        if PipelineRunner._api_client:
            print(f"✅ MES API client connected")

        # Show connection status
        if PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected():
            print(
                f"✅ Pipeline running with TCP heartbeat to {PipelineRunner._get_server_address()}:{PipelineRunner._get_server_port()}")
            if calibration and calibration.is_calibrated:
                print(f"📐 Using WORLD coordinates (calibration loaded)")
            else:
                print(f"📷 Using PIXEL coordinates (no calibration)")

        try:
            # Set current recipe
            config_manager.set_current_recipe(recipe_name)

            # 1. Load pipeline
            flow_data = PipelineRunner.get_pipeline_from_file(recipe_name)
            if not flow_data:
                QMessageBox.warning(
                    parent_widget,
                    "⚠️ No Pipeline Found",
                    f"Recipe '{recipe_name}' has no saved pipeline"
                )
                return False

            # 2. Get execution order
            execution_order = PipelineRunner.get_execution_order(flow_data)
            if not execution_order:
                QMessageBox.warning(
                    parent_widget,
                    "⚠️ Empty Pipeline",
                    "Pipeline has no executable blocks"
                )
                return False

            # 3. Create job record with MES job ID from title
            job_data = {
                'job_id': job_id,  # From MES title field
                'recipe': recipe_name,
                'start_time': datetime.now().isoformat(),
                'completed_steps': [],
                'skipped_steps': [],
                'waiting_steps': [],
                'total_steps': len(execution_order),
                'tcp_connected': PipelineRunner._heartbeat_manager.is_connected() if PipelineRunner._heartbeat_manager else False,
                'calibration_loaded': calibration.is_calibrated if calibration else False,
                'mes_job_id': job_id if job_id and not job_id.startswith('JOB_') else None,
                'mes_job_details': mes_job_details,  # Store full details for reference
                'product_code': mes_job_details.get('product_code') if mes_job_details else None,
                'work_order': mes_job_details.get('workOrder') if mes_job_details else None
            }

            # 4. Execute blocks with skip support
            for i, block_data in enumerate(execution_order):
                step_num = i + 1
                block_name = block_data.get('name', 'Unknown')

                print(f"DEBUG: Executing step {step_num}/{job_data['total_steps']}: {block_name}")

                # Check TCP connection status periodically
                if step_num % 5 == 0:  # Every 5 steps
                    if PipelineRunner._heartbeat_manager and not PipelineRunner._heartbeat_manager.is_connected():
                        print("⚠️ TCP heartbeat disconnected - attempting to reconnect...")
                        PipelineRunner._ensure_heartbeat_connected()

                # Execute based on block type
                if block_name == "Assembly":
                    # Execute assembly block with operator mode
                    result, info = PipelineRunner._execute_assembly_block_operator(
                        block_data, step_num, job_data['total_steps'],
                        parent_widget
                    )

                    if result == "completed":
                        job_data['completed_steps'].append(step_num)
                        print(f"DEBUG: Step {step_num} completed")
                    elif result == "skipped":
                        job_data['skipped_steps'].append({
                            'step': step_num,
                            'reason': info.get('reason', 'Missing parts'),
                            'missing_parts': info.get('missing_parts', [])
                        })
                        print(f"DEBUG: Step {step_num} skipped - {info.get('reason')}")
                    elif result == "waiting":
                        job_data['waiting_steps'].append({
                            'step': step_num,
                            'waiting_for': info.get('missing_parts', [])
                        })
                        # User chose to wait, stop execution

                        # Show waiting message with TCP status
                        tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and
                                                       PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"
                        cal_status = "World Coordinates" if (
                                calibration and calibration.is_calibrated) else "Pixel Coordinates"

                        QMessageBox.information(
                            parent_widget,
                            "⏳ Waiting for Parts",
                            f"Assembly paused, waiting for parts.\n\n"
                            f"Missing parts: {', '.join(info.get('missing_parts', []))}\n"
                            f"Completed {len(job_data['completed_steps'])} steps.\n\n"
                            f"📡 TCP Status: {tcp_status}\n"
                            f"📐 Calibration: {cal_status}"
                        )
                        break
                    else:  # cancelled
                        print(f"DEBUG: Pipeline cancelled at step {step_num}")
                        return False

                elif block_name == "Screw":
                    success = PipelineRunner._execute_screw_block(
                        block_data, step_num, job_data['total_steps'], parent_widget
                    )
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
                        print(f"DEBUG: Camera error: {e}")
                        reply = QMessageBox.question(
                            parent_widget,
                            "Camera Error",
                            f"Cannot open camera: {str(e)}\n\nSkip this step and continue?",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if reply == QMessageBox.Yes:
                            job_data['skipped_steps'].append({
                                'step': step_num,
                                'reason': 'camera_error'
                            })
                        else:
                            return False

                elif block_name == "End":
                    # End Block - just pass through and prepare for cleanup
                    job_data['completed_steps'].append(step_num)
                    print(f"DEBUG: End block reached - pipeline will complete")
                    # Don't break, let it finish normally

            # 5. Save job results
            job_data['end_time'] = datetime.now().isoformat()

            # Determine job status
            if job_data['skipped_steps'] and job_data['completed_steps']:
                job_data['status'] = 'partial'  # Partial completion
                message = f"Partial completion - Completed {len(job_data['completed_steps'])}/{job_data['total_steps']} steps"
            elif not job_data['skipped_steps'] and job_data['completed_steps']:
                job_data['status'] = 'complete'  # Full completion
                message = f"Full completion - {len(job_data['completed_steps'])} steps"
            elif job_data['waiting_steps']:
                job_data['status'] = 'waiting'  # Waiting for parts
                message = f"Waiting for parts - Completed {len(job_data['completed_steps'])} steps"
            else:
                job_data['status'] = 'incomplete'
                message = "Incomplete"

            # 🔥 MARK JOB COMPLETE IN MES - FOR BOTH FULL AND PARTIAL COMPLETION
            # Only mark MES-sourced jobs as complete (not locally generated ones)
            if job_data.get('job_id') and not str(job_data['job_id']).startswith('JOB_'):
                try:
                    from complete_mes import stop_latest_workorder
                    result = stop_latest_workorder(job_data['job_id'], recipe_name  )

                    if result:
                        print(
                            f"✅ Successfully marked job {job_data['job_id']} as complete in MES (status: {job_data['status']})"
                        )

                        # 通知 MainPage：post 成功后，尝试重新抓一次 MES
                        PipelineRunner._notify_main_page_refresh_mes(parent_widget)

                    else:
                        print(f"⚠️ MES stop_latest_workorder returned empty/failed for job {job_data['job_id']}")

                except ImportError:
                    print(f"⚠️ Could not import stop_latest_workorder from complete_mes")
                except Exception as e:
                    print(f"❌ Failed to mark job complete in MES: {e}")

            # Save pending job if there are skipped or waiting steps
            if pending_callback and (job_data['skipped_steps'] or job_data['waiting_steps']):
                pending_callback(job_data)

            # 6. Show completion message with TCP status and MES job info
            tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and
                                           PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"
            cal_status = "World Coordinates" if (calibration and calibration.is_calibrated) else "Pixel Coordinates"

            # Include MES job info in message
            mes_info = ""
            if mes_job_details:
                mes_info = f"\n📋 MES Job: {job_data.get('job_title', 'Unknown')}"
                if job_data.get('product_code'):
                    mes_info += f"\n📦 Product: {job_data.get('product_code')}"

            if job_data['skipped_steps']:
                skip_summary = "\n".join([
                    f"  Step {s['step']}: {s['reason']}"
                    for s in job_data['skipped_steps']
                ])
                QMessageBox.information(
                    parent_widget,
                    "✅ Assembly Complete",
                    f"Process execution completed!\n\n"
                    f"Job ID: {job_data['job_id']}{mes_info}\n"
                    f"Completed steps: {len(job_data['completed_steps'])}\n"
                    f"Skipped steps: {len(job_data['skipped_steps'])}\n\n"
                    f"Skipped steps:\n{skip_summary}\n\n"
                    f"These steps can be continued when parts arrive."
                )
            elif job_data['waiting_steps']:
                QMessageBox.information(
                    parent_widget,
                    "⏳ Waiting for Parts",
                    f"Process paused, waiting for parts.\n\n"
                    f"Job ID: {job_data['job_id']}{mes_info}\n"
                    f"Completed: {len(job_data['completed_steps'])}/{job_data['total_steps']} steps\n\n"
                    f"📡 TCP: {tcp_status}\n"
                    f"📐 Calibration: {cal_status}"
                )
            else:
                QMessageBox.information(
                    parent_widget,
                    "✅ Assembly Complete",
                    f"Process executed successfully!\n\n"
                    f"Job ID: {job_data['job_id']}{mes_info}\n"
                    f"Recipe: {recipe_name}\n"
                    f"Total steps: {job_data['total_steps']}\n\n"
                    f"📡 TCP: {tcp_status}\n"
                    f"📐 Calibration: {cal_status}"
                )

            return True

        except Exception as e:
            print(f"❌ Error in pipeline execution: {e}")
            import traceback
            traceback.print_exc()

            # Show error message with TCP status
            tcp_status = "🟢 Connected" if (PipelineRunner._heartbeat_manager and
                                           PipelineRunner._heartbeat_manager.is_connected()) else "🔴 Disconnected"

            QMessageBox.critical(
                parent_widget,
                "❌ Pipeline Error",
                f"Error during pipeline execution:\n\n{str(e)}\n\n"
                f"📡 TCP: {tcp_status}"
            )
            return False

        finally:
            # ===== CLEAN UP HEARTBEAT MANAGER =====
            # Force disconnect when pipeline ends (especially after End block)
            PipelineRunner.cleanup(force_disconnect=True)
            print("🔌 Pipeline heartbeat manager cleaned up and disconnected")

    # ================== Assembly Block Execution with Part Extraction ==================

    @staticmethod
    def _extract_part_from_product_name(product_name: str) -> str:
        """
        Extract MES part name from product display name.

        Examples:
            "0_A" -> "A"
            "1_B" -> "B"
            "2_AN10-01" -> "AN10-01"
            "Step_2_C" -> "C"
            "Install Part D" -> "D"
            "A" -> "A"
            "Screw M4" -> "M4"
        """
        if not product_name:
            return ""

        product_name = product_name.strip()

        # Case 1: If format is "number_part", remove the leading step/index prefix
        # Example: "2_AN10-01" -> "AN10-01", "0_A" -> "A"
        import re
        match = re.match(r'^\d+_(.+)$', product_name)
        if match:
            return match.group(1).strip()

        # Case 2: If format like "Step_2_C", take the last part
        parts = product_name.split('_')
        if len(parts) >= 2:
            last_part = parts[-1].strip()
            if last_part:
                return last_part

        # Case 3: If product name ends with a single letter (like "Install Part D")
        match = re.search(r'\b([A-F])\b$', product_name)
        if match:
            return match.group(1)

        # Case 4: If product name is already a simple letter
        if len(product_name) == 1 and product_name.isalpha():
            return product_name

        # Case 5: If product name contains standalone letter part
        words = product_name.split()
        for word in words:
            if len(word) == 1 and word.isalpha() and word in ['A', 'B', 'C', 'D', 'E', 'F']:
                return word

        # Case 6: Extract code like M4, M3
        match = re.search(r'\b([A-Z][0-9]+)\b$', product_name)
        if match:
            return match.group(1)

        # Default: use original name
        print(f"WARNING: Could not extract part from '{product_name}', using as-is")
        return product_name

    @staticmethod
    def _execute_assembly_block_operator(block_data: Dict, step_num: int, total_steps: int,
                                         parent_widget) -> Tuple[str, Dict]:
        """
        Operator mode execute Assembly block - extract part names after underscore
        Now uses MES API for inventory instead of callback
        """
        assembly_data = block_data.get('assembly_data', {})

        # Standardize configuration
        selections = {}
        total_assembly_steps = 0

        # Parse configuration structure (same as before)
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
            QMessageBox.warning(
                parent_widget,
                "⚠️ No Configuration",
                f"Assembly Block has no steps configured!"
            )
            return "cancelled", {}

        # Initialize API client if not already done
        if PipelineRunner._api_client is None:
            PipelineRunner.init_api_client()

        # Execute each step, checking inventory from API
        skipped_steps = []
        missing_parts_list = []

        for assembly_step in range(1, total_assembly_steps + 1):
            step_key = str(assembly_step)
            if step_key not in selections:
                continue

            selection = selections[step_key]
            product_data = selection.get('product_data', {})
            product_name = product_data.get('name', f'Step {assembly_step}')

            # 🔥 EXTRACT PART NAME FROM PRODUCT NAME (e.g., "0_A" → "A")
            part_needed = PipelineRunner._extract_part_from_product_name(product_name)

            print(f"DEBUG: Step {assembly_step} - Product: '{product_name}' → MES Part: '{part_needed}'")

            # In _execute_assembly_block_operator, around line where you get inventory:
            try:
                if PipelineRunner._api_client:
                    current_stock = PipelineRunner._api_client.get_inventory(part_needed)
                    print(f"   API inventory for {part_needed}: {current_stock}")
                else:
                    # Fallback if API client not available
                    print(f"   ⚠️ No API client available, assuming part {part_needed} is available")
                    current_stock = 999  # Assume available
            except Exception as e:
                print(f"❌ Failed to get inventory from API: {e}")
                current_stock = 999  # Fallback - assume available

            if current_stock <= 0:
                # Missing part, ask operator
                reply = PipelineRunner._ask_operator_about_missing_part(
                    assembly_step, product_name, part_needed, current_stock, parent_widget
                )

                if reply == "skip":
                    skipped_steps.append(assembly_step)
                    if part_needed:
                        missing_parts_list.append(part_needed)
                    continue
                elif reply == "wait":
                    return "waiting", {
                        'missing_parts': missing_parts_list + ([part_needed] if part_needed else []),
                        'step': assembly_step
                    }
                elif reply == "cancel":
                    return "cancelled", {}

            # Have part, execute step
            step_success = PipelineRunner._execute_assembly_step_like_dialog(
                assembly_step, total_assembly_steps, selection, parent_widget
            )

            if step_success:
                # 🔥 DEDUCT INVENTORY VIA API AFTER SUCCESSFUL ASSEMBLY
                try:
                    deduct_success = PipelineRunner._api_client.deduct_inventory(part_needed, 1)
                    if deduct_success:
                        print(f"✅ Deducted 1 from {part_needed} via API")
                    else:
                        print(f"⚠️ Failed to deduct inventory for {part_needed} via API")
                except Exception as e:
                    print(f"❌ Error deducting inventory: {e}")
            else:
                return "cancelled", {}

        if skipped_steps:
            return "skipped", {
                'reason': 'Missing parts',
                'missing_parts': list(set(missing_parts_list)),
                'skipped_steps': skipped_steps
            }

        return "completed", {}

    @staticmethod
    def _ask_operator_about_missing_part(step_num: int, product_name: str,
                                         part_needed: str, current_stock: int,
                                         parent_widget) -> str:
        """
        Ask operator how to handle missing part - shows both product name and MES part name
        """
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_num} - Missing Part")
        dialog.setFixedSize(500, 450)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)

        # Warning icon
        warning_label = QLabel("⚠️")
        warning_label.setStyleSheet("font-size: 72px; color: #f39c12;")
        warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(warning_label)

        # Message - shows both product name and MES part name
        message = QLabel(
            f"<h3>Step {step_num} - Missing Part</h3>"
            f"<p>Product: <b>{product_name}</b></p>"
            f"<p>MES Part: <b style='color:#e74c3c;'>{part_needed}</b></p>"
            f"<p>Current inventory: <b style='color:red;'>{current_stock}</b></p>"
            f"<p style='font-size:12px; color:#7f8c8d; margin-top:10px;'>"
            f"(Product name '{product_name}' mapped to MES part '{part_needed}')"
            f"</p>"
        )
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        message.setStyleSheet("font-size: 14px; margin: 10px;")
        layout.addWidget(message)

        # Option buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        skip_btn = QPushButton("⏭ Skip this step")
        skip_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 20px;
                background-color: #f39c12;
                color: white;
                border-radius: 6px;
                min-width: 120px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)

        wait_btn = QPushButton("⏳ Wait for parts")
        wait_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 20px;
                background-color: #3498db;
                color: white;
                border-radius: 6px;
                min-width: 120px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)

        cancel_btn = QPushButton("❌ Cancel assembly")
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 20px;
                background-color: #e74c3c;
                color: white;
                border-radius: 6px;
                min-width: 120px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)

        skip_btn.clicked.connect(lambda: dialog.done(1))
        wait_btn.clicked.connect(lambda: dialog.done(2))
        cancel_btn.clicked.connect(lambda: dialog.done(3))

        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(wait_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # Info tip
        info_label = QLabel(
            "💡 Tips:\n"
            "• Skip: Do other steps now, come back later\n"
            "• Wait: Pause current assembly, wait for parts\n"
            "• Cancel: End current assembly"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #7f8c8d;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 8px;
                margin-top: 10px;
            }
        """)
        layout.addWidget(info_label)

        result = dialog.exec()

        if result == 1:
            return "skip"
        elif result == 2:
            return "wait"
        else:
            return "cancel"

    @staticmethod
    def _execute_assembly_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        """Execute an Assembly block - standard mode."""
        assembly_data = block_data.get('assembly_data', {})

        # DEBUG: Print structure
        print(f"DEBUG: Assembly data keys: {list(assembly_data.keys())}")

        # STANDARDIZE: Always use flat structure for selections
        selections = {}
        total_assembly_steps = 0

        # Case 1: Flat structure - selections directly under assembly_data
        if 'selections' in assembly_data and isinstance(assembly_data['selections'], dict):
            selections_data = assembly_data['selections']

            # Check if selections has numeric keys directly
            step_keys = [k for k in selections_data.keys() if k.isdigit()]
            if step_keys:
                selections = selections_data
                total_assembly_steps = len(step_keys)
                print(f"DEBUG: Flat structure - {total_assembly_steps} steps")
            else:
                # Case 2: Nested structure - selections contains 'selections' and 'total_steps'
                if 'selections' in selections_data:
                    selections = selections_data.get('selections', {})
                    total_assembly_steps = selections_data.get('total_steps', 0)
                    print(f"DEBUG: Nested structure - {total_assembly_steps} steps")

        # Case 3: Direct numeric keys in assembly_data
        if not selections:
            step_keys = [k for k in assembly_data.keys() if k.isdigit()]
            if step_keys:
                selections = {k: assembly_data[k] for k in step_keys}
                total_assembly_steps = len(step_keys)
                print(f"DEBUG: Direct numeric keys - {total_assembly_steps} steps")

        # Fallback to total_steps
        if total_assembly_steps == 0:
            total_assembly_steps = assembly_data.get('total_steps', 0)

        if total_assembly_steps == 0 or not selections:
            QMessageBox.warning(
                parent_widget,
                "⚠️ No Configuration",
                f"This Assembly block has no assembly steps configured!\n\n"
                f"Please configure this block before running the pipeline."
            )
            return False

        # Execute each assembly step
        completed_steps = 0
        for step_num in range(1, total_assembly_steps + 1):
            step_key = str(step_num)

            if step_key in selections:
                selection = selections[step_key]

                print(f"DEBUG: Processing step {step_key}: {selection.get('product_id', 'Unknown')}")

                # Execute step
                step_success = PipelineRunner._execute_assembly_step_like_dialog(
                    step_num, total_assembly_steps, selection, parent_widget
                )

                if step_success:
                    completed_steps += 1
                    print(f"DEBUG: Step {step_num} completed successfully")
                else:
                    print(f"DEBUG: Step {step_num} cancelled or failed")
                    break
            else:
                print(f"DEBUG: Step {step_key} not found in selections")
                QMessageBox.warning(
                    parent_widget,
                    "⚠️ Missing Step",
                    f"Step {step_num} configuration not found!\n"
                    f"Available steps: {list(selections.keys())}"
                )
                break

        return True

    @staticmethod
    def cleanup(force_disconnect=True):
        """
        Clean up the heartbeat manager when pipeline execution ends.
        This should be called when pipeline completes, especially after End block.

        Args:
            force_disconnect: If True, always disconnect regardless of reference count
        """
        if PipelineRunner._heartbeat_manager is not None:
            PipelineRunner._heartbeat_reference_count -= 1
            print(f"🔌 Heartbeat manager reference count: {PipelineRunner._heartbeat_reference_count}")

            # Always disconnect when pipeline ends (especially after End block)
            if force_disconnect or PipelineRunner._heartbeat_reference_count <= 0:
                PipelineRunner._heartbeat_reference_count = 0
                if PipelineRunner._heartbeat_manager.is_connected():
                    PipelineRunner._heartbeat_manager.disconnect()
                    print("🔌 Heartbeat manager disconnected after pipeline completion")

                # Clear the manager to force fresh connection next time
                PipelineRunner._heartbeat_manager = None
                print("✅ Heartbeat manager cleared")

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
            except Exception as e:
                print(f"Error loading pending jobs: {e}")
                existing = []

        existing = [j for j in existing if j.get('job_id') != job_id]

        try:
            with open(pending_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving pending jobs: {e}")

    # ================== Screw Block Execution ==================

    @staticmethod
    def _execute_screw_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        """Execute a Screw block - send coordinates before and after operator confirmation."""
        PipelineRunner._init_heartbeat_manager()

        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_number}: Screw Operation")
        dialog.showFullScreen()

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        recipe_name = config_manager.current_recipe
        video_path = r"C:\Users\PC_AI_DS\Desktop\Video\1.mp4"

        # Try to get block_id from block_data / config / screw_data
        config = block_data.get('config')

        try:
            block_id = PipelineRunner._resolve_block_id(block_data)
        except Exception as e:
            QMessageBox.warning(
                parent_widget,
                "⚠️ Missing Block ID",
                f"Screw block does not contain a valid block id.\n\n{str(e)}"
            )
            return False

        print(f"🔍 Screw block resolved block_id = {block_id}")
        print(f"   block_data keys = {list(block_data.keys())}")
        if isinstance(config, dict):
            print(f"   config keys = {list(config.keys())}")

        print(f"🔍 Screw block resolved block_id = {block_id}")
        print(f"   block_data keys = {list(block_data.keys())}")
        if isinstance(config, dict):
            print(f"   config keys = {list(config.keys())}")

        # ===== SEND FIRST COORDINATES: ScrewBoxesData/Block_x =====
        first_send_success, first_coord_string = PipelineRunner._send_latest_coordinates_from_folder(
            recipe_name, "ScrewBoxesData", block_id
        )

        # Header
        header = QLabel(f"🔩 Screw Operation - Step {step_number}")
        header.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: white;
                background-color: #f39c12;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # TCP send status for first coordinates
        # first_coord_status = QLabel()
        # if first_send_success:
        #     first_coord_status.setText(
        #         # f"✅ Sent ScrewBoxesData coordinates to TCP\n"
        #         # f"Folder: {recipe_name}/ScrewBoxesData/Block_{block_id}\n"
        #         # f"{first_coord_string}"
        #     )
        #     first_coord_status.setStyleSheet("""
        #         QLabel {
        #             font-size: 13px;
        #             color: #27ae60;
        #             padding: 12px;
        #             background-color: #e8f8ef;
        #             border-radius: 8px;
        #             font-weight: bold;
        #         }
        #     """)
        # else:
        #     first_coord_status.setText(
        #         f"⚠️ Failed to send ScrewBoxesData coordinates\n"
        #         f"Folder: {recipe_name}/ScrewBoxesData/Block_{block_id}"
        #     )
        #     first_coord_status.setStyleSheet("""
        #         QLabel {
        #             font-size: 13px;
        #             color: #e74c3c;
        #             padding: 12px;
        #             background-color: #ffebee;
        #             border-radius: 8px;
        #             font-weight: bold;
        #         }
        #     """)
        # first_coord_status.setWordWrap(True)
        # layout.addWidget(first_coord_status)

        # Show configuration
        if config:
            info_frame = QFrame()
            info_frame.setStyleSheet("""
                QFrame {
                    border: 2px solid #f39c12;
                    border-radius: 8px;
                    background-color: #fff9e6;
                    padding: 6px;
                    margin: 6px;
                }
            """)

            info_layout = QVBoxLayout(info_frame)

            title_label = QLabel("⚙️ Screw Configuration")
            title_label.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #d35400;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #f39c12;
                    margin-bottom: 15px;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            info_layout.addWidget(title_label)

            if isinstance(config, dict):
                screw_count = config.get('count', 'Not specified')
                screw_type = config.get('type', 'Not specified')
                torque = config.get('torque', 'Not specified')
                position = config.get('position', 'Not specified')
            elif isinstance(config, str):
                screw_count = "Not specified"
                screw_type = "Not specified"
                torque = "Not specified"
                position = "Not specified"

                lines = config.strip().split('\n')
                for line in lines:
                    line_lower = line.lower()
                    if 'count:' in line_lower:
                        screw_count = line.split(':')[-1].strip()
                    elif 'type:' in line_lower:
                        screw_type = line.split(':')[-1].strip()
                    elif 'torque:' in line_lower:
                        torque = line.split(':')[-1].strip()
                    elif 'position:' in line_lower:
                        position = line.split(':')[-1].strip()
            else:
                screw_count = "Unknown"
                screw_type = "Unknown"
                torque = "Unknown"
                position = "Unknown"

            info_grid = QGridLayout()
            info_grid.setSpacing(10)

            labels = [
                ("🔢 Screw Count:", screw_count),
                ("⚙️ Screw Type:", screw_type),
                ("💪 Torque Setting:", torque),
                ("📍 Screw Positions:", position),
                ("🧩 Block ID:", block_id),
            ]

            for i, (label_text, value) in enumerate(labels):
                label = QLabel(label_text)
                label.setStyleSheet("font-weight: bold; font-size: 15px; color: #2c3e50;")
                info_grid.addWidget(label, i, 0)

                value_label = QLabel(str(value))
                value_label.setStyleSheet(
                    "font-size: 15px; padding: 5px; background-color: white; border-radius: 4px; border: 1px solid #bdc3c7;")
                if i == 3:
                    value_label.setWordWrap(True)
                info_grid.addWidget(value_label, i, 1)

            info_layout.addLayout(info_grid)
            info_layout.addStretch()
            layout.addWidget(info_frame)
        else:
            warning_frame = QFrame()
            warning_frame.setStyleSheet("""
                QFrame {
                    border: 2px dashed #e74c3c;
                    border-radius: 8px;
                    background-color: #ffebee;
                    padding: 40px;
                    margin: 20px;
                }
            """)

            warning_layout = QVBoxLayout(warning_frame)
            warning_label = QLabel("⚠️ No Configuration Found")
            warning_label.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #c0392b;
                }
            """)
            warning_label.setAlignment(Qt.AlignCenter)

            warning_text = QLabel(
                "This Screw block has not been configured.\n\n"
                "Configure it in the flow editor before running pipeline."
            )
            warning_text.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    color: #7f8c8d;
                    text-align: center;
                    margin-top: 10px;
                }
            """)
            warning_text.setWordWrap(True)
            warning_text.setAlignment(Qt.AlignCenter)

            warning_layout.addWidget(warning_label)
            warning_layout.addWidget(warning_text)
            layout.addWidget(warning_frame)

        # Instructions
        instructions_frame = QFrame()
        instructions_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #bdc3c7;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 20px;
                margin: 10px;
            }
        """)

        instructions_layout = QVBoxLayout(instructions_frame)
        instructions_title = QLabel("📋 Instructions:")
        instructions_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                padding-bottom: 8px;
                border-bottom: 1px solid #dfe6e9;
                margin-bottom: 10px;
            }
        """)

        instructions_text = QLabel(
            "1. Prepare the screwdriver/tool\n"
            "2. Position at specified locations\n"
            "3. Apply correct torque\n"
            "4. Verify tightness\n"
            "5. Check alignment"
        )
        instructions_text.setStyleSheet("font-size: 14px; color: #7f8c8d; line-height: 1.6;")

        instructions_layout.addWidget(instructions_title)
        instructions_layout.addWidget(instructions_text)
        layout.addWidget(instructions_frame)

        # Buttons
        button_layout = QHBoxLayout()

        cancel_btn = QPushButton("❌ Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 12px 24px;
                background-color: #e74c3c;
                color: white;
                border-radius: 8px;
                min-width: 150px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)

        ok_btn = QPushButton("✅ OK - Continue")
        ok_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 15px 30px;
                background-color: #2ecc71;
                color: white;
                border-radius: 8px;
                min-width: 220px;
                margin-top: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)

        cancel_btn.clicked.connect(dialog.reject)

        def on_ok_continue():
            # Send second coordinates first
            second_send_success, second_coord_string = PipelineRunner._send_latest_coordinates_from_folder(
                recipe_name, "ScrewBoxesData2", block_id
            )

            if second_send_success:
                print(f"✅ Sent ScrewBoxesData2 coordinates before video: {second_coord_string}")
            else:
                print(f"⚠️ Failed to send ScrewBoxesData2 coordinates before video")

            dialog.accept()

            # Show video after operator pressed OK
            PipelineRunner._show_video_dialog(
                video_path=video_path,
                parent_widget=parent_widget,
                title=f"Step {step_number}: Screw Video"
            )

        ok_btn.clicked.connect(on_ok_continue)

        button_layout.addWidget(cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)

        result = dialog.exec()
        return result == QDialog.Accepted

    @staticmethod
    def _resolve_block_id(block_data: Dict) -> str:
        """Resolve actual block id for Block_x folders using saved block id only."""
        candidates = []

        if isinstance(block_data, dict):
            # direct fields
            candidates.extend([
                block_data.get("id"),
                block_data.get("block_id"),
                block_data.get("block_number"),
                block_data.get("index"),
            ])

            # nested config
            config = block_data.get("config")
            if isinstance(config, dict):
                candidates.extend([
                    config.get("id"),
                    config.get("block_id"),
                    config.get("block_number"),
                    config.get("index"),
                ])

            # nested screw_data
            screw_data = block_data.get("screw_data")
            if isinstance(screw_data, dict):
                candidates.extend([
                    screw_data.get("id"),
                    screw_data.get("block_id"),
                    screw_data.get("block_number"),
                    screw_data.get("index"),
                ])

            # nested capture_info
            capture_info = block_data.get("capture_info")
            if isinstance(capture_info, dict):
                candidates.extend([
                    capture_info.get("id"),
                    capture_info.get("block_id"),
                    capture_info.get("block_number"),
                    capture_info.get("index"),
                ])

        for value in candidates:
            if value is not None and str(value).strip() != "":
                return str(value)

        raise ValueError("Cannot resolve block id from block_data")

    # ================== Generic Block Execution ==================

    @staticmethod
    def _execute_generic_block(block_data: Dict, step_number: int, total_steps: int, parent_widget) -> bool:
        """Execute a generic block."""
        block_name = block_data.get('name', 'Unknown')

        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_number}: {block_name}")
        dialog.showFullScreen()

        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel(f"{block_name} - Step {step_number}")
        header.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 15px;
                border-radius: 6px;
                margin-bottom: 15px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Information
        info_label = QLabel(f"Executing: {block_name}\n\n"
                            f"Step {step_number} of {total_steps}")
        info_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #2c3e50;
                padding: 30px;
                background-color: #f8f9fa;
                border-radius: 8px;
                margin: 10px;
            }
        """)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Show configuration if exists
        config = block_data.get('config')
        if config:
            config_label = QLabel(f"Configuration:\n{config}")
            config_label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    color: #7f8c8d;
                    padding: 15px;
                    background-color: #ecf0f1;
                    border-radius: 6px;
                    margin: 10px;
                }
            """)
            config_label.setWordWrap(True)
            layout.addWidget(config_label)

        # OK button
        ok_btn = QPushButton("OK - Continue")
        ok_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 15px 30px;
                background-color: #3498db;
                color: white;
                border-radius: 8px;
                margin-top: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)

        result = dialog.exec()
        return result == QDialog.Accepted

    # ================== Pending Jobs Management ==================

    @staticmethod
    def get_pending_jobs(recipe_name: str) -> List[Dict]:
        """Get pending jobs for a recipe."""
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return []

        pending_file = os.path.join(recipe_folder, 'pending_jobs.json')
        if os.path.exists(pending_file):
            try:
                with open(pending_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading pending jobs: {e}")
                return []
        return []

    @staticmethod
    def save_pending_job(recipe_name: str, job_data: Dict):
        """Save a pending job to file - remove if completed"""
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return

        pending_file = os.path.join(recipe_folder, 'pending_jobs.json')

        # Load existing jobs
        existing = []
        if os.path.exists(pending_file):
            try:
                with open(pending_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception as e:
                print(f"Error loading pending jobs: {e}")
                existing = []

        # Check job status
        status = job_data.get('status', '')
        job_id = job_data.get('job_id')
        completed_steps = job_data.get('completed_steps', [])
        total_steps = job_data.get('total_steps', 0)

        print(f"DEBUG: save_pending_job - {job_id}: status={status}, completed={len(completed_steps)}/{total_steps}")

        # Remove old record with same ID
        existing = [j for j in existing if j.get('job_id') != job_id]

        if status != 'complete' and len(completed_steps) < total_steps:
            # If not completed, add new record
            existing.append(job_data)
            print(f"DEBUG: Saved pending job: {job_id} (status: {status})")
        else:
            # If completed, don't add (already removed)
            print(f"DEBUG: Job {job_id} completed - removed from pending")

        # Keep only last 100 jobs
        if len(existing) > 100:
            existing = existing[-100:]

        # Save
        try:
            with open(pending_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving pending job: {e}")

    @staticmethod
    def clean_completed_jobs(recipe_name: str):
        """Clean up all completed jobs"""
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return

        pending_file = os.path.join(recipe_folder, 'pending_jobs.json')
        if not os.path.exists(pending_file):
            return

        try:
            with open(pending_file, 'r', encoding='utf-8') as f:
                jobs = json.load(f)

            # Keep only incomplete jobs
            incomplete_jobs = []
            for job in jobs:
                status = job.get('status', '')
                # Keep jobs with partial, waiting, pending status
                if status in ['partial', 'waiting', 'pending']:
                    incomplete_jobs.append(job)

            # Save back to file
            with open(pending_file, 'w', encoding='utf-8') as f:
                json.dump(incomplete_jobs, f, indent=2, ensure_ascii=False)

            print(f"DEBUG: Cleaned completed jobs - kept {len(incomplete_jobs)} pending jobs")

        except Exception as e:
            print(f"Error cleaning completed jobs: {e}")

    @staticmethod
    def _execute_assembly_step_like_dialog(step_num: int, total_steps: int, selection: Dict, parent_widget) -> bool:
        """
        Execute assembly step with camera capture and YOLO detection.
        Same behavior as AssemblyDialog auto-capture.
        """
        from datetime import datetime
        import os
        import shutil
        import cv2
        import numpy as np
        from PySide6.QtWidgets import QApplication, QProgressBar
        from PySide6.QtCore import QTimer

        # ===== INITIALIZE HEARTBEAT MANAGER AND CALIBRATION =====
        PipelineRunner._init_heartbeat_manager()  # This increments reference count for this step
        calibration = PipelineRunner._load_calibration(config_manager.current_recipe)

        product_data = selection.get('product_data', {})
        product_name = product_data.get('name', f'Product {step_num}')
        product_id = selection.get('product_id', product_data.get('id', f'product_{step_num}'))

        # ================== FIND REFERENCE IMAGE ==================
        reference_image_path = product_data.get('image_path')

        print(f"DEBUG product_name = {product_name}")
        print(f"DEBUG product_data = {product_data}")
        print(f"DEBUG original reference_image_path = {reference_image_path}")

        # Fallback 1: try Annotation folder in current recipe
        if not reference_image_path or not os.path.exists(reference_image_path):
            recipe_folder = config_manager.get_recipe_folder(config_manager.current_recipe)
            if recipe_folder:
                annotation_folder = os.path.join(recipe_folder, "Annotation")
                print(f"DEBUG trying annotation folder: {annotation_folder}")

                if os.path.exists(annotation_folder):
                    import glob

                    # exact name match first
                    exact_bmp = os.path.join(annotation_folder, f"{product_name}.bmp")
                    exact_png = os.path.join(annotation_folder, f"{product_name}.png")
                    exact_jpg = os.path.join(annotation_folder, f"{product_name}.jpg")
                    exact_jpeg = os.path.join(annotation_folder, f"{product_name}.jpeg")

                    if os.path.exists(exact_bmp):
                        reference_image_path = exact_bmp
                    elif os.path.exists(exact_png):
                        reference_image_path = exact_png
                    elif os.path.exists(exact_jpg):
                        reference_image_path = exact_jpg
                    elif os.path.exists(exact_jpeg):
                        reference_image_path = exact_jpeg
                    else:
                        # fuzzy match with full product name
                        matches = []
                        matches.extend(glob.glob(os.path.join(annotation_folder, f"*{product_name}*.bmp")))
                        matches.extend(glob.glob(os.path.join(annotation_folder, f"*{product_name}*.png")))
                        matches.extend(glob.glob(os.path.join(annotation_folder, f"*{product_name}*.jpg")))
                        matches.extend(glob.glob(os.path.join(annotation_folder, f"*{product_name}*.jpeg")))

                        # if product name like "3_PL8-02", also try suffix "PL8-02"
                        if not matches and "_" in product_name:
                            suffix = product_name.split("_", 1)[1].strip()
                            print(f"DEBUG trying suffix match: {suffix}")
                            matches.extend(glob.glob(os.path.join(annotation_folder, f"*{suffix}*.bmp")))
                            matches.extend(glob.glob(os.path.join(annotation_folder, f"*{suffix}*.png")))
                            matches.extend(glob.glob(os.path.join(annotation_folder, f"*{suffix}*.jpg")))
                            matches.extend(glob.glob(os.path.join(annotation_folder, f"*{suffix}*.jpeg")))

                        if matches:
                            matches.sort(key=os.path.getmtime, reverse=True)
                            reference_image_path = matches[0]

        # Fallback 2: try from selection root if image_path stored as relative path
        if reference_image_path and not os.path.isabs(reference_image_path):
            recipe_folder = config_manager.get_recipe_folder(config_manager.current_recipe)
            if recipe_folder:
                candidate = os.path.join(recipe_folder, reference_image_path)
                if os.path.exists(candidate):
                    reference_image_path = candidate

        print(f"DEBUG final reference_image_path = {reference_image_path}")
        print(f"DEBUG path exists = {os.path.exists(reference_image_path) if reference_image_path else False}")
        # ================== END FIND REFERENCE IMAGE ==================

        # Get saved configuration image path
        saved_config_image = None
        if 'captured_image_path' in selection and selection['captured_image_path']:
            saved_config_image = selection['captured_image_path']
            print(f"DEBUG: Found saved config image: {saved_config_image}")
        elif 'capture_info' in selection and 'current_image' in selection['capture_info']:
            saved_config_image = selection['capture_info']['current_image']
            print(f"DEBUG: Found saved config image from capture_info: {saved_config_image}")

        # Get block ID
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

        # Get recipe name
        recipe_name = config_manager.current_recipe

        # Create save path for new capture
        recipe_folder = config_manager.get_recipe_folder(recipe_name)
        capture_folder = os.path.join(recipe_folder, "Capture")
        os.makedirs(capture_folder, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Image_{timestamp}.bmp"
        new_capture_path = os.path.join(capture_folder, filename)

        # Find YOLO model and class ID
        model_path = None
        class_id = None

        recipe_path = config_manager.get_recipe_folder(recipe_name)
        if recipe_path:
            yolo_model_folder = os.path.join(recipe_path, "yolo_model")
            if os.path.exists(yolo_model_folder):
                import glob
                # Find best.pt in train_* subfolders
                best_pattern = os.path.join(yolo_model_folder, "**", "weights", "best.pt")
                best_files = glob.glob(best_pattern, recursive=True)
                if best_files:
                    best_files.sort(key=os.path.getmtime, reverse=True)
                    model_path = best_files[0]
                    print(f"DEBUG: Found model: {model_path}")

                    # Try to load model to get class mapping
                    try:
                        from ultralytics import YOLO
                        temp_model = YOLO(model_path)

                        # Get class ID for this product
                        if hasattr(temp_model, 'names'):
                            print(f"DEBUG: Model classes: {temp_model.names}")

                            # Try exact match first
                            for cid, name in temp_model.names.items():
                                if product_name.lower() == name.lower():
                                    class_id = cid
                                    print(f"DEBUG: Exact match - Class ID {cid}: {name}")
                                    break

                            # Try partial match if no exact match
                            if class_id is None:
                                for cid, name in temp_model.names.items():
                                    if product_name.lower() in name.lower() or name.lower() in product_name.lower():
                                        class_id = cid
                                        print(f"DEBUG: Partial match - Class ID {cid}: {name}")
                                        break

                            # Try just the letter (like 'A' from '0_A')
                            if class_id is None and '_' in product_name:
                                letter_part = product_name.split('_')[-1]
                                print(f"DEBUG: Trying letter part: '{letter_part}'")
                                for cid, name in temp_model.names.items():
                                    if letter_part.lower() == name.lower() or letter_part.lower() in name.lower():
                                        class_id = cid
                                        print(f"DEBUG: Letter match - Class ID {cid}: {name}")
                                        break

                        del temp_model

                    except Exception as e:
                        print(f"DEBUG: Error getting class mapping: {e}")

        # Create dialog
        dialog = QDialog(parent_widget)
        dialog.setWindowTitle(f"Step {step_num}/{total_steps}: {product_name} - Auto Detection")
        dialog.showFullScreen()

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        if class_id is not None:
            header_text = f"🔍 Step {step_num}/{total_steps}: {product_name}"
        else:
            header_text = f"🔍 Step {step_num}/{total_steps}: {product_name} (No class filter)"

        header = QLabel(header_text)
        header.setStyleSheet("""
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: white;
                background-color: #3498db;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }
        """)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # ----- LEFT: Reference Image -----
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(10, 10, 10, 10)

        ref_header = QLabel("📋 Product Image")
        ref_header.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #e3f2fd;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        ref_header.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(ref_header)

        ref_image_label = QLabel()
        ref_image_label.setAlignment(Qt.AlignCenter)
        ref_image_label.setMinimumHeight(450)
        ref_image_label.setStyleSheet("""
            QLabel {
                border: 3px solid #3498db;
                border-radius: 8px;
                background-color: #f8f9fa;
                padding: 1px;
            }
        """)

        if reference_image_path and os.path.exists(reference_image_path):
            pixmap = QPixmap(reference_image_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(550, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                ref_image_label.setPixmap(scaled_pixmap)
                print(f"✅ Loaded product image: {reference_image_path}")
            else:
                ref_image_label.setText(f"⚠️ Product image cannot be loaded\n{reference_image_path}")
                print(f"❌ QPixmap failed to load: {reference_image_path}")
        else:
            ref_image_label.setText(
                f"⚠️ Product image not found\n\n"
                f"Product: {product_name}\n"
                f"Path: {reference_image_path}"
            )
            print(f"❌ Product image not found for: {product_name}")

        left_layout.addWidget(ref_image_label)
        left_layout.addStretch()

        # ----- RIGHT: Detection Result with Loading -----
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 10, 10, 10)

        detection_header = QLabel("🤖 Detection Result")
        detection_header.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: white;
                padding: 10px;
                background-color: #8e44ad;
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        detection_header.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(detection_header)

        # Detection container
        detection_container = QWidget()
        detection_container.setMinimumHeight(450)
        detection_container.setStyleSheet("""
            QWidget {
                border: 3px solid #8e44ad;
                border-radius: 8px;
                background-color: #f5f0fa;
            }
        """)

        detection_container_layout = QVBoxLayout(detection_container)

        # Loading widget
        loading_widget = QWidget()
        loading_layout = QVBoxLayout(loading_widget)

        # Loading animation
        loading_label = QLabel()
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setMinimumHeight(200)

        # Try to use GIF or fallback to text animation
        loading_label.setText("⏳ Processing...")
        loading_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                color: #8e44ad;
                font-weight: bold;
            }
        """)

        # Create animation timer
        dot_count = 0
        loading_timer = QTimer()

        def update_loading_text():
            nonlocal dot_count
            dot_count = (dot_count + 1) % 4
            dots = "." * dot_count
            loading_label.setText(f"⏳ Processing{dots}")

        loading_timer.timeout.connect(update_loading_text)
        loading_timer.start(500)

        loading_layout.addWidget(loading_label)

        # Loading message
        loading_message = QLabel("Capturing image and running AI detection...")
        loading_message.setAlignment(Qt.AlignCenter)
        loading_message.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #2c3e50;
                margin-top: 20px;
            }
        """)
        loading_layout.addWidget(loading_message)

        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 0)  # Indeterminate mode
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #8e44ad;
                border-radius: 5px;
                text-align: center;
                height: 20px;
                max-width: 300px;
            }
            QProgressBar::chunk {
                background-color: #8e44ad;
                border-radius: 3px;
            }
        """)
        loading_layout.addWidget(progress_bar, alignment=Qt.AlignCenter)

        detection_container_layout.addWidget(loading_widget)

        # Detection result label (initially hidden)
        detection_label = QLabel()
        detection_label.setAlignment(Qt.AlignCenter)
        detection_label.setVisible(False)
        detection_container_layout.addWidget(detection_label)

        right_layout.addWidget(detection_container)

        # Detection info panel
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 6px;
                padding: 1x;
                margin-top: 10px;
                border: 1px solid #8e44ad;
            }
        """)
        info_layout = QVBoxLayout(info_frame)

        # Calibration status
        cal_status_label = QLabel()
        if calibration and calibration.is_calibrated:
            cal_status_label.setText("📐 Calibration: Loaded (World Coordinates)")
            cal_status_label.setStyleSheet(
                "font-size: 12px; color: #27ae60; padding: 5px; background-color: #e8f8ef; border-radius: 3px;")
        else:
            cal_status_label.setText("📐 Calibration: None (Pixel Coordinates)")
            cal_status_label.setStyleSheet(
                "font-size: 12px; color: #7f8c8d; padding: 5px; background-color: #ecf0f1; border-radius: 3px;")
        info_layout.addWidget(cal_status_label)

        detection_status = QLabel("📊 Status: Initializing camera...")
        detection_status.setStyleSheet("font-size: 13px; color: #f39c12; font-weight: bold;")
        info_layout.addWidget(detection_status)

        detection_result = QLabel("🏷️ Detected objects: --")
        detection_result.setStyleSheet("font-size: 13px; color: #7f8c8d;")
        info_layout.addWidget(detection_result)

        confidence_label = QLabel("📈 Confidence: --")
        confidence_label.setStyleSheet("font-size: 13px; color: #7f8c8d;")
        info_layout.addWidget(confidence_label)

        # Coordinate sent status
        coord_status_label = QLabel("📤 Coordinates: Not sent")
        coord_status_label.setStyleSheet(
            "font-size: 12px; color: #7f8c8d; padding: 5px; background-color: #f0f0f0; border-radius: 3px;")
        info_layout.addWidget(coord_status_label)

        right_layout.addWidget(info_frame)
        right_layout.addStretch()

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([550, 550])

        layout.addWidget(splitter)

        # Buttons
        button_layout = QHBoxLayout()

        cancel_btn = QPushButton("❌ Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px 24px;
                background-color: #e74c3c;
                color: white;
                border-radius: 6px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)

        verify_btn = QPushButton("✅ Verify & Continue")
        verify_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 15px 30px;
                background-color: #95a5a6;
                color: white;
                border-radius: 8px;
                min-width: 200px;
                font-weight: bold;
            }
            QPushButton:enabled {
                background-color: #2ecc71;
            }
            QPushButton:enabled:hover {
                background-color: #27ae60;
            }
        """)
        verify_btn.setEnabled(False)

        button_layout.addWidget(cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(verify_btn)

        layout.addLayout(button_layout)

        # Variables for capture results
        captured_image_path = None
        detection_results = None
        output_path = None
        processing_complete = False
        predictions_for_sending = []

        def show_results():
            """Hide loading and show detection results"""
            nonlocal processing_complete

            QApplication.processEvents()

            # Hide loading widget
            loading_widget.setVisible(False)

            # Show detection label
            detection_label.setVisible(True)

            processing_complete = True

            # Stop animation timer
            if loading_timer.isActive():
                loading_timer.stop()

        def on_capture_finished(success, message, image_path):
            """Callback when AutoCaptureFlow finishes"""
            nonlocal captured_image_path, detection_results, output_path, predictions_for_sending

            QApplication.processEvents()

            if success and image_path:
                try:
                    # Update status
                    detection_status.setText("📊 Status: Image captured, running AI detection...")

                    # Move/copy the captured image to the step folder
                    shutil.copy2(image_path, new_capture_path)

                    # Clean up original captured file
                    if os.path.exists(image_path):
                        os.remove(image_path)

                    captured_image_path = new_capture_path

                    # Run YOLO detection with class filter
                    if model_path and os.path.exists(model_path):
                        try:
                            from ultralytics import YOLO

                            # Read the captured image
                            frame = cv2.imread(new_capture_path)

                            # Load model
                            model = YOLO(model_path)

                            # Run detection with class filter
                            if class_id is not None:
                                print(f"DEBUG: 🔍 Detecting ONLY class {class_id} for product '{product_name}'")
                                results = model(frame, conf=0.25, classes=[class_id])
                            else:
                                print(f"DEBUG: 🔍 Detecting ALL objects for product '{product_name}'")
                                results = model(frame, conf=0.25)

                            detections = results[0]

                            # ===== EXTRACT PREDICTIONS FOR COORDINATE SENDING =====
                            predictions_for_sending = []
                            if len(detections.boxes) > 0:
                                boxes = detections.boxes

                                # Extract predictions in format expected by send_coordinates_to_server
                                if hasattr(boxes, 'xyxy') and hasattr(boxes, 'cls') and hasattr(boxes, 'conf'):
                                    for i in range(len(boxes)):
                                        # Get coordinates
                                        xyxy = boxes.xyxy[i].cpu().numpy() if hasattr(boxes.xyxy, 'cpu') else \
                                        boxes.xyxy[i]

                                        # Get class ID
                                        class_id_val = int(
                                            boxes.cls[i].cpu().numpy() if hasattr(boxes.cls, 'cpu') else boxes.cls[i])

                                        # Get confidence
                                        conf_val = float(
                                            boxes.conf[i].cpu().numpy() if hasattr(boxes.conf, 'cpu') else boxes.conf[
                                                i])

                                        # Get class name
                                        class_name = detections.names.get(class_id_val, f"class_{class_id_val}")

                                        predictions_for_sending.append({
                                            'bbox': xyxy.tolist() if hasattr(xyxy, 'tolist') else xyxy,
                                            'class_id': class_id_val,
                                            'class_name': class_name,
                                            'confidence': conf_val
                                        })

                                # ===== SEND COORDINATES TO SERVER =====
                                if predictions_for_sending:
                                    # Show calibration status with the fixed path
                                    if calibration and calibration.is_calibrated:
                                        print(
                                            f"📐 PipelineRunner using WORLD coordinates from: C:\\Users\\PC_AI_DS\\Pictures\\LaserCalibration\\calibration.json")
                                        coord_status_label.setText("📤 Converting to world coordinates...")
                                        coord_status_label.setStyleSheet(
                                            "font-size: 12px; color: #f39c12; padding: 5px; background-color: #fff3e0; border-radius: 3px; font-weight: bold;")
                                    else:
                                        print(f"📷 PipelineRunner using PIXEL coordinates (calibration not loaded)")
                                        coord_status_label.setText("📤 Using pixel coordinates...")
                                        coord_status_label.setStyleSheet(
                                            "font-size: 12px; color: #7f8c8d; padding: 5px; background-color: #f0f0f0; border-radius: 3px;")

                                    # Update status
                                    QApplication.processEvents()

                                    # Send coordinates
                                    success_sent = PipelineRunner.send_coordinates_to_server(predictions_for_sending,
                                                                                             calibration)

                                    if success_sent:
                                        coord_status_label.setText(
                                            f"✅ World coordinates sent: {len(predictions_for_sending)} objects")
                                        coord_status_label.setStyleSheet(
                                            "font-size: 12px; color: #27ae60; padding: 5px; background-color: #e8f8ef; border-radius: 3px; font-weight: bold;")
                                    else:
                                        coord_status_label.setText("❌ Failed to send world coordinates")
                                        coord_status_label.setStyleSheet(
                                            "font-size: 12px; color: #e74c3c; padding: 5px; background-color: #ffebee; border-radius: 3px; font-weight: bold;")

                                    QApplication.processEvents()

                            # Draw bounding boxes
                            annotated_frame = detections.plot()

                            # Save annotated image
                            annotated_filename = f"Step_{step_num}_{timestamp}_detected.jpg"
                            output_path = os.path.join(capture_folder, f"Step_{step_num}_{timestamp}_detected.jpg")
                            cv2.imwrite(output_path, annotated_frame)

                            # Display annotated image
                            rgb_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                            height, width = rgb_frame.shape[:2]

                            from PySide6.QtGui import QImage
                            q_img = QImage(rgb_frame.data, width, height,
                                           rgb_frame.strides[0], QImage.Format_RGB888)
                            pixmap = QPixmap.fromImage(q_img)

                            if not pixmap.isNull():
                                scaled = pixmap.scaled(detection_label.size(),
                                                       Qt.KeepAspectRatio,
                                                       Qt.SmoothTransformation)
                                detection_label.setPixmap(scaled)

                            # Update detection info
                            if len(detections.boxes) > 0:
                                boxes = detections.boxes
                                confidences = boxes.conf.cpu().numpy() if hasattr(boxes.conf, 'cpu') else boxes.conf

                                # Count objects by class
                                class_counts = {}
                                if hasattr(detections, 'names') and hasattr(boxes, 'cls'):
                                    class_ids = boxes.cls.cpu().numpy() if hasattr(boxes.cls, 'cpu') else boxes.cls
                                    for cid in class_ids:
                                        class_name = detections.names.get(int(cid), f"class_{int(cid)}")
                                        class_counts[class_name] = class_counts.get(class_name, 0) + 1

                                # Update UI based on whether we found the target class
                                target_found = False
                                if class_id is not None:
                                    for cid in class_ids:
                                        if int(cid) == class_id:
                                            target_found = True
                                            break

                                if (class_id is None) or (class_id is not None and target_found):
                                    detection_header.setText("✅ Detection Result")
                                    detection_header.setStyleSheet("""
                                        QLabel {
                                            font-size: 16px;
                                            font-weight: bold;
                                            color: white;
                                            padding: 10px;
                                            background-color: #27ae60;
                                            border-radius: 6px;
                                            margin-bottom: 10px;
                                        }
                                    """)

                                    detection_status.setText(f"✅ Detection: {len(boxes)} objects found")
                                    detection_status.setStyleSheet(
                                        "font-size: 13px; color: #27ae60; font-weight: bold;")
                                else:
                                    detection_header.setText(f"⚠️ No {product_name} Detected")
                                    detection_header.setStyleSheet("""
                                        QLabel {
                                            font-size: 16px;
                                            font-weight: bold;
                                            color: white;
                                            padding: 10px;
                                            background-color: #e67e22;
                                            border-radius: 6px;
                                            margin-bottom: 10px;
                                        }
                                    """)

                                    detection_status.setText(f"⚠️ No {product_name} found")
                                    detection_status.setStyleSheet(
                                        "font-size: 13px; color: #e67e22; font-weight: bold;")

                                objects_text = ", ".join([f"{k}: {v}" for k, v in class_counts.items()])
                                detection_result.setText(f"🏷️ Detected: {objects_text}")

                                avg_confidence = np.mean(confidences) * 100
                                confidence_label.setText(f"📈 Confidence: {avg_confidence:.1f}%")

                                detection_results = {
                                    'image_path': output_path,
                                    'objects': class_counts,
                                    'count': len(boxes),
                                    'confidence': float(avg_confidence),
                                    'class_id': class_id,
                                    'target_found': target_found if class_id is not None else True
                                }
                            else:
                                detection_header.setText(f"⚠️ No Objects Detected")
                                detection_header.setStyleSheet("""
                                    QLabel {
                                        font-size: 16px;
                                        font-weight: bold;
                                        color: white;
                                        padding: 10px;
                                        background-color: #e67e22;
                                        border-radius: 6px;
                                        margin-bottom: 10px;
                                    }
                                """)

                                detection_status.setText("⚠️ No objects detected")
                                detection_status.setStyleSheet("font-size: 13px; color: #e67e22; font-weight: bold;")
                                detection_result.setText(f"🏷️ Detected: None")
                                confidence_label.setText(f"📈 Confidence: N/A")

                                detection_results = {
                                    'image_path': output_path,
                                    'objects': {},
                                    'count': 0,
                                    'confidence': 0,
                                    'class_id': class_id,
                                    'target_found': False
                                }

                            # Show results and enable verify button
                            show_results()
                            verify_btn.setEnabled(True)

                        except Exception as e:
                            detection_header.setText("❌ Detection Error")
                            detection_header.setStyleSheet("""
                                QLabel {
                                    font-size: 16px;
                                    font-weight: bold;
                                    color: white;
                                    padding: 10px;
                                    background-color: #e74c3c;
                                    border-radius: 6px;
                                    margin-bottom: 10px;
                                }
                            """)
                            detection_status.setText(f"❌ Error: {str(e)[:50]}")
                            show_results()
                            verify_btn.setEnabled(True)
                            import traceback
                            traceback.print_exc()
                    else:
                        detection_header.setText("⚠️ No YOLO Model Found")
                        detection_header.setStyleSheet("""
                            QLabel {
                                font-size: 16px;
                                font-weight: bold;
                                color: white;
                                padding: 10px;
                                background-color: #e67e22;
                                border-radius: 6px;
                                margin-bottom: 10px;
                            }
                        """)
                        detection_status.setText("⚠️ No model found in yolo_model folder")
                        show_results()
                        verify_btn.setEnabled(True)

                except Exception as e:
                    detection_status.setText(f"❌ Error: {str(e)[:50]}")
                    show_results()
                    verify_btn.setEnabled(True)
                    import traceback
                    traceback.print_exc()
            else:
                detection_label.setText(f"❌ Capture failed: {message}")
                detection_status.setText(f"❌ {message}")
                show_results()
                verify_btn.setEnabled(True)

        # Start camera capture
        if CAMERA_AVAILABLE:
            detection_status.setText("📊 Status: Opening camera...")
            QApplication.processEvents()

            # Use AutoCaptureFlow with callback
            from camera.camera import AutoCaptureFlow
            AutoCaptureFlow(callback=on_capture_finished)

            QApplication.processEvents()
        else:
            detection_label.setText("❌ Camera module not available")
            detection_status.setText("❌ Camera unavailable")
            show_results()
            verify_btn.setEnabled(True)

        def on_verify():
            """Save results, show image from Capture/Block_x folder, and send coordinates"""
            nonlocal captured_image_path, detection_results, output_path

            # Save the new capture results to selection
            if captured_image_path and os.path.exists(captured_image_path):
                selection['pipeline_capture_path'] = captured_image_path
            if output_path and os.path.exists(output_path):
                selection['pipeline_detection_path'] = output_path
            if detection_results:
                selection['pipeline_detection_results'] = detection_results

            # ===== SEND COORDINATES TO SERVER =====
            coordinates_sent = False
            coord_string = ""

            try:
                # Construct path to BoxesData folder
                recipe_folder = config_manager.get_recipe_folder(recipe_name)
                boxes_folder = os.path.join(recipe_folder, "BoxesData", f"Block_{block_id}")

                # Find the most recent box_world JSON file
                if os.path.exists(boxes_folder):
                    import glob
                    json_files = glob.glob(os.path.join(boxes_folder, "box_world_*.json"))
                    if json_files:
                        # Get the most recent file
                        latest_json = max(json_files, key=os.path.getmtime)
                        print(f"📂 Found box data file: {latest_json}")

                        # Read the JSON file
                        with open(latest_json, 'r') as f:
                            box_data = json.load(f)

                        # Format coordinates as string: -23.62_10.11,23.27_10.35,...
                        coord_parts = []
                        for point in box_data:
                            if len(point) >= 2:
                                coord_parts.append(f"{point[0]:.2f}_{point[1]:.2f}")

                        if coord_parts:
                            coord_string = ",".join(coord_parts)

                            # Send to server using heartbeat manager
                            if PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected():
                                success = PipelineRunner._heartbeat_manager.send_data(coord_string + "\n")
                                if success:
                                    print(f"✅ Sent box coordinates: {coord_string}")
                                    coordinates_sent = True
                                else:
                                    print("❌ Failed to send box coordinates")
                            else:
                                print("⚠️ Heartbeat manager not connected, attempting to reconnect...")
                                PipelineRunner._ensure_heartbeat_connected()
                                if PipelineRunner._heartbeat_manager and PipelineRunner._heartbeat_manager.is_connected():
                                    success = PipelineRunner._heartbeat_manager.send_data(coord_string + "\n")
                                    if success:
                                        print(f"✅ Sent box coordinates after reconnect: {coord_string}")
                                        coordinates_sent = True
                    else:
                        print(f"⚠️ No box_world JSON files found in {boxes_folder}")
            except Exception as e:
                print(f"❌ Error sending box coordinates: {e}")
                import traceback
                traceback.print_exc()

            # Close the current dialog
            dialog.accept()

            # ===== SHOW IMAGE FROM recipe_folder/Capture/Block_x =====
            image_to_show = None

            try:
                import glob

                recipe_folder = config_manager.get_recipe_folder(recipe_name)
                block_capture_folder = os.path.join(recipe_folder, "Capture", f"Block_{block_id}")

                print(f"🔍 Looking for image in block capture folder: {block_capture_folder}")

                bmp_files = glob.glob(os.path.join(block_capture_folder, "*.bmp"))
                png_files = glob.glob(os.path.join(block_capture_folder, "*.png"))
                jpg_files = glob.glob(os.path.join(block_capture_folder, "*.jpg"))
                jpeg_files = glob.glob(os.path.join(block_capture_folder, "*.jpeg"))

                all_files = bmp_files + png_files + jpg_files + jpeg_files

                if all_files:
                    # 只拿最新那张
                    all_files.sort(key=os.path.getmtime, reverse=True)
                    image_to_show = all_files[0]
                    print(f"✅ Showing image from block folder: {image_to_show}")
                else:
                    print(f"⚠️ No image files found in {block_capture_folder}")

            except Exception as e:
                print(f"❌ Error finding image in block folder: {e}")
                import traceback
                traceback.print_exc()

            if image_to_show and os.path.exists(image_to_show):
                saved_image_dialog = QDialog(parent_widget)
                saved_image_dialog.setWindowTitle(f"Step {step_num}: Assembly Result")
                saved_image_dialog.showFullScreen()

                saved_layout = QVBoxLayout(saved_image_dialog)

                saved_header = QLabel(f"📸 Step {step_num}: Assembly Result")
                saved_header.setStyleSheet("""
                    QLabel {
                        font-size: 18px;
                        font-weight: bold;
                        color: white;
                        background-color: #3498db;
                        padding: 15px;
                        border-radius: 8px;
                        margin-bottom: 15px;
                    }
                """)
                saved_header.setAlignment(Qt.AlignCenter)
                saved_layout.addWidget(saved_header)

                # ===== COORDINATE STATUS =====
                # coord_status = QLabel()
                # if coordinates_sent:
                #     # coord_status.setText(f"✅ Coordinates sent to 127.0.0.1:8888\n{coord_string}")
                #     # coord_status.setStyleSheet("""
                #     #     QLabel {
                #     #         font-size: 14px;
                #     #         color: #27ae60;
                #     #         padding: 15px;
                #     #         background-color: #e8f8ef;
                #     #         border-radius: 8px;
                #     #         margin: 10px;
                #     #         font-weight: bold;
                #     #     }
                #     # """)
                # else:
                #     coord_status.setText("⚠️ Failed to send coordinates to server")
                #     coord_status.setStyleSheet("""
                #         QLabel {
                #             font-size: 14px;
                #             color: #e74c3c;
                #             padding: 15px;
                #             background-color: #ffebee;
                #             border-radius: 8px;
                #             margin: 10px;
                #             font-weight: bold;
                #         }
                #     """)
                # coord_status.setWordWrap(True)
                # saved_layout.addWidget(coord_status)

                # ===== IMAGE DISPLAY =====
                saved_image_label = QLabel()
                saved_image_label.setAlignment(Qt.AlignCenter)
                saved_image_label.setMinimumHeight(400)
                saved_image_label.setStyleSheet("""
                    QLabel {
                        border: 3px solid #3498db;
                        border-radius: 8px;
                        background-color: #f8f9fa;
                        padding: 10px;
                    }
                """)

                pixmap = QPixmap(image_to_show)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(700, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    saved_image_label.setPixmap(scaled)
                    print(f"✅ Showing image: {image_to_show}")
                else:
                    saved_image_label.setText("❌ Cannot load image")
                    print(f"❌ Failed to load image: {image_to_show}")

                saved_layout.addWidget(saved_image_label)

                # ===== COORDINATES DISPLAY =====
                if coordinates_sent:
                    coord_display = QLabel(f"📊 Sent Coordinates:\n{coord_string}")
                    coord_display.setStyleSheet("""
                        QLabel {
                            font-size: 12px;
                            color: #2c3e50;
                            padding: 10px;
                            background-color: #f8f9fa;
                            border-radius: 5px;
                            margin: 5px;
                            font-family: monospace;
                        }
                    """)
                    coord_display.setWordWrap(True)
                    saved_layout.addWidget(coord_display)

                # ===== CONTINUE BUTTON =====
                close_btn = QPushButton("Continue")
                close_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 14px;
                        padding: 12px 24px;
                        background-color: #2ecc71;
                        color: white;
                        border-radius: 6px;
                        min-width: 150px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #27ae60;
                    }
                """)
                close_btn.clicked.connect(saved_image_dialog.accept)
                saved_layout.addWidget(close_btn, alignment=Qt.AlignCenter)

                saved_image_dialog.exec()
            else:
                error_msg = (
                    f"No image found in Step {step_num}.\n\n"
                    f"Capture folder: {capture_folder}\n"
                    f"Selected image: {image_to_show}"
                )

                if coordinates_sent:
                    error_msg += f"\n\n✅ Coordinates were sent:\n{coord_string}"
                else:
                    error_msg += "\n\n❌ No coordinates were sent"

                QMessageBox.warning(
                    parent_widget,
                    "⚠️ Image Not Found",
                    error_msg
                )

        verify_btn.clicked.connect(on_verify)

        try:
            # Show dialog
            result = dialog.exec()

            # ===== DECREMENT HEARTBEAT REFERENCE COUNT =====
            # Each Assembly step should release its reference when done
            if PipelineRunner._heartbeat_manager is not None:
                PipelineRunner._heartbeat_reference_count -= 1
                print(
                    f"🔌 Assembly step {step_num} released heartbeat, reference count: {PipelineRunner._heartbeat_reference_count}")

            return result == QDialog.Accepted

        except Exception as e:
            # Make sure to decrement even on error
            if PipelineRunner._heartbeat_manager is not None:
                PipelineRunner._heartbeat_reference_count -= 1
                print(
                    f"🔌 Assembly step {step_num} released heartbeat on error, reference count: {PipelineRunner._heartbeat_reference_count}")
            raise e
        finally:
            # Clean up timer
            if loading_timer.isActive():
                loading_timer.stop()

    @staticmethod
    def _notify_main_page_refresh_mes(parent_widget, force=False):
        """通知 MainPage 尝试刷新一次 MES recipe"""
        try:
            if not parent_widget:
                return

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