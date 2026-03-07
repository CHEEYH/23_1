import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigManager:
    """Configuration manager for the application"""

    def __init__(self):
        self.config_data = {}
        self.current_recipe = None
        self.load_config()

    # ================== File Path Utilities ==================

    def _get_config_path(self) -> str:
        """Get the absolute path to config.json"""
        return os.path.join(os.path.dirname(__file__), 'config.json')

    def _get_recipes_path(self) -> str:
        """Get the absolute path to recipes directory"""
        return os.path.join(os.path.dirname(__file__), 'recipes')

    def _ensure_recipes_dir(self) -> bool:
        """Ensure recipes directory exists"""
        try:
            recipes_path = self._get_recipes_path()
            os.makedirs(recipes_path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create recipes directory: {e}")
            return False

    def _get_recipe_info_path(self, recipe_name: str) -> Optional[str]:
        """Get the path to a recipe's info file"""
        recipe_folder = self.get_recipe_folder(recipe_name)
        if recipe_folder:
            return os.path.join(recipe_folder, 'recipe_info.json')
        return None

    # ================== Config File Management ==================

    def load_config(self):
        """Load configuration from config.json"""
        config_path = self._get_config_path()
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
                logger.info(f"✅ Loaded config from {config_path}")
            else:
                logger.warning(f"⚠️ Config file not found at {config_path}, using defaults")
                self.config_data = {
                    'mes_api': {
                        'url': 'http://127.0.0.1:5000/api',
                        'timeout': 5
                    },
                    'tcp': {
                        'server': '127.0.0.1',
                        'port': 8888
                    }
                }
                self.save_config()

            # Restore current recipe from config
            saved_recipe = self.config_data.get('current_recipe')
            if saved_recipe in self.get_available_recipes():
                self.current_recipe = saved_recipe
            else:
                self.current_recipe = None

        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            self.config_data = {}
            self.current_recipe = None

    # https: // xlentmesapi.ir - four.com / api
    def save_config(self):
        """Save configuration to config.json"""
        config_path = self._get_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Saved config to {config_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Error saving config: {e}")
            return False

    # ================== MES API Methods ==================

    def get_mes_api_url(self) -> str:
        """Get MES API URL from config"""
        return self.config_data.get('mes_api', {}).get('url', 'http://127.0.0.1:5000/api')

    def get_mes_api_timeout(self) -> int:
        """Get MES API timeout from config"""
        return self.config_data.get('mes_api', {}).get('timeout', 5)

    def set_mes_api_url(self, url: str) -> bool:
        """Set MES API URL in config"""
        if 'mes_api' not in self.config_data:
            self.config_data['mes_api'] = {}
        self.config_data['mes_api']['url'] = url
        return self.save_config()

    def set_mes_api_timeout(self, timeout: int) -> bool:
        """Set MES API timeout in config"""
        if 'mes_api' not in self.config_data:
            self.config_data['mes_api'] = {}
        self.config_data['mes_api']['timeout'] = timeout
        return self.save_config()

    # ================== TCP Server Methods ==================

    def get_tcp_server(self) -> str:
        """Get TCP server IP from config"""
        return self.config_data.get('tcp', {}).get('server', '127.0.0.1')

    def get_tcp_port(self) -> int:
        """Get TCP server port from config"""
        return self.config_data.get('tcp', {}).get('port', 8888)

    def set_tcp_server(self, server: str) -> bool:
        """Set TCP server IP in config"""
        if 'tcp' not in self.config_data:
            self.config_data['tcp'] = {}
        self.config_data['tcp']['server'] = server
        return self.save_config()

    def set_tcp_port(self, port: int) -> bool:
        """Set TCP server port in config"""
        if 'tcp' not in self.config_data:
            self.config_data['tcp'] = {}
        self.config_data['tcp']['port'] = port
        return self.save_config()

    # ================== Recipe Methods ==================

    def get_available_recipes(self) -> List[str]:
        """Get list of available recipes"""
        if not self._ensure_recipes_dir():
            return []

        recipes = []
        try:
            recipes_path = self._get_recipes_path()
            for item in os.listdir(recipes_path):
                item_path = os.path.join(recipes_path, item)
                if os.path.isdir(item_path):
                    recipes.append(item)
        except Exception as e:
            logger.error(f"Error listing recipes: {e}")

        return sorted(recipes)

    def get_recipe_folder(self, recipe_name: str) -> Optional[str]:
        """Get folder path for a recipe"""
        if not recipe_name:
            return None

        recipes_path = self._get_recipes_path()
        recipe_folder = os.path.join(recipes_path, recipe_name)

        if os.path.exists(recipe_folder) and os.path.isdir(recipe_folder):
            return recipe_folder

        return None

    def set_current_recipe(self, recipe_name: str):
        """Set current recipe"""
        if recipe_name in self.get_available_recipes():
            self.current_recipe = recipe_name
            self.config_data['current_recipe'] = recipe_name
            self.save_config()
            logger.info(f"Current recipe set to: {recipe_name}")
            return True
        else:
            logger.warning(f"Attempted to set invalid recipe: {recipe_name}")
            return False

    def get_current_recipe_folder(self) -> Optional[str]:
        """Get folder path for current recipe"""
        return self.get_recipe_folder(self.current_recipe)

    def get_current_yolo_dataset_folder(self):
        """Get current recipe YOLO dataset folder path"""
        if not self.current_recipe:
            return None
        return os.path.join(self.get_current_recipe_folder(), "yolo_dataset")

    def get_current_yolo_model_folder(self) -> Optional[str]:
        """Get YOLO models folder for current recipe"""
        recipe_folder = self.get_current_recipe_folder()
        if recipe_folder:
            yolo_folder = os.path.join(recipe_folder, 'yolo_model')
            try:
                os.makedirs(yolo_folder, exist_ok=True)
                return yolo_folder
            except Exception as e:
                logger.error(f"Error creating YOLO models folder: {e}")
                return None
        return None

    def create_new_recipe(self, name: str, description: str = "") -> Tuple[bool, str, Optional[str]]:
        """Create a new recipe folder and metadata file"""
        try:
            if not name or not name.strip():
                return False, "Recipe name cannot be empty", None

            # Clean recipe name (remove invalid characters)
            clean_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_', '.')).strip()

            if not clean_name:
                return False, "Recipe name is invalid after cleaning", None

            # Ensure recipes directory exists
            if not self._ensure_recipes_dir():
                return False, "Could not create recipes directory", None

            recipes_path = self._get_recipes_path()
            recipe_folder = os.path.join(recipes_path, clean_name)

            # Check if recipe already exists
            if os.path.exists(recipe_folder):
                return False, f"Recipe '{clean_name}' already exists", None

            # Create recipe folder
            os.makedirs(recipe_folder)
            logger.info(f"Created recipe folder: {recipe_folder}")

            # Create YOLO models subfolder
            yolo_folder = os.path.join(recipe_folder, 'yolo_models')
            os.makedirs(yolo_folder)
            logger.info(f"Created YOLO models folder: {yolo_folder}")

            # Create recipe metadata
            recipe_info = {
                'name': clean_name,
                'original_name': name,
                'description': description,
                'created': datetime.now().isoformat(),
                'last_modified': datetime.now().isoformat(),
                'trained_products': [],
                'settings': {}
            }

            info_path = os.path.join(recipe_folder, 'recipe_info.json')
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(recipe_info, f, indent=2, ensure_ascii=False)

            logger.info(f"Created recipe metadata: {info_path}")
            return True, f"Recipe '{clean_name}' created successfully", clean_name

        except Exception as e:
            logger.error(f"Error creating recipe: {e}")
            return False, f"Error creating recipe: {str(e)}", None

    def get_recipe_info(self, recipe_name: str = None) -> Dict[str, Any]:
        """Get recipe information from its metadata file"""
        if recipe_name is None:
            recipe_name = self.current_recipe

        if not recipe_name:
            return {}

        info_path = self._get_recipe_info_path(recipe_name)
        if not info_path or not os.path.exists(info_path):
            return {}

        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading recipe info for {recipe_name}: {e}")
            return {}

    def update_recipe_info(self, recipe_name: str, updates: Dict[str, Any]) -> bool:
        """Update specific fields in recipe info"""
        recipe_info = self.get_recipe_info(recipe_name)
        if not recipe_info:
            return False

        try:
            # Update the fields
            recipe_info.update(updates)
            recipe_info['last_modified'] = datetime.now().isoformat()

            # Save back to file
            info_path = self._get_recipe_info_path(recipe_name)
            if info_path:
                with open(info_path, 'w', encoding='utf-8') as f:
                    json.dump(recipe_info, f, indent=2, ensure_ascii=False)
                return True
        except Exception as e:
            logger.error(f"Error updating recipe info: {e}")

        return False

    # ================== Trained Products Methods ==================

    def get_trained_products(self, recipe_name: str = None) -> List[str]:
        """Get list of trained products for a recipe"""
        recipe_info = self.get_recipe_info(recipe_name)
        return recipe_info.get('trained_products', [])

    def add_trained_product(self, product_name: str, recipe_name: str = None) -> bool:
        """Add a trained product to recipe metadata"""
        if recipe_name is None:
            recipe_name = self.current_recipe

        if not recipe_name:
            logger.warning("No recipe selected to add trained product")
            return False

        recipe_info = self.get_recipe_info(recipe_name)
        if not recipe_info:
            return False

        # Get current trained products
        trained_products = recipe_info.get('trained_products', [])

        # Add if not already present
        if product_name not in trained_products:
            trained_products.append(product_name)
            return self.update_recipe_info(recipe_name, {'trained_products': trained_products})

        return True

    def remove_trained_product(self, product_name: str, recipe_name: str = None) -> bool:
        """Remove a trained product from recipe metadata"""
        if recipe_name is None:
            recipe_name = self.current_recipe

        if not recipe_name:
            return False

        recipe_info = self.get_recipe_info(recipe_name)
        if not recipe_info:
            return False

        trained_products = recipe_info.get('trained_products', [])
        if product_name in trained_products:
            trained_products.remove(product_name)
            return self.update_recipe_info(recipe_name, {'trained_products': trained_products})

        return True

    # ================== Recipe Settings Methods ==================

    def get_recipe_setting(self, key: str, default: Any = None, recipe_name: str = None) -> Any:
        """Get a specific setting for a recipe"""
        recipe_info = self.get_recipe_info(recipe_name)
        settings = recipe_info.get('settings', {})
        return settings.get(key, default)

    def set_recipe_setting(self, key: str, value: Any, recipe_name: str = None) -> bool:
        """Set a specific setting for a recipe"""
        if recipe_name is None:
            recipe_name = self.current_recipe

        if not recipe_name:
            return False

        recipe_info = self.get_recipe_info(recipe_name)
        if not recipe_info:
            return False

        settings = recipe_info.get('settings', {})
        settings[key] = value

        return self.update_recipe_info(recipe_name, {'settings': settings})

    # ================== Recipe Deletion ==================

    def delete_recipe(self, recipe_name: str) -> Tuple[bool, str]:
        """Delete a recipe folder and all its contents"""
        if not recipe_name:
            return False, "No recipe specified"

        recipe_folder = self.get_recipe_folder(recipe_name)
        if not recipe_folder:
            return False, f"Recipe '{recipe_name}' not found"

        try:
            # Check if this is the current recipe
            if self.current_recipe == recipe_name:
                self.current_recipe = None

            # Delete the entire recipe folder
            import shutil
            shutil.rmtree(recipe_folder)
            logger.info(f"Deleted recipe: {recipe_name}")
            return True, f"Recipe '{recipe_name}' deleted successfully"

        except Exception as e:
            logger.error(f"Error deleting recipe {recipe_name}: {e}")
            return False, f"Error deleting recipe: {str(e)}"

    # ================== Utility Methods ==================

    def get_all_recipes_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information for all available recipes"""
        recipes_info = {}
        for recipe_name in self.get_available_recipes():
            recipes_info[recipe_name] = self.get_recipe_info(recipe_name)
        return recipes_info

    def rename_recipe(self, old_name: str, new_name: str) -> Tuple[bool, str]:
        """Rename a recipe folder and update metadata"""
        if not old_name or not new_name:
            return False, "Recipe names cannot be empty"

        old_folder = self.get_recipe_folder(old_name)
        if not old_folder:
            return False, f"Recipe '{old_name}' not found"

        recipes_path = self._get_recipes_path()
        new_folder = os.path.join(recipes_path, new_name)

        if os.path.exists(new_folder):
            return False, f"Recipe '{new_name}' already exists"

        try:
            # Rename the folder
            os.rename(old_folder, new_folder)

            # Update the recipe info file
            info_path = os.path.join(new_folder, 'recipe_info.json')
            if os.path.exists(info_path):
                with open(info_path, 'r', encoding='utf-8') as f:
                    recipe_info = json.load(f)

                recipe_info['name'] = new_name
                recipe_info['last_modified'] = datetime.now().isoformat()

                with open(info_path, 'w', encoding='utf-8') as f:
                    json.dump(recipe_info, f, indent=2, ensure_ascii=False)

            # Update current recipe if needed
            if self.current_recipe == old_name:
                self.current_recipe = new_name

            return True, f"Recipe renamed to '{new_name}'"

        except Exception as e:
            logger.error(f"Error renaming recipe: {e}")
            return False, f"Error renaming recipe: {str(e)}"


# Create singleton instance
config_manager = ConfigManager()