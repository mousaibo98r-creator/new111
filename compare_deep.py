import pandas as pd
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

def extract_list(val):
    if pd.isna(val) or val == 'None' or val == '[]' or val == '':
        return set()
    s = str(val).strip()
    if '[' in s and ']' in s:
        import json
        try:
            s_json = s.replace("'", '"')
            lst = json.loads(s_json)
            return set([str(x).strip().lower() for x in lst if str(x).strip()])
        except:
            pass
    
    items = re.split(r'[,;]+', s)
    return set([re.sub(r'["\[\]]', '', x).strip().lower() for x in items if x.strip()])

try:
    db_file = r'c:\Users\ASUS\Downloads\website 4th time\2026-07-04T12-16_export.csv'
    new_file = r'c:\Users\ASUS\Downloads\website 4th time\2026-07-20T18-39_export.csv'
    
    df_db = pd.read_csv(db_file)
    df_new = pd.read_csv(new_file)
    
    df_db['buyer_name_lower'] = df_db['Buyer'].astype(str).str.lower().str.strip()
    df_new['buyer_name_lower'] = df_new['Buyer'].astype(str).str.lower().str.strip()
    
    df_new_unique = df_new.drop_duplicates(subset=['buyer_name_lower'])
    db_dict = df_db.drop_duplicates(subset=['buyer_name_lower']).set_index('buyer_name_lower').to_dict('index')
    
    companies_with_new_items = 0
    updates_breakdown = {'Email': 0, 'Phone': 0, 'Website': 0}
    
    for _, row in df_new_unique.iterrows():
        b_name = row['buyer_name_lower']
        if b_name in db_dict:
            db_row = db_dict[b_name]
            has_update = False
            
            for col in ['Email', 'Phone', 'Website']:
                new_val = str(row.get(col, ''))
                db_val = str(db_row.get(col, ''))
                
                new_set = extract_list(new_val)
                db_set = extract_list(db_val)
                
                new_items = new_set - db_set
                
                if new_items:
                    has_update = True
                    updates_breakdown[col] += len(new_items)
                    
            if has_update:
                companies_with_new_items += 1
                
    print(f'=== DEEP COMPARISON RESULTS ===')
    print(f'Companies in BOTH that have ADDITIONAL Emails/Phones/Websites in the New File: {companies_with_new_items}')
    print(f'Breakdown of brand new individual items we can add:')
    for k, v in updates_breakdown.items():
        print(f'   - {k}: {v} new {k}s found across existing companies')

except Exception as e:
    import traceback
    traceback.print_exc()
