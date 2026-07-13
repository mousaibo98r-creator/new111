import json
import smtplib
import socket
import re
import time
import csv

try:
    import dns.resolver
    HAS_DNS = True
except ImportError:
    HAS_DNS = False
    print("WARNING: 'dnspython' is not installed. MX checks will be skipped.")
    print("Please run: pip install dnspython")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("WARNING: 'pandas' or 'openpyxl' is not installed. Will output to CSV instead.")
    print("Please run: pip install pandas openpyxl to get Excel output.")

# The requested target countries (English names or partial matches)
TARGET_COUNTRIES = [
    "romania", "hungary", "greece", "bulgaria", "serbia", "albania", 
    "bosnia", "kosovo", "macedonia", "montenegro", "moldova", "croatia", 
    "slovenia", "slovakia", "czech", "poland", "morocco", "libya", "georgia"
]

def is_target_country(country_name):
    if not country_name:
        return False
    c = str(country_name).lower()
    for tc in TARGET_COUNTRIES:
        if tc in c:
            return True
    return False

def verify_email(email):
    """
    Verifies an email using:
    1. Regex format check
    2. DNS MX Record lookup
    3. SMTP Handshake (Ping)
    """
    # 1. Format check
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return "Invalid Format"
    
    domain = email.split('@')[1]
    
    # 2. DNS MX Check
    if HAS_DNS:
        try:
            records = dns.resolver.resolve(domain, 'MX')
            mxRecord = str(records[0].exchange)
        except Exception:
            return "Dead Domain (No MX)"
    else:
        # Fallback if dnspython is missing
        mxRecord = domain

    # 3. SMTP Ping
    try:
        # Connect to the mail server
        server = smtplib.SMTP(timeout=3)
        server.set_debuglevel(0)
        server.connect(mxRecord)
        server.helo(socket.getfqdn())
        server.mail('hello@example.com')
        
        # Ping the exact email address
        code, message = server.rcpt(str(email))
        server.quit()
        
        if code == 250:
            return "Valid (SMTP 250)"
        elif code >= 500:
            return f"Invalid (SMTP {code})"
        else:
            return f"Catch-All/Unknown ({code})"
            
    except smtplib.SMTPServerDisconnected:
        return "Server Blocked Ping"
    except socket.timeout:
        return "Timeout"
    except Exception as e:
        return f"Unknown Error"

def main():
    input_file = 'combined_buyers.json'
    output_file = 'verified_target_leads.csv'
    
    print(f"Loading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"Found {len(data)} total leads. Filtering by target countries...")
    
    target_leads = []
    for lead in data:
        # Check both english and original destination country fields
        c_eng = lead.get("country_english", "")
        c_dest = lead.get("destination_country", "")
        
        if is_target_country(c_eng) or is_target_country(c_dest):
            # Only add leads that actually have emails
            emails = lead.get("email", [])
            if emails:
                target_leads.append(lead)
                
    print(f"Extracted {len(target_leads)} leads with emails from target countries.")
    # Gather rows instantly
    rows = []
    
    for lead in target_leads:
        company = lead.get("company_name_english") or lead.get("buyer_name")
        country = lead.get("country_english") or lead.get("destination_country")
        total_usd = lead.get("total_usd", 0)
        
        # Only get the first email to keep the list clean, or join them
        emails = ", ".join([e.strip() for e in lead.get("email", [])])
        
        rows.append({
            "Company Name": company,
            "Country": country,
            "Emails": emails,
            "Total USD": total_usd
        })

    print("-" * 50)
    
    if HAS_PANDAS:
        output_file = 'target_countries_only.xlsx'
        df = pd.DataFrame(rows)
        df.to_excel(output_file, index=False)
    else:
        output_file = 'target_countries_only.csv'
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["Company Name", "Country", "Emails", "Total USD"])
            writer.writeheader()
            writer.writerows(rows)
            
    print(f"Done! Saved to {output_file}.")
    print(f"Instantly extracted {len(rows)} companies from your target countries!")

if __name__ == "__main__":
    main()
