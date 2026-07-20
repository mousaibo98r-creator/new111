import pandas as pd
import re
import json
import sys
import requests
import urllib.parse

def extract_list(val):
    if pd.isna(val) or val == 'None' or val == '[]' or val == '':
        return set()
    s = str(val).strip()
    if '[' in s and ']' in s:
        try:
            s_json = s.replace("'", '"')
            lst = json.loads(s_json)
            return set([str(x).strip() for x in lst if str(x).strip()])
        except:
            pass
    
    items = re.split(r'[,;]+', s)
    return set([re.sub(r'["\[\]]', '', x).strip() for x in items if x.strip()])

def to_comma_separated(val_set):
    return ', '.join(sorted(list(val_set)))

try:
    print("1. Updating local CSV database...")
    db_file = r'c:\Users\ASUS\Downloads\website 4th time\2026-07-04T12-16_export.csv'
    new_file = r'c:\Users\ASUS\Downloads\website 4th time\2026-07-20T18-39_export.csv'
    
    df_db = pd.read_csv(db_file)
    df_new = pd.read_csv(new_file)
    
    df_db['buyer_name_lower'] = df_db['Buyer'].astype(str).str.lower().str.strip()
    df_new['buyer_name_lower'] = df_new['Buyer'].astype(str).str.lower().str.strip()
    
    df_new_unique = df_new.drop_duplicates(subset=['buyer_name_lower'])
    db_idx_map = df_db.drop_duplicates(subset=['buyer_name_lower']).reset_index().set_index('buyer_name_lower')['index'].to_dict()
    
    cols_to_update = ['Country', 'Email', 'Phone', 'Website', 'Address']
    
    csv_updates_made = 0
    updated_records = {} # store what we updated to push to supabase
    
    for _, row in df_new_unique.iterrows():
        b_name = row['buyer_name_lower']
        if b_name in db_idx_map:
            idx = db_idx_map[b_name]
            updated = False
            
            supabase_payload = {}
            for col in cols_to_update:
                if col in row and col in df_db.columns:
                    new_val = str(row.get(col, ''))
                    db_val = str(df_db.at[idx, col])
                    
                    new_set = extract_list(new_val)
                    db_set = extract_list(db_val)
                    
                    # Add new to old
                    combined_set = db_set.union(new_set)
                    new_combined_val = to_comma_separated(combined_set)
                    
                    if new_combined_val != to_comma_separated(db_set) and new_combined_val:
                        df_db.at[idx, col] = new_combined_val
                        updated = True
                        
                        # map local CSV col to supabase col
                        if col == 'Country': supabase_payload['destination_country'] = new_combined_val
                        elif col == 'Email': supabase_payload['email'] = new_combined_val
                        elif col == 'Phone': supabase_payload['phone'] = new_combined_val
                        elif col == 'Website': supabase_payload['website'] = new_combined_val
                        elif col == 'Address': supabase_payload['address'] = new_combined_val
            
            if updated:
                csv_updates_made += 1
                updated_records[df_db.at[idx, 'Buyer']] = supabase_payload
                
    # Save local CSV
    df_db = df_db.drop(columns=['buyer_name_lower'])
    df_db.to_csv(db_file, index=False)
    print(f"Updated {csv_updates_made} rows in local CSV database.")
    
    print("2. Pushing these exact updates to Supabase...")
    
    # Parse secrets
    url, key = None, None
    with open(r'.streamlit\secrets.toml', 'r', encoding='utf-8') as f:
        content = f.read()
        url_m = re.search(r'SUPABASE_URL\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        key_m = re.search(r'SUPABASE_ANON_KEY\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        if url_m and key_m:
            url = url_m.group(1)
            key = key_m.group(1)
            
    if not url or not key:
        print("Could not find Supabase credentials, skipping Supabase sync.")
    else:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        supabase_updates = 0
        for original_buyer_name, payload in updated_records.items():
            encoded_name = urllib.parse.quote(original_buyer_name)
            try:
                patch_resp = requests.patch(f"{url}/rest/v1/mousa?buyer_name=eq.{encoded_name}", headers=headers, json=payload)
                if patch_resp.status_code in [200, 204]:
                    supabase_updates += 1
            except Exception as e:
                pass
                
        print(f"Updated {supabase_updates} rows in Supabase.")
    print("Done!")
    
except Exception as e:
    import traceback
    traceback.print_exc()
