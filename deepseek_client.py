import os
import json
import asyncio
import re
import requests
from openai import AsyncOpenAI
from bs4 import BeautifulSoup

# Try Google Search first, fallback to DuckDuckGo
try:
    from googlesearch import search as google_search
    SEARCH_ENGINE = "google"
except ImportError:
    try:
        from ddgs import DDGS
        SEARCH_ENGINE = "ddgs"
    except ImportError:
        from duckduckgo_search import DDGS
        SEARCH_ENGINE = "ddgs"

class DeepSeekClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.client = AsyncOpenAI(
            api_key=self.api_key, 
            base_url="https://api.deepseek.com"
        )
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the internet for company contact details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (e.g. 'Chalishkan Company Iraq contact email')"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_page",
                    "description": "Fetch the content of a webpage to extract contact details like email, phone, address. Use this AFTER finding a website URL from search.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to fetch (e.g. 'https://company.com/contact')"
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]

    async def extract_company_data(self, system_prompt, buyer_name, country, model="deepseek-chat", callback=None):
        """
        Orchestrates the chat completion with MULTI-TURN tool calling.
        """
        user_content = f"Find contact info for Buyer: '{buyer_name}' located in '{country}'."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        if callback: callback(f"Initiating request with model: {model}...")

        max_turns = 15
        current_turn = 0

        while current_turn < max_turns:
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto"
                )
                
                message = response.choices[0].message
                
                # Check for Tool Calls
                if message.tool_calls:
                    messages.append(message) # Add assistant's tool-call message
                    
                    for tool_call in message.tool_calls:
                        args = json.loads(tool_call.function.arguments)
                        
                        if tool_call.function.name == "web_search":
                            query = args.get('query')
                            if callback: callback(f"Turn {current_turn+1}: Searching for '{query}'...")
                            result = self._perform_search(query)
                            
                        elif tool_call.function.name == "fetch_page":
                            url = args.get('url')
                            if callback: callback(f"Turn {current_turn+1}: Fetching page '{url}'...")
                            result = self._fetch_page(url)
                        else:
                            result = {"error": "Unknown tool"}
                        
                        # Add Tool Output
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                    
                    current_turn += 1
                    # Loop continues...
                else:
                    # No tool calls -> Final Answer
                    content = message.content
                    if not content: return None, current_turn
                    return self._clean_json(content), current_turn

            except Exception as e:
                if callback: callback(f"API Error: {str(e)}")
                return None, current_turn
        
        # If we exit loop without returning, force a FINAL answer without tools
        if callback: callback("Max turns reached. Forcing final JSON output...")
        
        # INJECT A STOP MESSAGE TO FORCE JSON
        messages.append({
            "role": "user",
            "content": "STOP SEARCHING. You have exceeded the search limit. Return the JSON object immediately with whatever data you found. If fields are missing, use null. Do NOT output any more thought or tool calls."
        })

        try:
             # Force a non-tool response by NOT sending tools
            final_response = await self.client.chat.completions.create(
                model=model,
                messages=messages
                # NO tools=self.tools here!
            )
            content = final_response.choices[0].message.content
            return self._clean_json(content), current_turn
        except:
             return None, current_turn

    def _perform_search(self, query):
        """Uses DuckDuckGo Search and extracts contact info from snippets and pages."""
        try:
            # Use DuckDuckGo
            from ddgs import DDGS
            ddgs = DDGS(timeout=30)
            results = list(ddgs.text(query, max_results=10))
            
            if not results:
                return [{"error": "No search results found."}]
            
            all_emails = []
            all_phones = []
            website = None
            output = []
            
            # First, extract data from search snippets (they often contain contact info!)
            # Skip directory/aggregator sites - we want actual company websites
            directory_domains = [
                'dnb.com', 'yellowpages', 'yelp.com', 'linkedin.com', 
                'facebook.com', 'bloomberg.com', 'zoominfo.com', 
                'crunchbase.com', 'glassdoor.com', 'indeed.com',
                'scribd.com', 'opencorporates.com', 'kompass.com',
                'b2bhint.com', 'volza.com', 'bizorg.su', 'panjiva.com',
                'importgenius.com', 'zauba.com', 'trademap.org',
                'europages.com', 'alibaba.com', 'made-in-china.com',
                'globalsources.com', 'thomasnet.com', 'manta.com',
                'hoovers.com', 'spoke.com', 'corporationwiki.com',
                'buzzfile.com', 'owler.com', 'datanyze.com', 'apollo.io'
            ]
            
            for r in results:
                snippet = r.get('body', '')
                title = r.get('title', '')
                url = r.get('href', '')
                
                # Get website from first NON-directory result
                if not website and url:
                    url_lower = url.lower()
                    is_directory = any(d in url_lower for d in directory_domains)
                    if not is_directory:
                        website = url
                
                # Extract emails from snippet
                emails_in_snippet = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet)
                all_emails.extend(emails_in_snippet)
                
                # Extract phone numbers from snippet (various formats)
                # Pattern for numbers like 9647514504009+ or +964 751 455 4426
                phones_in_snippet = re.findall(r'[\d]{10,15}\+?|\+[\d\s\-]{10,20}', snippet)
                for p in phones_in_snippet:
                    cleaned = re.sub(r'[^\d]', '', p)
                    if len(cleaned) >= 10:
                        all_phones.append(cleaned)
                
                output.append({
                    "title": title,
                    "snippet": snippet,
                    "url": url
                })
            
            # Fetch first result's page for more data
            page_text_preview = ""
            if results and (not all_emails or not all_phones):
                first_url = results[0].get('href', '')
                if first_url:
                    page_data = self._fetch_page(first_url)
                    if page_data.get('emails_found'):
                        all_emails.extend(page_data['emails_found'])
                    if page_data.get('phones_found'):
                        all_phones.extend(page_data['phones_found'])
                    if page_data.get('page_text_preview'):
                        page_text_preview = page_data['page_text_preview']
            
            # Deduplicate
            all_emails = list(set(all_emails))
            all_phones = list(set(all_phones))
            
            # Filter out invalid emails
            all_emails = [e for e in all_emails if not any(x in e.lower() for x in ['example', 'test', 'sample', 'wix', 'sentry'])]
            
            # Add summary at top with found data
            output.insert(0, {
                "CONTACT_INFO_FOUND": bool(all_emails or all_phones or page_text_preview),
                "website": website,
                "all_emails": all_emails[:10],
                "all_phones": all_phones[:10],
                "page_preview": page_text_preview[:2000],
                "instruction": "USE THESE VALUES IN YOUR JSON RESPONSE. Look for address in page_preview."
            })
            
            return output
            
        except Exception as e:
            return [{"error": f"Search failed: {str(e)}"}]

    def _fetch_page(self, url):
        """Fetches a webpage and extracts contact info using BeautifulSoup."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            html = response.text
            
            # Use BeautifulSoup for better parsing
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'noscript']):
                element.decompose()
            
            # Get clean text
            text = soup.get_text(separator=' ')
            text = re.sub(r'\s+', ' ', text)
            
            # Extract emails from raw HTML (more reliable than text)
            emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)))
            
            # Extract Cloudflare protected emails
            cf_emails = re.findall(r'data-cfemail="([^"]+)"', html)
            for cf in cf_emails:
                try:
                    r = int(cf[:2], 16)
                    decoded_email = ''.join([chr(int(cf[i:i+2], 16) ^ r) for i in range(2, len(cf), 2)])
                    if '@' in decoded_email:
                        emails.append(decoded_email)
                except:
                    pass
            
            # Filter out fake/generic emails
            emails = [e for e in emails if not any(x in e.lower() for x in ['example', 'test', 'sample', 'your', 'email', 'domain', 'wix', 'wordpress', 'sentry', 'schema'])]
            
            # Extract phone numbers with FIXED patterns
            phone_patterns = [
                r'\d{10,15}\+',  # 9647514504009+  (Iraqi format with + at end)
                r'\+\d{10,15}',  # +9647514554426  (+ at start)
                r'\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}',  # +964 751 455 4426
                r'(?:tel|phone|call)[:\s]+([+\d\s\-()]+)',  # tel: or phone: prefixed
                r'0\d{9,12}',  # 07514504009 (local format)
            ]
            
            phones = []
            for pattern in phone_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for m in matches:
                    if isinstance(m, str):
                        phones.append(m)
            
            # Flatten and clean phone numbers
            flat_phones = []
            for p in phones:
                if isinstance(p, list):
                    flat_phones.extend(p)
                else:
                    flat_phones.append(p)
            
            # Clean: remove non-digits except +
            cleaned_phones = []
            for p in flat_phones:
                cleaned = re.sub(r'[^\d+]', '', str(p))
                if len(cleaned) >= 10 and cleaned not in cleaned_phones:
                    cleaned_phones.append(cleaned)
            
            # Also look for href="tel:" links
            tel_links = soup.find_all('a', href=re.compile(r'^tel:'))
            for link in tel_links:
                tel = link.get('href', '').replace('tel:', '').strip()
                cleaned = re.sub(r'[^\d+]', '', tel)
                if len(cleaned) >= 10 and cleaned not in cleaned_phones:
                    cleaned_phones.append(cleaned)
            
            # Extract Address Candidates
            address_candidates = []
            # Look for common address markers
            address_markers = ['address', 'location', 'hq', 'office', 'box ', 'street', 'road', 'avenue', 'suite', 'floor']
            text_lower = text.lower()
            
            for marker in address_markers:
                idx = text_lower.find(marker)
                if idx != -1:
                    # Capture context around marker
                    start = max(0, idx - 50)
                    end = min(len(text), idx + 150)
                    candidate = text[start:end].strip()
                    if len(candidate) > 10:
                        address_candidates.append(candidate)
                        
            # Add footer text as it often contains address
            footer = soup.find('footer')
            if footer:
                footer_text = footer.get_text(separator=' ').strip()
                footer_text = re.sub(r'\s+', ' ', footer_text)
                if len(footer_text) < 500:
                    address_candidates.append(f"Footer: {footer_text}")
            
            # Join candidates for preview
            address_text = " | ".join(address_candidates[:3])
            
            final_text = text[:2500] 
            if address_text:
                final_text += f"\n\nPossible Address Info: {address_text}"

            return {
                "url": url,
                "emails_found": emails[:10],
                "phones_found": cleaned_phones[:10],
                "page_text_preview": final_text
            }
        except Exception as e:
            return {"error": f"Failed to fetch page: {str(e)}"}

    def _clean_json(self, text):
        """Extracts JSON from markdown code blocks if necessary."""
        if not text: return None
        text = text.strip()
        # Sometimes models output text before json
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.rfind("```")
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.rfind("```")
            text = text[start:end].strip()
        return text
