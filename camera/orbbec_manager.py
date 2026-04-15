from camera.orbbec_camera_thread import OrbbecCameraThread
from PySide6.QtWidgets import QApplication


class OrbbecManager:
    _instance = None

    def __init__(self):
        self.thread = None
        self.current_handler = None
        self.current_live_slot = None


    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = OrbbecManager()
        return cls._instance

    def _find_existing_thread(self):
        try:
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, "orbbec_thread") and widget.orbbec_thread is not None:
                    return widget.orbbec_thread

                if hasattr(widget, "main_page") and hasattr(widget.main_page, "orbbec_thread"):
                    if widget.main_page.orbbec_thread is not None:
                        return widget.main_page.orbbec_thread
        except Exception as e:
            print(f"[OrbbecManager] ⚠️ Failed to find existing thread: {e}")

        return None

    def get_thread(self, recipe_name=None):
        if self.thread is not None:
            if recipe_name:
                try:
                    self.thread.set_recipe_name(recipe_name)
                except Exception:
                    pass
            return self.thread

        existing = self._find_existing_thread()
        if existing is not None:
            self.thread = existing
            if recipe_name:
                try:
                    self.thread.set_recipe_name(recipe_name)
                except Exception:
                    pass

            try:
                self.thread.use_trigger_boxes = True
                self.thread.trigger_delay_sec = 1.0
            except Exception:
                pass

            print("✅ OrbbecManager reused existing MainPage thread")
            return self.thread

        self.thread = OrbbecCameraThread()

        if recipe_name:
            self.thread.set_recipe_name(recipe_name)

        self.thread.use_trigger_boxes = True
        self.thread.trigger_delay_sec = 1.0
        self.thread.start()

        print("✅ OrbbecManager created new thread")
        return self.thread

    def reset_trigger_state(self):
        if self.thread is None:
            return

        try:
            self.thread.set_trigger_state("idle")
            self.thread.trigger_was_used = False
            self.thread.trigger_enter_time = None
        except Exception as e:
            print(f"[OrbbecManager] ⚠️ Failed to reset trigger state: {e}")

    def set_handler(self, handler):
        if self.thread is None:
            return

        if self.current_handler is handler:
            self.reset_trigger_state()
            return

        if self.current_handler is not None:
            try:
                self.thread.start_pipeline_signal.disconnect(self.current_handler)
            except Exception:
                pass

        self.current_handler = handler
        self.reset_trigger_state()

        if handler is not None:
            try:
                self.thread.start_pipeline_signal.connect(handler)
            except Exception as e:
                print(f"[OrbbecManager] ❌ Failed to connect handler: {e}")

    def attach_live_view(self, slot):
        if self.thread is None or slot is None:
            return

        if self.current_live_slot is slot:
            return

        if self.current_live_slot is not None:
            try:
                self.thread.frame_signal.disconnect(self.current_live_slot)
            except Exception:
                pass

        self.current_live_slot = slot

        try:
            self.thread.frame_signal.connect(slot)
        except Exception as e:
            print(f"[OrbbecManager] ❌ Failed to connect live slot: {e}")

    def detach_live_view(self, slot=None):
        if self.thread is None:
            return

        target = slot if slot is not None else self.current_live_slot
        if target is None:
            return

        try:
            self.thread.frame_signal.disconnect(target)
        except Exception:
            pass

        if target is self.current_live_slot:
            self.current_live_slot = None

    def clear_boxes(self):
        if self.thread:
            try:
                self.thread.clear_external_target_bbox()
                self.thread.clear_all_detection_boxes()
            except Exception:
                pass

    def set_boxes(self, target=None, others=None):
        if self.thread is None:
            return

        try:
            self.clear_boxes()

            if target:
                self.thread.set_external_target_bbox(target)

                if others:
                    self.thread.set_all_detection_boxes(others)
        except Exception as e:
            print(f"[OrbbecManager] ❌ set_boxes error: {e}")