"""
import_csv.py — Script to push data from the exported CSV to Supabase using direct HTTP requests.
(Workaround for SDK key format issues)
"""

import pandas as pd
import json
import requests
import logging
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CSV_PATH = "2026-05-14T14-12_export.csv"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

def parse_json_list(val: str) -> List[str]:
    """Parse JSON strings or handle raw text into a list of strings."""
    if pd.isna(val) or not val:
        return []
    
    val_str = str(val).strip()
    if not val_str:
        return []
        
    try:
        if val_str.startswith('[') and val_str.endswith(']'):
            data = json.loads(val_str)
            if isinstance(data, list):
                return [str(item) for item in data if item]
        if ';' in val_str:
            return [s.strip() for s in val_str.split(';') if s.strip()]
        return [val_str]
    except Exception:
        return [val_str]

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY missing from .env")
        return

    if not os.path.exists(CSV_PATH):
        logger.error(f"CSV file not found at: {CSV_PATH}")
        return

    logger.info(f"Reading CSV: {CSV_PATH}")
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return

    leads_to_create = []
    seen_emails = set()

    logger.info(f"Processing {len(df)} rows...")

    for idx, row in df.iterrows():
        raw_emails = parse_json_list(row.get('Email', ''))
        if not raw_emails:
            continue
            
        email = None
        for e in raw_emails:
            e_clean = e.strip().lower()
            if '@' in e_clean and '.' in e_clean:
                email = e_clean
                break
        
        if not email or email in seen_emails:
            continue
        
        seen_emails.add(email)

        name = str(row.get('Buyer', 'Unknown Contact')).strip()
        company = name
        
        notes_parts = []
        for field in ['Country', 'Invoices', 'USD', 'Website', 'Phone', 'Address']:
            val = row.get(field)
            if pd.notna(val) and str(val).strip():
                if str(val).startswith('['):
                    val_list = parse_json_list(str(val))
                    val = ", ".join(val_list)
                notes_parts.append(f"{field}: {val}")
        
        notes = "\n".join(notes_parts)

        leads_to_create.append({
            "name": name,
            "company": company,
            "email": email,
            "status": "new",
            "notes": notes,
            "industry": "Aluminum Industry" 
        })

    if not leads_to_create:
        logger.warning("No valid new leads found to import.")
        return

    logger.info(f"Found {len(leads_to_create)} valid leads. Uploading to Supabase via PostgREST...")

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    BATCH_SIZE = 100
    success_count = 0
    
    # We will try to push to 'mousa' table as per instructions
    for i in range(0, len(leads_to_create), BATCH_SIZE):
        batch = leads_to_create[i : i + BATCH_SIZE]
        try:
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/mousa",
                headers=headers,
                json=batch
            )
            
            if response.status_code in [201, 204]:
                success_count += len(batch)
                logger.info(f"Progress: {success_count}/{len(leads_to_create)} uploaded.")
            else:
                logger.error(f"Error uploading batch at index {i}: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Request failed: {e}")

    logger.info(f"Done! Successfully imported {success_count} leads.")

if __name__ == "__main__":
    main()
