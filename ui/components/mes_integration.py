# ui/components/mes_integration.py

import requests
import json
from datetime import datetime
from typing import Dict, List, Optional


class MESIntegration:
    """MES System Integration"""

    def __init__(self, api_url: str = None):
        # Point to local test server
        self.api_url = api_url or "http://localhost:5000/api"
        self.connected = False
        self.last_sync = None

    def check_connection(self) -> bool:
        """Check MES connection"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=3)
            self.connected = response.status_code == 200
            return self.connected
        except:
            self.connected = False
            return False

    # In mes_integration.py

    def get_inventory(self, part_numbers: List[str] = None) -> Dict[str, int]:
        """Get inventory for specified parts"""
        if not self.check_connection():
            return self.get_local_inventory()

        try:
            params = {}
            if part_numbers:
                params['parts'] = ','.join(part_numbers)
                print(f"DEBUG: Requesting inventory for parts: {part_numbers}")
            else:
                print(f"DEBUG: Requesting all inventory")

            response = requests.get(
                f"{self.api_url}/inventory",
                params=params,
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                self.last_sync = datetime.now()
                inventory = data.get('inventory', {})
                print(f"DEBUG: Received inventory: {inventory}")
                return inventory
        except Exception as e:
            print(f"Inventory fetch error: {e}")

        return self.get_local_inventory()

    def get_today_jobs(self, recipe_name: str = None) -> List[Dict]:
        """Get today's production jobs"""
        if not self.check_connection():
            return []

        try:
            params = {}
            if recipe_name:
                params['recipe'] = recipe_name

            response = requests.get(
                f"{self.api_url}/jobs/today",
                params=params,
                timeout=5
            )

            if response.status_code == 200:
                return response.json().get('jobs', [])
        except Exception as e:
            print(f"Jobs fetch error: {e}")

        return []

    def get_recipe_bom(self, recipe_name: str) -> Dict[str, int]:
        """Get Bill of Materials for a recipe"""
        if not self.check_connection():
            # Return default BOM
            return {"A": 1, "B": 1, "C": 1}

        try:
            response = requests.get(
                f"{self.api_url}/recipes/{recipe_name}/bom",
                timeout=5
            )

            if response.status_code == 200:
                return response.json().get('bom', {})
        except Exception as e:
            print(f"BOM fetch error: {e}")

        return {"A": 1, "B": 1, "C": 1}

    def get_part_numbers(self, recipe_name: str = None) -> List[str]:
        """Get all part numbers needed for current recipe"""
        if not self.check_connection():
            return ['A', 'B', 'C']  # Default fallback

        try:
            if recipe_name:
                # Get BOM from recipe to get all parts
                bom = self.get_recipe_bom(recipe_name)
                return list(bom.keys())
            else:
                # Get all available parts
                response = requests.get(f"{self.api_url}/parts", timeout=5)
                if response.status_code == 200:
                    return response.json().get('parts', [])
        except Exception as e:
            print(f"Part numbers fetch error: {e}")

        return ['A', 'B', 'C']  # Default fallback

    def report_completion(self, job_data: Dict) -> bool:
        """Report job completion to MES"""
        if not self.check_connection():
            return False

        try:
            response = requests.post(
                f"{self.api_url}/jobs/complete",
                json=job_data,
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Completion report error: {e}")
            return False

    def get_local_inventory(self) -> Dict[str, int]:
        """Get locally cached inventory"""
        try:
            with open('local_inventory.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Local inventory load error: {e}")
            return {"A": 0, "B": 0, "C": 0}

    def save_local_inventory(self, inventory: Dict[str, int]):
        """Save inventory to local cache"""
        try:
            with open('local_inventory.json', 'w') as f:
                json.dump(inventory, f, indent=2)
        except Exception as e:
            print(f"Local inventory save error: {e}")