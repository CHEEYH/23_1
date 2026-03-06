# ui/components/mes_client.py
from datetime import datetime

import requests
import json
from typing import Dict, List, Optional, Any


class MESClient:
    """Client for MES API to get pending parts with their UIDs"""

    def __init__(self, base_url: str = "https://xlentmesapi.ir-four.com/api"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.timeout = 5
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        print(f"🔧 MES Client initialized with URL: {self.base_url}")

        # Cache for pending parts
        self.pending_parts = []
        self.last_fetch = None

    def _fetch_pending_parts(self) -> list:
        try:
            url = f"{self.base_url}/GetPartNumberDetail/running"
            print(f"DEBUG _fetch_pending_parts URL: {url}")

            response = self.session.get(url, timeout=self.timeout)
            print(f"DEBUG status code: {response.status_code}")
            print(f"DEBUG response text: {response.text}")

            response.raise_for_status()
            data = response.json()

            flat_pending = []

            if isinstance(data, list):
                for job in data:
                    pending_list = job.get("pending", [])
                    if isinstance(pending_list, list):
                        flat_pending.extend(pending_list)

            elif isinstance(data, dict):
                pending_list = data.get("pending", [])
                if isinstance(pending_list, list):
                    flat_pending.extend(pending_list)

            print(f"DEBUG flattened pending parts: {flat_pending}")
            return flat_pending

        except Exception as e:
            print(f"❌ Failed to fetch pending parts: {e}")
            return []

    def get_part_uid(self, part_number: str) -> Optional[str]:
        pending = self._fetch_pending_parts()

        print(f"\n{'=' * 60}")
        print(f"🔍 Looking for UID of part: {repr(part_number)}")

        for part in pending:
            api_part = str(part.get('partNumber', '')).strip()
            api_uid = part.get('uid')
            print(f"DEBUG compare api_part={repr(api_part)} target={repr(part_number.strip())} uid={api_uid}")

            if api_part == part_number.strip():
                uid = api_uid
                print(f"✅ Found! Part {part_number} has UID: {uid}")
                print(f"   Full details: {part}")
                print(f"{'=' * 60}\n")
                return uid

        print(f"❌ Part {part_number} not found in pending list")
        print(f"{'=' * 60}\n")
        return None

    def get_all_pending_parts(self) -> List[Dict]:
        """Get all pending parts with their details"""
        return self._fetch_pending_parts()

    def get_part_details(self, part_number: str) -> Optional[Dict]:
        """Get full details for a specific part number"""
        pending = self._fetch_pending_parts()

        for part in pending:
            if part.get('partNumber') == part_number:
                return part

        return None

    def get_inventory(self, part_number: str) -> int:
        print(f"DEBUG get_inventory input: {repr(part_number)}")
        uid = self.get_part_uid(part_number)
        print(f"DEBUG get_inventory uid result: {uid}")
        return 1 if uid else 0

    def post_batch_assembly_results(self, assembled_parts: List[Dict]) -> bool:
        """
        Post multiple assembly results to MES
        Endpoint: /api/UpdatePartNumberUID/scan

        Args:
            assembled_parts: List of dicts with 'partNumber' and 'uid'

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not assembled_parts:
                print("⚠️ No assembled parts to post")
                return False

            # Validate payload format
            for i, part in enumerate(assembled_parts):
                if 'partNumber' not in part or 'uid' not in part:
                    print(f"❌ Invalid payload at index {i}: {part}")
                    print("   Expected keys: 'partNumber', 'uid'")
                    return False

            url = f"{self.base_url}/UpdatePartNumberUID/scan"
            print(f"\n{'=' * 60}")
            print("📤 POSTING UIDs to MES")
            print(f"URL: {url}")
            print(f"Data: {json.dumps(assembled_parts, indent=2)}")

            response = self.session.post(
                url,
                json=assembled_parts,
                timeout=self.timeout
            )

            print(f"Response Status: {response.status_code}")
            print(f"Response Body: {response.text}")

            if response.status_code in (200, 201, 202, 204):
                print(f"✅ Successfully posted {len(assembled_parts)} UIDs to MES")
                print(f"{'=' * 60}\n")
                return True
            else:
                print(f"❌ Failed to post UIDs. Status code: {response.status_code}")
                print(f"❌ Response: {response.text}")
                print(f"{'=' * 60}\n")
                return False

        except requests.exceptions.ConnectionError:
            print(f"❌ Connection Error: Cannot connect to {self.base_url}")
            print("   Make sure the MES server is running")
            print(f"{'=' * 60}\n")
            return False
        except requests.exceptions.Timeout:
            print(f"❌ Timeout Error: Server not responding within {self.timeout}s")
            print(f"{'=' * 60}\n")
            return False
        except Exception as e:
            print(f"❌ Unexpected Error: {e}")
            import traceback
            traceback.print_exc()
            print(f"{'=' * 60}\n")
            return False

    def deduct_inventory(self, part_number: str, quantity: int = 1) -> bool:
        """
        Mark a part as assembled by removing it from pending

        Note: This would need a POST endpoint to update the MES system
        """
        uid = self.get_part_uid(part_number)

        print(f"\n{'=' * 60}")
        print(f"💰 Part Assembly Complete")
        print(f"   Part Number: {part_number}")

        if uid:
            print(f"   UID: {uid}")
            print(f"   Would mark this UID as COMPLETED in MES")
            print(f"   ⚠️ API endpoint for updating status not available")
        else:
            print(f"   ⚠️ No UID found for part {part_number}")

        print(f"{'=' * 60}\n")
        return True  # Return True to not block assembly

    def test_connection(self) -> bool:
        """Test the API connection"""
        try:
            response = self.session.get(
                f"{self.base_url}/GetPartNumberDetail/running",
                timeout=self.timeout
            )
            return response.status_code == 200
        except:
            return False

    # In ui/components/mes_client.py, add this method:

    def get_current_recipe(self) -> Optional[str]:
        try:
            response = self.session.get(
                f"{self.base_url}/GetPartNumberDetail/running",
                timeout=self.timeout
            )

            if response.status_code == 200:
                raw_data = response.json()

                if isinstance(raw_data, list):
                    if len(raw_data) > 0 and isinstance(raw_data[0], dict):
                        data = raw_data[0]
                    else:
                        print("⚠️ Empty list returned from MES API")
                        return None
                elif isinstance(raw_data, dict):
                    data = raw_data
                else:
                    print(f"⚠️ Unexpected response type: {type(raw_data)}")
                    return None

                recipe_name = data.get('recipe')

                if recipe_name:
                    print(f"📋 API provides recipe: {recipe_name}")
                    return recipe_name
                else:
                    print("⚠️ No recipe found in API response")
                    return None
            else:
                print(f"⚠️ Failed to get recipe from API: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Error getting recipe from API: {e}")
            return None

    def get_running_job(self) -> Dict:
        try:
            url = f"{self.base_url}/GetPartNumberDetail/running"
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 200:
                raw_data = response.json()

                if isinstance(raw_data, list):
                    if raw_data and isinstance(raw_data[0], dict):
                        data = raw_data[0]
                    else:
                        print("⚠️ Running job API returned empty list")
                        return {}
                elif isinstance(raw_data, dict):
                    data = raw_data
                else:
                    print(f"⚠️ Unexpected response type: {type(raw_data)}")
                    return {}

                print(f"✅ Got running job data: {data}")
                return data
            else:
                print(f"⚠️ Failed to get running job: {response.status_code}")
                print(f"Response: {response.text}")

        except Exception as e:
            print(f"❌ Error getting running job: {e}")

        return {}

    def get_current_job_id(self) -> str:
        """
        Get current job ID from MES API.
        The job ID is stored in the 'title' field.

        Returns:
            str: Job ID from title field, or None if not available
        """
        job_data = self.get_running_job()

        # Extract job ID from 'title' field
        if job_data and 'workOrder' in job_data:
            job_id = job_data['workOrder']
            print(f"✅ Got job ID from MES title: {job_id}")
            return job_id

        print("⚠️ No job ID found in MES response")
        return None

    def get_job_details(self) -> Dict:
        """
        Get complete job details from running endpoint.
        Returns all fields from the API response.
        """
        return self.get_running_job()