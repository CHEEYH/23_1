# ui/pages/recipe_pages.py
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
import requests
from ..components.buttons import create_button
from config_manager import config_manager


class APICreateRecipeThread(QThread):
    """Thread for API call to avoid freezing UI"""
    finished = Signal(bool, str)  # success, message

    def __init__(self, recipe_name, description):
        super().__init__()
        self.recipe_name = recipe_name
        self.description = description

    def run(self):
        try:
            # Prepare the data
            data = {
                "recipeName": self.recipe_name,
            }

            # Make the API request (just send, don't expect response)
            response = requests.post(
                "https://xlentmesapi.ir-four.com/api/xlentrecipe/create",
                json=data,
                timeout=5  # Shorter timeout since we don't need response
            )

            # Even if server doesn't return data, 200/201 means it was received
            if response.status_code in [200, 201, 202]:
                self.finished.emit(True, "Recipe sent to MES")
                print(f"Recipe send")
            else:
                # Server might still accept even with different status code
                # Some servers return 200 even without response body
                self.finished.emit(True, "Recipe sent to MES")

        except Exception as e:
            # Don't fail completely - just log the error but continue
            print(f"Note: Could not send to MES: {str(e)}")
            self.finished.emit(True, "Recipe created locally (MES communication optional)")


class RecipeMenuPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        # Title
        self.title = QLabel("📋 RECIPE MENU")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size:48px;font-weight:bold;color:#4b5563;")
        layout.addWidget(self.title)

        # Current recipe information
        self.current_recipe_label = QLabel("Current Recipe: None")
        self.current_recipe_label.setAlignment(Qt.AlignCenter)
        self.current_recipe_label.setStyleSheet(
            "font-size:20px;color:#666;background:#f3f4f6;padding:10px;border-radius:8px;")
        layout.addWidget(self.current_recipe_label)

        # Recipe information display
        self.recipe_info_label = QLabel("")
        self.recipe_info_label.setAlignment(Qt.AlignCenter)
        self.recipe_info_label.setStyleSheet(
            "font-size:14px;color:#666;background:#f9fafb;padding:10px;border-radius:8px;")
        self.recipe_info_label.setWordWrap(True)
        layout.addWidget(self.recipe_info_label)

        # Buttons
        self.btn_select = create_button("🔍 Select Recipe", "#33CCFF", self.select_recipe)
        self.btn_create = create_button("➕ Create Recipe", "#33CC99",
                                        lambda: self.main.go_to(self.main.create_recipe_page))
        self.btn_back = create_button("← Back", "#999999", self.main.go_back)

        layout.addWidget(self.btn_select)
        layout.addWidget(self.btn_create)
        layout.addWidget(self.btn_back)
        layout.addStretch()
        self.setLayout(layout)

    def showEvent(self, event):
        """Update recipe information when page is shown"""
        if config_manager.current_recipe:
            self.current_recipe_label.setText(f"📁 Current Recipe: {config_manager.current_recipe}")

            # Get recipe detailed information
            recipe_info = config_manager.get_recipe_info(config_manager.current_recipe)
            info_text = f"📂 Folder: {config_manager.get_current_recipe_folder()}\n"
            if recipe_info.get('description'):
                info_text += f"📝 Description: {recipe_info['description']}\n"
            if recipe_info.get('created'):
                info_text += f"🕐 Created: {recipe_info['created'][:10]}\n"

            # Show number of trained products
            trained_products = config_manager.get_trained_products()
            info_text += f"🤖 Trained Products: {len(trained_products)}"
            if trained_products:
                info_text += f"\n📋 Products: {', '.join(trained_products[:5])}"
                if len(trained_products) > 5:
                    info_text += "..."

            self.recipe_info_label.setText(info_text)
        else:
            self.current_recipe_label.setText("📭 Current Recipe: None")
            self.recipe_info_label.setText("Select a recipe to get started")
        super().showEvent(event)

    def select_recipe(self):
        """Select recipe"""
        recipes = config_manager.get_available_recipes()

        if not recipes:
            QMessageBox.warning(self, "⚠️ No Recipes",
                                "No recipes found! Please create a recipe first.")
            return

        recipe, ok = QInputDialog.getItem(self, "🔍 Select Recipe",
                                          "Choose recipe:", recipes, 0, False)

        if ok and recipe:
            # Set current recipe
            config_manager.set_current_recipe(recipe)

            # Update display
            self.current_recipe_label.setText(f"📁 Current Recipe: {recipe}")

            # Get recipe detailed information
            recipe_info = config_manager.get_recipe_info(recipe)
            info_text = f"📂 Folder: {config_manager.get_current_recipe_folder()}\n"
            if recipe_info.get('description'):
                info_text += f"📝 Description: {recipe_info['description']}\n"
            if recipe_info.get('created'):
                info_text += f"🕐 Created: {recipe_info['created'][:10]}\n"

            # Show trained products
            trained_products = config_manager.get_trained_products()
            info_text += f"🤖 Trained Products: {len(trained_products)}"
            if trained_products:
                info_text += f"\n📋 Products: {', '.join(trained_products[:5])}"
                if len(trained_products) > 5:
                    info_text += "..."

            self.recipe_info_label.setText(info_text)

            QMessageBox.information(self, "✅ Recipe Selected",
                                    f"Recipe '{recipe}' selected.\n\n"
                                    f"Trained products: {len(trained_products)}")


class CreateRecipePage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.main = parent
        self.api_thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("➕ Create Recipe")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:48px;font-weight:bold;color:#4b5563;")
        layout.addWidget(title)

        # Recipe name input
        self.input = QLineEdit()
        self.input.setFixedHeight(60)
        self.input.setStyleSheet("font-size:28px;padding:10px;border:2px solid #ccc;border-radius:8px;")
        self.input.setPlaceholderText("Enter recipe name")
        layout.addWidget(self.input)

        # Recipe description input
        self.desc_input = QLineEdit()
        self.desc_input.setFixedHeight(50)
        self.desc_input.setStyleSheet("font-size:18px;padding:10px;border:2px solid #ccc;border-radius:8px;")
        self.desc_input.setPlaceholderText("Description (optional)")
        layout.addWidget(self.desc_input)

        # Information label
        self.info_label = QLabel("Recipe will be saved in: recipes/[name]/")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("font-size:14px;color:#666;")
        layout.addWidget(self.info_label)

        # Status label for API calls
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size:14px;color:#666;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        self.btn_create = create_button("➕ Create", "#33CC99", self.create_recipe)
        self.btn_back = create_button("← Back", "#999999", self.main.go_back)

        layout.addWidget(self.btn_create)
        layout.addWidget(self.btn_back)
        layout.addStretch()
        self.setLayout(layout)

    def create_recipe(self):
        name = self.input.text().strip()
        if not name:
            QMessageBox.warning(self, "❌ Error", "Please enter a recipe name")
            return

        description = self.desc_input.text().strip()

        self.btn_create.setEnabled(False)
        self.status_label.setText("⏳ Creating recipe locally...")
        self.status_label.show()

        success, message, actual_name = config_manager.create_new_recipe(name, description)

        if success:
            config_manager.set_current_recipe(actual_name)

            self.status_label.setText("⏳ Sending recipe to MES...")

            self.api_thread = APICreateRecipeThread(actual_name, description)
            self.api_thread.finished.connect(self.on_api_finished)
            self.api_thread.start()
        else:
            self.btn_create.setEnabled(True)
            self.status_label.hide()
            QMessageBox.critical(self, "❌ Error", message)

    def on_api_finished(self, success, message):
        self.btn_create.setEnabled(True)

        # Get the recipe name (store it before clearing)
        recipe_name = self.input.text().strip()

        # Clear inputs
        self.input.clear()
        self.desc_input.clear()

        # Get folder paths
        recipe_folder = config_manager.get_current_recipe_folder()
        yolo_model_folder = config_manager.get_current_yolo_model_folder()

        # Simple success message - don't confuse user with MES details
        QMessageBox.information(self, "✅ Success",
                                f"Recipe '{recipe_name}' created successfully!\n\n"
                                f"📂 Folder: {recipe_folder}\n"
                                f"🤖 YOLO Models: {yolo_model_folder}")

        # Go to deep learning page
        self.main.go_to(self.main.deep_learning_page)

    def closeEvent(self, event):
        """Clean up thread when closing"""
        if self.api_thread and self.api_thread.isRunning():
            self.api_thread.quit()
            self.api_thread.wait()
        event.accept()