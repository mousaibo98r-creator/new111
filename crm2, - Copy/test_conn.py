import db
try:
    leads = db.get_all_leads()
    print(f"Success! Found {len(leads)} leads.")
except Exception as e:
    print(f"Error: {e}")
