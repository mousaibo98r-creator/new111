"""
DeepSeek Smart Contact Finder — Upgraded
Combines multi-turn AI tool-calling with intelligent search:
  • AI name correction & language detection
  • Async DuckDuckGo search with contact-page detection
  • Intelligent contact-page navigation (İletişim, Contact, Kontakt…)
  • Cloudflare email decoding
  • httpx async HTTP with rotating User-Agent
"""

import os
import json
import re
import asyncio
import httpx
from openai import AsyncOpenAI
from bs4 import BeautifulSoup

# Search engine imports
try:
    from duckduckgo_search import AsyncDDGS
    ASYNC_SEARCH = True
except ImportError:
    ASYNC_SEARCH = False
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

# Optional: rotating user agent
try:
    from fake_useragent import UserAgent
    _UA = UserAgent()
    def _random_ua():
        return _UA.random
except ImportError:
    def _random_ua():
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# Sites to skip — directories, aggregators, social media
DIRECTORY_DOMAINS = frozenset([
    'dnb.com', 'yellowpages', 'yelp.com', 'linkedin.com',
    'facebook.com', 'bloomberg.com', 'zoominfo.com',
    'crunchbase.com', 'glassdoor.com', 'indeed.com',
    'scribd.com', 'opencorporates.com', 'kompass.com',
    'b2bhint.com', 'volza.com', 'bizorg.su', 'panjiva.com',
    'importgenius.com', 'zauba.com', 'trademap.org',
    'europages.com', 'alibaba.com', 'made-in-china.com',
    'globalsources.com', 'thomasnet.com', 'manta.com',
    'hoovers.com', 'spoke.com', 'corporationwiki.com',
    'buzzfile.com', 'owler.com', 'datanyze.com', 'apollo.io',
    'instagram.com', 'twitter.com', 'x.com', 'youtube.com',
    'tiktok.com', 'pinterest.com',
])


class DeepSeekClient:
    """
    Smart AI-powered company contact finder.
    Uses DeepSeek (or any OpenAI-compatible API) with real web search + scraping.
    """

    def __init__(self, api_key=None, base_url="https://api.deepseek.com"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=base_url)
        self._http = None  # lazy init

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the internet for company contact details, websites, emails, phones.",
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
                    "description": (
                        "Fetch a webpage and extract contact info (email, phone, address). "
                        "Automatically follows Contact/İletişim/Kontakt links if on homepage."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to fetch (e.g. 'https://company.com/contact')"
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]

    async def _get_http(self):
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": _random_ua()},
            )
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── Phase 0: AI Name Correction ──────────────────────────────────────────
    async def _fix_name_with_ai(self, raw_name, country_hint, callback=None):
        """Use AI to correct company name and get localized search keywords."""
        if callback:
            callback(f"🤖 AI analyzing company name: '{raw_name}'...")

        system = (
            "You are a data expert. Given a company name (possibly misspelled) and country hint:\n"
            "1. Correct the company name (fix spelling, missing letters, transliteration issues).\n"
            "2. Identify the country and primary language.\n"
            "3. Provide the translation for 'Contact' and 'Address' in that language.\n\n"
            "Output JSON ONLY:\n"
            '{"corrected_name":"...","country":"...","language_code":"en",'
            '"keywords":{"contact_page":["Contact","İletişim"],"address":["Address","Adres"]}}'
        )
        user_msg = f"Company: '{raw_name}'. Country hint: {country_hint or 'Unknown'}"

        try:
            resp = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            corrected = data.get("corrected_name", raw_name)
            if callback:
                callback(f"✅ Corrected name: '{corrected}'")
            return data
        except Exception:
            return {
                "corrected_name": raw_name,
                "country": country_hint or "",
                "keywords": {
                    "contact_page": ["Contact", "İletişim", "Kontakt", "Contacto"],
                    "address": ["Address", "Adres", "Adresse"],
                },
            }

    # ── Main Entry Point ─────────────────────────────────────────────────────
    async def extract_company_data(
        self, system_prompt, buyer_name, country,
        model="deepseek-chat", callback=None
    ):
        """
        Full pipeline:
        1. AI name correction → get corrected name + localized keywords
        2. Multi-turn AI tool-calling loop (search + scrape)
        3. Return extracted JSON
        """
        # Phase 0 — fix name
        ai_meta = await self._fix_name_with_ai(buyer_name, country, callback)
        corrected_name = ai_meta.get("corrected_name", buyer_name)
        self._contact_keywords = ai_meta.get("keywords", {}).get(
            "contact_page", ["Contact", "İletişim"]
        )
        self._address_keywords = ai_meta.get("keywords", {}).get(
            "address", ["Address", "Adres"]
        )

        # Use corrected name in the user prompt
        user_content = (
            f"Find contact info for Buyer: '{corrected_name}' "
            f"(original name: '{buyer_name}') located in '{country}'."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        if callback:
            callback(f"🚀 Starting search for: {corrected_name}")

        max_turns = 12
        current_turn = 0

        while current_turn < max_turns:
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                )
                message = response.choices[0].message

                if message.tool_calls:
                    messages.append(message)

                    for tool_call in message.tool_calls:
                        args = json.loads(tool_call.function.arguments)

                        if tool_call.function.name == "web_search":
                            query = args.get("query", "")
                            if callback:
                                callback(f"🔎 Turn {current_turn+1}: Searching '{query}'...")
                            result = await self._perform_search(query)

                        elif tool_call.function.name == "fetch_page":
                            url = args.get("url", "")
                            if callback:
                                callback(f"🌐 Turn {current_turn+1}: Scraping '{url}'...")
                            result = await self._fetch_page(url)
                        else:
                            result = {"error": "Unknown tool"}

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })

                    current_turn += 1
                else:
                    content = message.content
                    if not content:
                        return None, current_turn
                    return self._clean_json(content), current_turn

            except Exception as e:
                if callback:
                    callback(f"⚠️ API Error: {e}")
                return None, current_turn

        # Max turns — force final answer
        if callback:
            callback("⏱️ Max turns reached. Forcing final answer...")

        messages.append({
            "role": "user",
            "content": (
                "STOP SEARCHING. Return the JSON object immediately with whatever "
                "data you found. If fields are missing, use null or empty arrays."
            ),
        })

        try:
            final = await self.client.chat.completions.create(
                model=model, messages=messages  # NO tools
            )
            content = final.choices[0].message.content
            return self._clean_json(content), current_turn
        except Exception:
            return None, current_turn

    # ── Web Search (async) ───────────────────────────────────────────────────
    async def _perform_search(self, query):
        """Async DuckDuckGo search with smart contact-page detection."""
        try:
            results = []
            if ASYNC_SEARCH:
                async with AsyncDDGS() as ddgs:
                    async for r in ddgs.text(query, max_results=8):
                        results.append(r)
            else:
                ddgs = DDGS(timeout=30)
                results = list(ddgs.text(query, max_results=8))

            if not results:
                return [{"error": "No search results found."}]

            all_emails = []
            all_phones = []
            website = None
            contact_page = None
            output = []

            for r in results:
                snippet = r.get("body", r.get("snippet", ""))
                title = r.get("title", "")
                url = r.get("href", r.get("link", ""))
                url_lower = url.lower()

                is_directory = any(d in url_lower for d in DIRECTORY_DOMAINS)

                # Detect contact page URLs
                if not is_directory and not contact_page:
                    if any(kw.lower() in url_lower for kw in self._contact_keywords) or "contact" in url_lower:
                        contact_page = url

                # First non-directory = website
                if not website and url and not is_directory:
                    website = url

                # Extract emails from snippet
                emails_found = re.findall(
                    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet
                )
                all_emails.extend(emails_found)

                # Extract phone numbers from snippet
                phones_found = re.findall(r'[\d]{10,15}\+?|\+[\d\s\-]{10,20}', snippet)
                for p in phones_found:
                    cleaned = re.sub(r'[^\d]', '', p)
                    if len(cleaned) >= 10:
                        all_phones.append(cleaned)

                output.append({"title": title, "snippet": snippet, "url": url})

            # Auto-fetch the contact page or first result
            target_url = contact_page or website
            page_text_preview = ""

            if target_url and (not all_emails or not all_phones):
                page_data = await self._fetch_page(target_url)
                if page_data.get("emails_found"):
                    all_emails.extend(page_data["emails_found"])
                if page_data.get("phones_found"):
                    all_phones.extend(page_data["phones_found"])
                if page_data.get("page_text_preview"):
                    page_text_preview = page_data["page_text_preview"]

            # Deduplicate & filter
            all_emails = list(set(all_emails))
            all_emails = [
                e for e in all_emails
                if not any(x in e.lower() for x in [
                    'example', 'test', 'sample', 'wix', 'sentry',
                    'wordpress', 'schema', 'domain'
                ])
            ]
            all_phones = list(set(all_phones))

            output.insert(0, {
                "CONTACT_INFO_FOUND": bool(all_emails or all_phones or page_text_preview),
                "website": website,
                "contact_page": contact_page,
                "all_emails": all_emails[:10],
                "all_phones": all_phones[:10],
                "page_preview": page_text_preview[:2000],
                "instruction": "USE THESE VALUES IN YOUR JSON RESPONSE. Look for address in page_preview.",
            })

            return output

        except Exception as e:
            return [{"error": f"Search failed: {e}"}]

    # ── Fetch Page (async + smart navigation) ────────────────────────────────
    async def _fetch_page(self, url):
        """Fetch a webpage, auto-follow contact links, extract all contact info."""
        try:
            http = await self._get_http()
            resp = await http.get(url)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # ── Smart navigation: if on homepage, find Contact link ──────────
            is_contact_page = any(
                x in url.lower() for x in ["contact", "iletisim", "kontakt", "contacto"]
            )

            if not is_contact_page:
                for a_tag in soup.find_all("a", href=True):
                    link_text = a_tag.get_text().strip().lower()
                    href_val = a_tag["href"].lower()

                    contact_kws = getattr(self, "_contact_keywords", ["Contact", "İletişim"])
                    if any(k.lower() in link_text for k in contact_kws) or \
                       any(k.lower() in href_val for k in contact_kws):

                        raw_href = a_tag["href"]
                        if raw_href.startswith("/"):
                            base = "/".join(url.split("/")[:3])
                            follow_url = base + raw_href
                        elif raw_href.startswith("http"):
                            follow_url = raw_href
                        else:
                            continue

                        try:
                            resp2 = await http.get(follow_url)
                            if resp2.status_code == 200:
                                html = resp2.text
                                soup = BeautifulSoup(html, "html.parser")
                                url = follow_url
                        except Exception:
                            pass
                        break

            # ── Clean HTML ───────────────────────────────────────────────────
            for el in soup(["script", "style", "noscript"]):
                el.decompose()

            text = soup.get_text(separator=" ")
            text = re.sub(r"\s+", " ", text)

            # ── Extract Emails ───────────────────────────────────────────────
            emails = list(set(re.findall(
                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html
            )))

            # Cloudflare protected emails
            cf_emails = re.findall(r'data-cfemail="([^"]+)"', html)
            for cf in cf_emails:
                try:
                    r = int(cf[:2], 16)
                    decoded = "".join(
                        chr(int(cf[i:i+2], 16) ^ r) for i in range(2, len(cf), 2)
                    )
                    if "@" in decoded:
                        emails.append(decoded)
                except Exception:
                    pass

            # Filter junk emails
            emails = [
                e for e in emails
                if not any(x in e.lower() for x in [
                    'example', 'test', 'sample', 'your', 'email',
                    'domain', 'wix', 'wordpress', 'sentry', 'schema'
                ])
            ]

            # ── Extract Phones ───────────────────────────────────────────────
            phone_patterns = [
                r'\d{10,15}\+',
                r'\+\d{10,15}',
                r'\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
                r'(?:tel|phone|call)[:\s]+([\+\d\s\-()]+)',
                r'0\d{9,12}',
                r'(?:\+90|0)?\s?[2-5]\d{2}\s?\d{3}\s?\d{2}\s?\d{2}',
            ]

            phones_raw = []
            for pat in phone_patterns:
                matches = re.findall(pat, html, re.IGNORECASE)
                for m in matches:
                    if isinstance(m, str):
                        phones_raw.append(m)

            # tel: links
            for link in soup.find_all("a", href=re.compile(r"^tel:")):
                tel = link.get("href", "").replace("tel:", "").strip()
                phones_raw.append(tel)

            # Clean phones
            cleaned_phones = []
            for p in phones_raw:
                cleaned = re.sub(r'[^\d+]', '', str(p))
                if len(cleaned) >= 10 and cleaned not in cleaned_phones:
                    cleaned_phones.append(cleaned)

            # ── Extract Address ──────────────────────────────────────────────
            address_candidates = []
            all_markers = ["address", "location", "hq", "office", "box ",
                           "street", "road", "avenue", "suite", "floor"]
            # Add localized markers
            addr_kws = getattr(self, "_address_keywords", ["Address", "Adres"])
            all_markers.extend(k.lower() for k in addr_kws)

            text_lower = text.lower()
            for marker in all_markers:
                idx = text_lower.find(marker)
                if idx != -1:
                    start = max(0, idx - 50)
                    end = min(len(text), idx + 150)
                    candidate = text[start:end].strip()
                    if len(candidate) > 10:
                        address_candidates.append(candidate)

            # Footer often has address
            footer = soup.find("footer")
            if footer:
                ft = re.sub(r"\s+", " ", footer.get_text(separator=" ").strip())
                if len(ft) < 500:
                    address_candidates.append(f"Footer: {ft}")

            address_text = " | ".join(address_candidates[:3])

            final_text = text[:2500]
            if address_text:
                final_text += f"\n\nPossible Address Info: {address_text}"

            return {
                "url": url,
                "emails_found": emails[:10],
                "phones_found": cleaned_phones[:10],
                "page_text_preview": final_text,
            }

        except Exception as e:
            return {"error": f"Failed to fetch page: {e}"}

    # ── JSON cleanup ─────────────────────────────────────────────────────────
    def _clean_json(self, text):
        if not text:
            return None
        text = text.strip()
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.rfind("```")
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.rfind("```")
            text = text[start:end].strip()
        return text
