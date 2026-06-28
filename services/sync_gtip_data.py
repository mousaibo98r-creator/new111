import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to sys.path so we can import services
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.supabase_client import get_client

def update_buyer(client, item):
    buyer_name = item["buyer_name"]
    retries = 3
    delay = 0.5
    
    for attempt in range(retries):
        try:
            resp = client.table("mousa").update({
                "gtip_aciklamasi": item["gtip_aciklamasi"],
                "esya_ticari_tanimi": item["esya_ticari_tanimi"]
            }).eq("buyer_name", buyer_name).execute()
            return buyer_name, True, len(resp.data) if resp.data else 0
        except Exception as e:
            # Check if socket error or temp error
            err_str = str(e)
            if "10035" in err_str or "socket" in err_str.lower() or attempt < retries - 1:
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                continue
            return buyer_name, False, err_str
    
    return buyer_name, False, "Max retries reached"

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    client = get_client()
    if not client:
        print("[Error] Supabase client could not be initialized.")
        return

    # Load JSON data
    json_path = r"c:\Users\salah\OneDrive\Desktop\website 4th time\enriched_export.json"
    if not os.path.exists(json_path):
        print(f"[Error] JSON file not found at: {json_path}")
        return

    print("[Info] Loading enriched_export.json...")
    with open(json_path, "r", encoding="utf-8") as f:
        export_data = json.load(f)
    print(f"[Success] Loaded {len(export_data)} records from JSON.")

    # Create mapping: buyer_name (normalized) -> data
    json_mapping = {}
    for entry in export_data:
        buyer = entry.get("Buyer")
        if buyer:
            buyer_norm = str(buyer).strip().lower()
            json_mapping[buyer_norm] = {
                "gtip": entry.get("GTIP Açıklaması"),
                "description": entry.get("Eşya Ticari Tanımı")
            }

    # Fetch all rows from Supabase 'mousa' table
    print("[Info] Fetching all buyers from Supabase table 'mousa'...")
    all_db_rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = client.table("mousa").select("buyer_name", "gtip_aciklamasi").range(offset, offset + page_size - 1).execute()
        if not resp.data:
            break
        all_db_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    print(f"[Success] Loaded {len(all_db_rows)} buyers from Supabase.")

    # Find matching records that need updates (skip if already has gtip_aciklamasi to save requests)
    updates = []
    for row in all_db_rows:
        buyer_name = row.get("buyer_name")
        if buyer_name:
            buyer_norm = str(buyer_name).strip().lower()
            if buyer_norm in json_mapping:
                item = json_mapping[buyer_norm]
                updates.append({
                    "buyer_name": buyer_name,
                    "gtip_aciklamasi": item["gtip"],
                    "esya_ticari_tanimi": item["description"]
                })

    print(f"[Info] Found {len(updates)} matching buyers that need updating.")

    if not updates:
        print("[Info] No matching buyers need updating.")
        return

    print(f"[Info] Starting sync of {len(updates)} records using parallel execution with 8 workers...")
    success_count = 0
    failed_count = 0

    # Run updates in parallel with 8 worker threads
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(update_buyer, client, item): item for item in updates}
        for idx, future in enumerate(as_completed(futures)):
            buyer_name, success, info = future.result()
            if success:
                success_count += 1
            else:
                failed_count += 1
                print(f"[Error] Failed to update '{buyer_name}': {info}")
            
            # Print progress every 50 items
            if (idx + 1) % 50 == 0:
                print(f"[Sync Progress] Processed {idx + 1}/{len(updates)} updates. Success: {success_count}, Failed: {failed_count}")

    print(f"[Success] Sync completed! Successfully updated {success_count} records. Failed: {failed_count}.")

if __name__ == "__main__":
    main()
