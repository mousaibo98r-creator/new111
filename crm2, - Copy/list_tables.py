import requests
import os
from dotenv import load_dotenv

load_dotenv()

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_SERVICE_KEY")

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}"
}

try:
    # Get OpenAPI spec which lists available tables
    response = requests.get(f"{URL}/rest/v1/", headers=headers)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        paths = data.get("paths", {}).keys()
        print("Available tables/paths:")
        for path in paths:
            print(f" - {path}")
    else:
        print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
