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
    response = requests.get(f"{URL}/rest/v1/", headers=headers)
    if response.status_code == 200:
        data = response.json()
        definitions = data.get("definitions", {})
        logs_def = definitions.get("logs", {})
        properties = logs_def.get("properties", {}).keys()
        print(f"Logs columns: {list(properties)}")
    else:
        print(f"Error: {response.status_code} - {response.text}")
except Exception as e:
    print(f"Error: {e}")
