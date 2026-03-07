import requests
import json
job_id=456
recipe_name=123

def stop_latest_workorder(job_id, recipe_name):
    url = "http://127.0.0.1:5000/api/UpdateworkorderStatus/stop-latest"
    payload = {"workOrder": str(job_id), "recipe": str(recipe_name)}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()  # Check for HTTP errors
        return response.json()  # Return parsed JSON response
    except Exception as e:
        print(f"API call failed: {e}")
        return None