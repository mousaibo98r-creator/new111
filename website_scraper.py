import re
import csv
import smtplib
import socket
import time
import requests
import pandas as pd

try:
    import dns.resolver
    HAS_DNS = True
except ImportError:
    HAS_DNS = False
    print("WARNING: 'dnspython' is not installed. MX checks will be skipped.")

# ---------------------------------------------------------
# 1. EMAIL VERIFICATION LOGIC (From previous script)
# ---------------------------------------------------------
def verify_email(email):
    """Verifies an email using DNS MX Record lookup and SMTP Ping"""
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return "Invalid Format"
    
    domain = email.split('@')[1]
    
    if HAS_DNS:
        try:
            records = dns.resolver.resolve(domain, 'MX')
            mxRecord = str(records[0].exchange)
        except Exception:
            return "Dead Domain (No MX)"
    else:
        mxRecord = domain

    try:
        server = smtplib.SMTP(timeout=3)
        server.set_debuglevel(0)
        server.connect(mxRecord)
        server.helo(socket.getfqdn())
        server.mail('hello@example.com')
        
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
        return "Unknown Error"


# ---------------------------------------------------------
# 2. WEBSITE SCRAPER LOGIC
# ---------------------------------------------------------
def scrape_emails_from_url(url):
    """Visits a website and uses Regex to find all email addresses on the homepage"""
    if not url.startswith('http'):
        url = 'http://' + url
        
    print(f"Scraping website: {url} ...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        # Regex to find emails in the HTML source code
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        raw_emails = set(re.findall(email_pattern, response.text))
        
        # Filter out false positives like images or css files that look like emails
        clean_emails = set()
        for e in raw_emails:
            e = e.lower()
            if not any(e.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css']):
                clean_emails.add(e)
                
        return list(clean_emails)
    except requests.exceptions.RequestException as e:
        print(f"  -> Failed to load website: {e}")
        return []


# ---------------------------------------------------------
# 3. MAIN SCRIPT
# ---------------------------------------------------------
def main():
    print("=======================================")
    print(" WEBSITE EMAIL SCRAPER & VERIFIER")
    print("=======================================")
    
    choice = input("Do you want to check a (1) Single Website or (2) Multiple Websites from a file? Enter 1 or 2: ")
    
    urls_to_check = []
    
    if choice == '1':
        single_url = input("Enter the website URL (e.g. example.com): ")
        urls_to_check.append(single_url)
    elif choice == '2':
        # Let's read from the combined_buyers.json we have
        import json
        print("Reading websites from combined_buyers.json (checking target countries)...")
        try:
            with open('combined_buyers.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            target_countries = [
                "romania", "hungary", "greece", "bulgaria", "serbia", "albania", 
                "bosnia", "kosovo", "macedonia", "montenegro", "moldova", "croatia", 
                "slovenia", "slovakia", "czech", "poland", "morocco", "libya", "georgia"
            ]
            
            for lead in data:
                c_eng = str(lead.get("country_english", "")).lower()
                c_dest = str(lead.get("destination_country", "")).lower()
                
                is_target = any(tc in c_eng or tc in c_dest for tc in target_countries)
                if is_target:
                    websites = lead.get("website", [])
                    if websites:
                        # Add the first website
                        urls_to_check.append(websites[0])
                        
            print(f"Found {len(urls_to_check)} websites from target countries!")
        except Exception as e:
            print(f"Error reading file: {e}")
            return
    else:
        print("Invalid choice.")
        return

    results = []
    
    # Process each website
    for url in set(urls_to_check):
        found_emails = scrape_emails_from_url(url)
        
        if not found_emails:
            print("  -> No emails found on this website.")
            continue
            
        print(f"  -> Found {len(found_emails)} emails! Verifying them now...")
        
        for email in found_emails:
            status = verify_email(email)
            print(f"     [ {email} ] -> {status}")
            
            results.append({
                "Website": url,
                "Email": email,
                "Status": status
            })
            time.sleep(0.1) # small pause to prevent ban
            
    # Save Results
    if results:
        print("\n------------------------------------------------")
        output_file = "scraped_and_verified_emails.xlsx"
        df = pd.DataFrame(results)
        df.to_excel(output_file, index=False)
        print(f"Saved {len(results)} scraped emails to {output_file}!")
    else:
        print("\nNo emails were successfully extracted and verified.")

if __name__ == "__main__":
    main()
