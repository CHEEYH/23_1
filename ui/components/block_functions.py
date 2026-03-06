# ui/components/block_functions.py
import os

import cv2
import numpy as np
import pyrealsense2 as rs
from PySide6.QtWidgets import QMessageBox
import threading

camera_running = False

def open_realsense_camera():
    global camera_running
    if camera_running:
        return
    camera_running = True

    def cam():
        global camera_running
        try:
            pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            pipeline.start(config)

            cv2.namedWindow("Intel RealSense Camera", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Intel RealSense Camera", 800, 600)

            while camera_running:
                frames = pipeline.wait_for_frames(timeout_ms=5000)
                color_frame = frames.get_color_frame()
                if not color_frame:
                    continue

                img = np.asanyarray(color_frame.get_data())
                cv2.imshow("Intel RealSense Camera", img)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # 'q' or ESC
                    break

                if cv2.getWindowProperty("Intel RealSense Camera", cv2.WND_PROP_VISIBLE) < 1:
                    break

            camera_running = False
            pipeline.stop()
            cv2.destroyAllWindows()
        except Exception as e:
            camera_running = False
            QMessageBox.critical(None, "Camera Error", f"Cannot open camera:\n{str(e)}")
            print("Camera Error:", str(e))

    # Run camera in new thread
    thread = threading.Thread(target=cam, daemon=True)
    thread.start()


def assembly_function():
    try:
        from .dialogs import AssemblyDialog

        dialog = AssemblyDialog()
        if dialog.exec():
            step = dialog.selected_step
            product = dialog.selected_product
            product_data = dialog.product_data
            all_selections = dialog.get_all_selections()

            # Create detail message
            details = [f"🔧 Total Steps: {step}"]

            for step_num, selection in all_selections.items():
                details.append(f"\nStep {step_num}: {selection['product_id']}")
                product_data = selection['product_data']
                details.append(f"   📄 Annotation: {product_data.get('filename', 'N/A')}")
                details.append(f"   📁 Path: {product_data.get('annotation_path', 'N/A')}")
                model_path = product_data.get('model_path', '')
                model_name = os.path.basename(model_path) if model_path else 'N/A'
                details.append(f"   🤖 Model: {model_name}")
                details.append(f"   ✅ Trained: {'Yes' if product_data.get('trained') else 'No'}")

            message = "\n".join(details)

            # Ask if user wants to view captured images
            if hasattr(dialog, 'capture_folder') and dialog.capture_folder and os.path.exists(dialog.capture_folder):
                reply = QMessageBox.question(
                    None, "✅ Assembly Configured",
                    f"Assembly configuration saved!\n\n"
                    f"Captured images saved to:\n{dialog.capture_folder}\n\n"
                    "Would you like to open the capture folder?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes and hasattr(dialog, 'open_capture_folder'):
                    dialog.open_capture_folder()
            else:
                QMessageBox.information(None, "✅ Assembly Configured",
                                        f"Assembly configuration saved:\n\n{message}")

            return {
                'total_steps': step,
                'selections': all_selections,
                'capture_folder': getattr(dialog, 'capture_folder', None)
            }

    except Exception as e:
        QMessageBox.critical(None, "❌ Error", f"Failed to configure assembly: {str(e)}")
        print(f"Assembly dialog error: {e}")

    return None

def screw_function():
    from .dialogs import ScrewDialog
    dialog = ScrewDialog()
    if dialog.exec():
        count = dialog.screw_count
        screw_type = dialog.screw_type
        torque = dialog.torque

        QMessageBox.information(None, "✅ Screw Configuration",
                                f"Screws configured:\n\n"
                                f"🔩 Type: {screw_type}\n"
                                f"🔢 Count: {count}\n"
                                f"💪 Torque: {torque} N·m")

        # Actual screw tightening logic can be added here
        print(f"Screw: Tightening {count} of type {screw_type} at {torque} N·m")

def end_function():
    reply = QMessageBox.question(None, "🏁 End Process",
                                 "Are you sure you want to end the assembly process?",
                                 QMessageBox.Yes | QMessageBox.No)

    if reply == QMessageBox.Yes:
        QMessageBox.information(None, "✅ Process Completed",
                                "Assembly process completed successfully!")
        print("End: Process completed")

# Block function list
BLOCKS = [
    ("Assembly", assembly_function),
    ("Screw", screw_function),
    ("End", end_function),
    ("Camera", open_realsense_camera)
]