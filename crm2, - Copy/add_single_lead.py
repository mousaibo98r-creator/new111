import requests
import os
from dotenv import load_dotenv

load_dotenv()

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_SERVICE_KEY")

headers = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

payload = {
    "name": "mousaibo97r",
    "company": "Personal",
    "email": "mousaibo97r@gmail.com",
    "status": "new"
}

try:
    response = requests.post(f"{URL}/rest/v1/mousa", headers=headers, json=payload)
    if response.status_code in [201, 204]:
        print("Success: Lead added.")
    else:
        print(f"Error: {response.status_code} - {response.text}")
except Exception as e:
    print(f"Error: {e}")
