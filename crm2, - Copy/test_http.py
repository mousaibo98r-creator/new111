import requests
import os
from dotenv import load_dotenv

load_dotenv()

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_SERVICE_KEY")

print(f"Testing URL: {URL}")
print(f"Testing KEY prefix: {KEY[:10]}...")

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}"
}

try:
    response = requests.get(f"{URL}/rest/v1/mousa?select=count", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
