# prediction_manager.py
import torch
from ultralytics import YOLO
import os
from PySide6.QtCore import QObject, Signal


class PredictionSignals(QObject):
    """Signals for prediction communication"""
    progress = Signal(int, str)  # progress_percentage, status_message
    finished = Signal(bool, str, list)  # success, message, predictions
    image_ready = Signal(str)  # path to predicted image


class PredictionManager:
    """
    Singleton prediction manager that can be used by both DeepLearningPage and AssemblyDialog
    Uses the same prediction logic as DeepLearningPage
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not PredictionManager._initialized:
            self.current_model = None
            self.model_path = None
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.signals = PredictionSignals()
            self.cancel_flag = False  # Add this line
            PredictionManager._initialized = True

    def load_model(self, model_path):
        """Load a YOLO model - same as DeepLearningPage.load_model()"""
        try:
            if not model_path or not os.path.exists(model_path):
                return False, "Model file not found"

            # Load the model using ultralytics
            self.current_model = YOLO(model_path)
            self.model_path = model_path

            # Get model info
            model_name = os.path.basename(model_path)
            model_size = os.path.getsize(model_path) / (1024 * 1024)  # MB

            return True, f"✅ Model loaded successfully!\n\n• Model: {model_name}\n• Size: {model_size:.1f} MB\n• Device: {self.device}"

        except ImportError as e:
            error_msg = (
                f"Failed to import required libraries:\n{str(e)}\n\n"
                f"Please install required packages:\n"
                f"pip install ultralytics torch torchvision\n\n"
                f"For GPU support:\n"
                f"pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118"
            )
            return False, error_msg
        except Exception as e:
            return False, f"Failed to load model:\n{str(e)}"

    def predict_image(self, image_path, class_filter=None, progress_callback=None, conf_threshold=0.25):
        """Run prediction on an image - with debug output"""
        if not self.current_model:
            return False, "No model loaded", [], None

        if not os.path.exists(image_path):
            return False, f"Image not found: {image_path}", [], None

        try:
            if progress_callback:
                progress_callback(10, "Starting prediction...")

            # Prepare class filter
            classes_param = None
            if class_filter is not None:
                classes_param = [int(class_filter)] if isinstance(class_filter, (int, str)) else [int(c) for c in
                                                                                                  class_filter]

            print(f"DEBUG: Predict - Class filter: {classes_param}")

            # Run prediction
            results = self.current_model(
                source=image_path,
                conf=conf_threshold,
                iou=0.45,
                device=self.device,
                save=False,
                save_txt=False,
                save_conf=True,
                show=False,
                verbose=False,
                classes=classes_param
            )

            if progress_callback:
                progress_callback(70, "Processing results...")

            # Extract predictions
            predictions = []
            if results and len(results) > 0:
                result = results[0]
                if hasattr(result, 'boxes') and result.boxes is not None:
                    boxes = result.boxes
                    num_detections = len(boxes) if boxes is not None else 0
                    print(f"DEBUG: Found {num_detections} detections")

                    for i in range(num_detections):
                        try:
                            # Get box coordinates
                            if hasattr(boxes, 'xyxy') and boxes.xyxy is not None and len(boxes.xyxy) > i:
                                box = boxes.xyxy[i].cpu().numpy()
                            else:
                                continue

                            # Get confidence
                            if hasattr(boxes, 'conf') and boxes.conf is not None and len(boxes.conf) > i:
                                conf = boxes.conf[i].cpu().numpy()
                            else:
                                conf = 0.0

                            # Get class ID
                            if hasattr(boxes, 'cls') and boxes.cls is not None and len(boxes.cls) > i:
                                cls = boxes.cls[i].cpu().numpy()
                                cls_int = int(cls.item()) if hasattr(cls, 'item') else int(cls)
                            else:
                                cls_int = 0

                            # Get class name
                            class_name = f"class_{cls_int}"
                            if hasattr(result, 'names') and result.names:
                                class_name = result.names.get(cls_int, f"class_{cls_int}")

                            predictions.append({
                                'bbox': box.tolist(),
                                'confidence': float(conf),
                                'class_id': cls_int,
                                'class_name': class_name
                            })
                        except Exception as e:
                            print(f"Error processing detection {i}: {e}")
                            continue

            if progress_callback:
                progress_callback(90, "Saving results...")

            # Save annotated image
            output_path = self.save_prediction_image(image_path, results)
            print(f"DEBUG: Saved prediction image to: {output_path}")

            if progress_callback:
                progress_callback(100, "Done!")

            return True, f"Found {len(predictions)} objects", predictions, output_path

        except Exception as e:
            print(f"Prediction error: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Prediction failed: {str(e)}", [], None

    def get_class_id_by_name(self, class_name):
        """Find class ID by name with smarter normalization and partial matching"""
        if not self.current_model or not hasattr(self.current_model, 'names'):
            print("DEBUG: No model loaded or no class names available")
            return None

        import re

        original = class_name.strip()
        print(f"DEBUG: Looking for class matching '{original}'")
        print(f"DEBUG: Available classes: {list(self.current_model.names.values())}")

        # Step 1: remove numeric prefix like "1_", "2_", etc.
        cleaned = re.sub(r'^\d+_', '', original).strip()
        print(f"DEBUG: Cleaned input = '{cleaned}'")

        # Step 2: exact match
        for class_id, name in self.current_model.names.items():
            if cleaned.lower() == name.lower():
                print(f"DEBUG: ✓ Exact match! Class {class_id}: '{name}'")
                return class_id

        # Step 3: input contained in model class
        for class_id, name in self.current_model.names.items():
            if cleaned.lower() in name.lower():
                print(f"DEBUG: ✓ Partial match! Class {class_id}: '{name}' contains '{cleaned}'")
                return class_id

        # Step 4: compare normalized alphanumeric only
        def normalize(s):
            return re.sub(r'[^a-zA-Z0-9]', '', s).lower()

        cleaned_norm = normalize(cleaned)
        print(f"DEBUG: Normalized input = '{cleaned_norm}'")

        for class_id, name in self.current_model.names.items():
            name_norm = normalize(name)
            if cleaned_norm == name_norm:
                print(f"DEBUG: ✓ Normalized exact match! Class {class_id}: '{name}'")
                return class_id

        # Step 5: normalized partial match
        for class_id, name in self.current_model.names.items():
            name_norm = normalize(name)
            if cleaned_norm in name_norm:
                print(f"DEBUG: ✓ Normalized partial match! Class {class_id}: '{name}'")
                return class_id

        print(f"DEBUG: ✗ No matching class found for '{original}'")
        return None

    def cancel_prediction(self):
        """Cancel ongoing prediction"""
        self.cancel_flag = True

    def save_prediction_image(self, image_path, results):
        """Save image with predictions"""
        if not results or len(results) == 0:
            print("DEBUG: No results to save")
            return None

        try:
            # Create predictions folder
            output_dir = os.path.join(os.path.dirname(image_path), "predictions")
            os.makedirs(output_dir, exist_ok=True)
            print(f"DEBUG: Created output directory: {output_dir}")

            # Generate output filename
            base_name = os.path.basename(image_path)
            name, ext = os.path.splitext(base_name)
            output_filename = f"pred_{name}{ext}"
            output_path = os.path.join(output_dir, output_filename)

            # Ensure unique filename
            count = 1
            while os.path.exists(output_path):
                output_path = os.path.join(output_dir, f"pred_{name}_{count}{ext}")
                count += 1

            print(f"DEBUG: Saving to: {output_path}")

            # Save the result
            if results and len(results) > 0:
                # Try plot() method first
                try:
                    plotted = results[0].plot()
                    import cv2
                    cv2.imwrite(output_path, plotted)
                    print(f"DEBUG: Saved using plot() method")
                    return output_path
                except:
                    # Fallback to save() method
                    results[0].save(filename=output_path)
                    print(f"DEBUG: Saved using save() method")
                    return output_path

        except Exception as e:
            print(f"Error saving prediction image: {e}")
            import traceback
            traceback.print_exc()

        return None

    def debug_print_classes(self):
        """Print all available classes in the loaded model"""
        if not self.current_model:
            print("DEBUG: No model loaded")
            return {}

        if hasattr(self.current_model, 'names'):
            print("\n" + "=" * 50)
            print(f"📋 AVAILABLE CLASSES IN MODEL: {self.model_path}")
            print("=" * 50)
            for class_id, class_name in self.current_model.names.items():
                print(f"  Class {class_id}: '{class_name}'")
            print("=" * 50 + "\n")
            return self.current_model.names
        else:
            print("DEBUG: Model has no 'names' attribute")
            return {}

    def get_model_info(self):
        """Get information about loaded model"""
        if not self.model_path:
            return "No model loaded"

        try:
            model_name = os.path.basename(self.model_path)
            if os.path.exists(self.model_path):
                model_size = os.path.getsize(self.model_path) / (1024 * 1024)  # MB
                return f"{model_name} ({model_size:.1f} MB) on {self.device}"
            else:
                return f"{model_name} (file not found)"
        except:
            return "Error getting model info"

    def is_model_loaded(self):
        """Check if a model is loaded"""
        return self.current_model is not None

    def get_loaded_model_path(self):
        """Get path of loaded model"""
        return self.model_path

    def clear_model(self):
        """Clear loaded model"""
        self.current_model = None
        self.model_path = None

    def reset(self):
        """Reset the prediction manager to initial state"""
        self.current_model = None
        self.model_path = None
        self.cancel_flag = False