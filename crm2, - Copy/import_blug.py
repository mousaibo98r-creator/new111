"""
import_blug.py — Import data from blug.json into Supabase 'mousa' table.
"""

from __future__ import annotations

import os
import json
import logging
import db

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("import_blug")

JSON_PATH = r"c:\Users\salah\OneDrive\Desktop\crm2,\blug.json"

def clean_val(val) -> list[str]:
    """Parse list or string to return a list of clean strings."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(item).strip() for item in val if item]
    
    val_str = str(val).strip()
    if not val_str:
        return []
    return [val_str]

def main():
    if not os.path.exists(JSON_PATH):
        logger.error(f"JSON file not found at: {JSON_PATH}")
        return

    logger.info(f"Reading JSON: {JSON_PATH}")
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read JSON: {e}")
        return

    # 1. Fetch existing emails from the database to prevent duplicate crashes
    logger.info("Fetching existing emails from database...")
    try:
        client = db.get_client()
        response = client.table("mousa").select("email").execute()
        existing_emails = {r["email"].strip().lower() for r in response.data} if response.data else set()
        logger.info(f"Found {len(existing_emails)} existing email(s) in database.")
    except Exception as e:
        logger.error(f"Failed to query existing emails: {e}")
        return

    leads_to_create = []
    seen_in_json = set()

    logger.info(f"Processing {len(data)} items...")

    for item in data:
        buyer = item.get("Buyer")
        if not buyer:
            continue
        
        company = str(buyer).strip()
        name = company # Set contact name to company name by default
        
        # Get emails (can be string or list)
        emails = clean_val(item.get("Email"))
        
        # Parse country, website, phone, address, invoices, USD
        country = item.get("Country", "")
        invoices = item.get("Invoices", "")
        usd = item.get("USD", "")
        
        websites = clean_val(item.get("Website"))
        phones = clean_val(item.get("Phone"))
        addresses = clean_val(item.get("Address"))
        
        # Construct notes
        notes_parts = []
        if country:
            notes_parts.append(f"Country: {country}")
        if invoices:
            notes_parts.append(f"Invoices: {invoices}")
        if usd:
            notes_parts.append(f"USD Volume: {usd}")
        if websites:
            notes_parts.append(f"Website(s): {', '.join(websites)}")
        if phones:
            notes_parts.append(f"Phone(s): {', '.join(phones)}")
        if addresses:
            notes_parts.append(f"Address(es): {'; '.join(addresses)}")
            
        notes = "\n".join(notes_parts)

        # For each email, create a separate lead
        for email in emails:
            email_clean = email.strip().lower()
            if '@' not in email_clean or '.' not in email_clean:
                continue
                
            # Skip if already in database or already seen in this JSON parsing run
            if email_clean in existing_emails or email_clean in seen_in_json:
                continue
                
            seen_in_json.add(email_clean)
            
            leads_to_create.append({
                "name": name,
                "company": company,
                "email": email_clean,
                "status": "new",
                "notes": notes,
                "industry": "Aluminum Industry"
            })

    if not leads_to_create:
        logger.warning("No new unique leads found to import.")
        return

    logger.info(f"Found {len(leads_to_create)} new unique leads to upload. Uploading in batches...")

    # Upload in batches of 100
    BATCH_SIZE = 100
    success_count = 0
    
    for i in range(0, len(leads_to_create), BATCH_SIZE):
        batch = leads_to_create[i : i + BATCH_SIZE]
        try:
            db.bulk_create_leads(batch)
            success_count += len(batch)
            logger.info(f"Progress: {success_count}/{len(leads_to_create)} uploaded...")
        except Exception as e:
            logger.error(f"Error uploading batch at index {i}: {e}")

    logger.info(f"Done! Successfully imported {success_count} leads to Supabase 'mousa' table.")

if __name__ == "__main__":
    main()
