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
    response = requests.get(f"{URL}/rest/v1/leads?limit=1", headers=headers)
    print(f"Leads structure: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
