import pandas as pd
import re
import json
import sys
import requests

def extract_list(val):
    if pd.isna(val) or val == 'None' or val == '[]' or val == '':
        return set()
    s = str(val).strip()
    if '[' in s and ']' in s:
        try:
            s_json = s.replace("'", '"')
            lst = json.loads(s_json)
            return set([str(x).strip().lower() for x in lst if str(x).strip()])
        except:
            pass
    
    items = re.split(r'[,;]+', s)
    return set([re.sub(r'["\[\]]', '', x).strip().lower() for x in items if x.strip()])

def to_comma_separated(val_set):
    return ', '.join(sorted(list(val_set)))

try:
    # 1. Parse secrets
    url, key = None, None
    with open(r'.streamlit\secrets.toml', 'r', encoding='utf-8') as f:
        content = f.read()
        url_m = re.search(r'SUPABASE_URL\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        key_m = re.search(r'SUPABASE_ANON_KEY\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        if url_m and key_m:
            url = url_m.group(1)
            key = key_m.group(1)
            
    if not url or not key:
        print("Could not find Supabase credentials")
        sys.exit(1)
        
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    # 2. Load all data from Supabase via REST
    print('Loading Supabase database...')
    all_rows = []
    offset = 0
    limit = 1000

    while True:
        resp = requests.get(f"{url}/rest/v1/mousa?select=*&limit={limit}&offset={offset}", headers=headers)
        if resp.status_code != 200:
            print("Error fetching data:", resp.text)
            break
        data = resp.json()
        if not data:
            break
        all_rows.extend(data)
        if len(data) < limit:
            break
        offset += limit
        
    df_db = pd.DataFrame(all_rows)
    df_db['buyer_name_lower'] = df_db['buyer_name'].astype(str).str.lower().str.strip()
    
    db_dict = {}
    for idx, row in df_db.iterrows():
        b_name = row['buyer_name_lower']
        if b_name not in db_dict:
            db_dict[b_name] = []
        db_dict[b_name].append(row)
    
    # 3. Load the NEW CSV
    print('Loading CSV...')
    new_file = r'2026-07-20T18-39_export.csv'
    df_new = pd.read_csv(new_file)
    df_new['buyer_name_lower'] = df_new['Buyer'].astype(str).str.lower().str.strip()
    df_new_unique = df_new.drop_duplicates(subset=['buyer_name_lower'])
    
    # 4. Update Database
    updates_made = 0
    
    for _, row in df_new_unique.iterrows():
        b_name = row['buyer_name_lower']
        if b_name in db_dict:
            # Update based on buyer_name since id might not exist
            db_row = db_dict[b_name][0]
            original_buyer_name = db_row['buyer_name']
            
            update_payload = {}
            
            for csv_col, db_col in [('Email', 'email'), ('Phone', 'phone'), ('Website', 'website')]:
                new_val = str(row.get(csv_col, ''))
                db_val = str(db_row.get(db_col, ''))
                
                new_set = extract_list(new_val)
                db_set = extract_list(db_val)
                
                new_items = new_set - db_set
                
                if new_items:
                    combined_set = db_set.union(new_set)
                    update_payload[db_col] = to_comma_separated(combined_set)
            
            if update_payload:
                try:
                    import urllib.parse
                    encoded_name = urllib.parse.quote(original_buyer_name)
                    patch_resp = requests.patch(f"{url}/rest/v1/mousa?buyer_name=eq.{encoded_name}", headers=headers, json=update_payload)
                    if patch_resp.status_code in [200, 204]:
                        updates_made += 1
                        if updates_made % 100 == 0:
                            print(f'Updated {updates_made} companies by COMBINING old and new data together...')
                    else:
                        print(f"Error updating {original_buyer_name}: {patch_resp.text}")
                except Exception as e:
                    print(f"Error updating {original_buyer_name}: {e}")
                    
    print(f'Successfully updated {updates_made} companies in Supabase with extra contacts without deleting past data!')

except Exception as e:
    import traceback
    traceback.print_exc()
