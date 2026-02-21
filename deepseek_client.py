"""
DeepSeek Smart Contact Finder
AI-powered company contact search with web scraping & tool-calling.
"""

import os, json, re, asyncio, httpx
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

# Optional rotating user agent
try:
    from fake_useragent import UserAgent
    _UA = UserAgent()
    _random_ua = lambda: _UA.random
except ImportError:
    _random_ua = lambda: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# Domains to skip
SKIP_DOMAINS = frozenset([
    'dnb.com', 'yellowpages', 'yelp.com', 'linkedin.com', 'facebook.com',
    'bloomberg.com', 'zoominfo.com', 'crunchbase.com', 'glassdoor.com',
    'indeed.com', 'scribd.com', 'opencorporates.com', 'kompass.com',
    'b2bhint.com', 'volza.com', 'bizorg.su', 'panjiva.com',
    'importgenius.com', 'zauba.com', 'trademap.org', 'europages.com',
    'alibaba.com', 'made-in-china.com', 'globalsources.com', 'thomasnet.com',
    'manta.com', 'hoovers.com', 'spoke.com', 'corporationwiki.com',
    'buzzfile.com', 'owler.com', 'datanyze.com', 'apollo.io',
    'instagram.com', 'twitter.com', 'x.com', 'youtube.com',
    'tiktok.com', 'pinterest.com',
])

JUNK_EMAIL_WORDS = ['example', 'test', 'sample', 'your@', 'domain', 'wix',
                    'wordpress', 'sentry', 'schema', 'noreply', 'no-reply',
                    '.png', '.jpg', '.gif']

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

CONTACT_PATHS = [
    "/contact", "/contact-us", "/contacts", "/en/contact", "/en/contact-us",
    "/iletisim", "/tr/iletisim", "/kontakt", "/de/kontakt",
    "/contacto", "/es/contacto", "/about/contact", "/about-us/contact",
]

PHONE_PATTERNS = [
    r'\d{10,15}\+', r'\+\d{10,15}',
    r'\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
    r'\+\d{1,3}[\s\-]?\(\d+\)[\s\-]?[\d\s\.\-]+',
    r'(?:tel|phone|fax|call|mobile)[:\s]+([\+\d\s\-()./]+)',
    r'0\d{9,12}',
    r'(?:\+90|0)?\s?[2-5]\d{2}\s?\d{3}\s?\d{2}\s?\d{2}',
    r'(?:\+\d{1,3})?\s?\(0?\d{2,4}\)\s?[\d\s\.\-]{6,}',
]

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the internet for company contact details, websites, emails, phones.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "fetch_page",
        "description": "Fetch a webpage and extract contact info. Auto-follows contact page links.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL to fetch"}
        }, "required": ["url"]}
    }},
]


def _filter_emails(emails):
    """Deduplicate and remove junk emails."""
    return list({e for e in emails if not any(w in e.lower() for w in JUNK_EMAIL_WORDS)})


def _clean_phones(raw_phones):
    """Deduplicate and normalize phone numbers."""
    seen, out = set(), []
    for p in raw_phones:
        cleaned = re.sub(r'[^\d+]', '', str(p))
        if len(cleaned) >= 10 and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


class DeepSeekClient:
    """AI-powered company contact finder using DeepSeek + web search/scraping."""

    def __init__(self, api_key=None, base_url="https://api.deepseek.com"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=base_url)
        self._http = None
        self._contact_kw = ["Contact", "İletişim", "Kontakt", "Contacto"]
        self._address_kw = ["Address", "Adres", "Adresse"]

    async def _get_http(self):
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=20.0, follow_redirects=True,
                headers={"User-Agent": _random_ua()},
            )
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── Phase 0: AI Name Correction ──────────────────────────────────────
    async def _fix_name_with_ai(self, raw_name, country_hint, callback=None):
        if callback:
            callback(f"🤖 AI analyzing company name: '{raw_name}'...")

        system = (
            "You are a data expert. Given a company name (possibly misspelled) and country hint:\n"
            "1. Correct the company name.\n"
            "2. Identify the country and primary language.\n"
            "3. Provide translations for 'Contact' and 'Address' in that language.\n\n"
            "Output JSON ONLY:\n"
            '{"corrected_name":"...","country":"...","language_code":"en",'
            '"keywords":{"contact_page":["Contact","İletişim"],"address":["Address","Adres"]}}'
        )
        try:
            resp = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Company: '{raw_name}'. Country hint: {country_hint or 'Unknown'}"},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            if callback:
                callback(f"✅ Corrected name: '{data.get('corrected_name', raw_name)}'")
            return data
        except Exception:
            return {"corrected_name": raw_name, "country": country_hint or "",
                    "keywords": {"contact_page": self._contact_kw, "address": self._address_kw}}

    # ── Main Pipeline ────────────────────────────────────────────────────
    async def extract_company_data(self, system_prompt, buyer_name, country,
                                   model="deepseek-chat", callback=None):
        # Phase 0 — fix name
        ai_meta = await self._fix_name_with_ai(buyer_name, country, callback)
        corrected = ai_meta.get("corrected_name", buyer_name)
        self._contact_kw = ai_meta.get("keywords", {}).get("contact_page", self._contact_kw)
        self._address_kw = ai_meta.get("keywords", {}).get("address", self._address_kw)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Find contact info for Buyer: '{corrected}' "
                f"(original name: '{buyer_name}') located in '{country}'."
            )},
        ]
        if callback:
            callback(f"🚀 Starting search for: {corrected}")

        for turn in range(12):
            try:
                response = await self.client.chat.completions.create(
                    model=model, messages=messages, tools=TOOLS, tool_choice="auto",
                )
                msg = response.choices[0].message

                if not msg.tool_calls:
                    return (self._clean_json(msg.content), turn) if msg.content else (None, turn)

                messages.append(msg)
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    if tc.function.name == "web_search":
                        q = args.get("query", "")
                        if callback: callback(f"🔎 Turn {turn+1}: Searching '{q}'...")
                        result = await self._perform_search(q)
                    elif tc.function.name == "fetch_page":
                        u = args.get("url", "")
                        if callback: callback(f"🌐 Turn {turn+1}: Scraping '{u}'...")
                        result = await self._fetch_page(u)
                    else:
                        result = {"error": "Unknown tool"}

                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": json.dumps(result, ensure_ascii=False)})
            except Exception as e:
                if callback: callback(f"⚠️ API Error: {e}")
                return None, turn

        # Max turns — force final answer
        if callback:
            callback("⏱️ Max turns reached. Forcing final answer...")
        messages.append({"role": "user", "content":
            "STOP SEARCHING. Return the JSON object immediately with whatever "
            "data you found. If fields are missing, use null or empty arrays."})
        try:
            final = await self.client.chat.completions.create(model=model, messages=messages)
            return self._clean_json(final.choices[0].message.content), 12
        except Exception:
            return None, 12

    # ── Web Search ───────────────────────────────────────────────────────
    async def _perform_search(self, query):
        try:
            if ASYNC_SEARCH:
                async with AsyncDDGS() as ddgs:
                    results = [r async for r in ddgs.text(query, max_results=12)]
            else:
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(
                    None, lambda: list(DDGS(timeout=30).text(query, max_results=12)))

            if not results:
                return [{"error": "No search results found."}]

            all_emails, all_phones = [], []
            website, contact_page = None, None
            best_dir_url = None
            output = []

            for r in results:
                snippet = r.get("body", r.get("snippet", ""))
                title, url = r.get("title", ""), r.get("href", r.get("link", ""))
                url_lower = url.lower()
                is_dir = any(d in url_lower for d in SKIP_DOMAINS)

                if not is_dir and not contact_page:
                    if any(kw.lower() in url_lower for kw in self._contact_kw) or "contact" in url_lower:
                        contact_page = url

                if not website and url and not is_dir:
                    website = url

                if is_dir and not best_dir_url and url:
                    best_dir_url = url

                all_emails.extend(EMAIL_RE.findall(snippet))
                for p in re.findall(r'[\d]{10,15}\+?|\+[\d\s\-]{10,20}', snippet):
                    cleaned = re.sub(r'[^\d]', '', p)
                    if len(cleaned) >= 10:
                        all_phones.append(cleaned)

                output.append({"title": title, "snippet": snippet, "url": url})

            # Fetch contact page and homepage; fall back to directory if nothing else
            targets = [t for t in [contact_page, website] if t]
            if not targets and best_dir_url:
                targets = [best_dir_url]

            page_preview, fetched = "", set()
            for target in targets[:2]:
                if target and target not in fetched:
                    fetched.add(target)
                    page = await self._fetch_page(target)
                    all_emails.extend(page.get("emails_found", []))
                    all_phones.extend(page.get("phones_found", []))
                    if not page_preview:
                        page_preview = page.get("page_text_preview", "")

            output.insert(0, {
                "CONTACT_INFO_FOUND": bool(all_emails or all_phones or page_preview),
                "website": website, "contact_page": contact_page,
                "all_emails": _filter_emails(all_emails)[:10],
                "all_phones": list(set(all_phones))[:10],
                "page_preview": page_preview[:2500],
                "no_official_site": website is None,
                "instruction": "USE THESE VALUES IN YOUR JSON RESPONSE. Look for address in page_preview. If no_official_site is true, try a different search query.",
            })
            return output
        except Exception as e:
            return [{"error": f"Search failed: {e}"}]

    # ── Fetch Page ───────────────────────────────────────────────────────
    async def _fetch_page(self, url):
        try:
            http = await self._get_http()
            resp = await http.get(url)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            base_url = "/".join(url.split("/")[:3])

            # Navigate to contact page if on homepage
            if not any(x in url.lower() for x in ["contact", "iletisim", "kontakt", "contacto"]):
                soup, html, url = await self._find_contact_page(soup, base_url, http, html, url)

            # Extract emails
            emails = list(set(EMAIL_RE.findall(html)))
            for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
                mailto = a.get("href", "").replace("mailto:", "").split("?")[0].strip()
                if "@" in mailto and mailto not in emails:
                    emails.append(mailto)

            # Cloudflare protected emails
            for cf in re.findall(r'data-cfemail="([^"]+)"', html):
                try:
                    r = int(cf[:2], 16)
                    decoded = "".join(chr(int(cf[i:i+2], 16) ^ r) for i in range(2, len(cf), 2))
                    if "@" in decoded and decoded not in emails:
                        emails.append(decoded)
                except Exception:
                    pass

            # Emails from text content
            for e in EMAIL_RE.findall(soup.get_text(separator=" ")):
                if e not in emails:
                    emails.append(e)

            emails = _filter_emails(emails)

            # Extract phones
            phones_raw = []
            for pat in PHONE_PATTERNS:
                for m in re.findall(pat, html, re.IGNORECASE):
                    if isinstance(m, str):
                        phones_raw.append(m)
            for link in soup.find_all("a", href=re.compile(r"^tel:")):
                phones_raw.append(link.get("href", "").replace("tel:", "").strip())

            # Clean HTML for text
            for el in soup(["script", "style", "noscript"]):
                el.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(separator=" "))

            # Extract address hints
            addr_markers = ["address", "location", "hq", "office", "box ",
                           "street", "road", "avenue", "suite", "floor"]
            addr_markers.extend(k.lower() for k in self._address_kw)
            address_parts = []
            text_lower = text.lower()
            for marker in addr_markers:
                idx = text_lower.find(marker)
                if idx != -1:
                    candidate = text[max(0, idx-50):min(len(text), idx+150)].strip()
                    if len(candidate) > 10:
                        address_parts.append(candidate)

            footer = soup.find("footer")
            if footer:
                ft = re.sub(r"\s+", " ", footer.get_text(separator=" ").strip())
                if len(ft) < 500:
                    address_parts.append(f"Footer: {ft}")

            final_text = text[:2500]
            addr_text = " | ".join(address_parts[:3])
            if addr_text:
                final_text += f"\n\nPossible Address Info: {addr_text}"

            return {
                "url": url,
                "emails_found": list(set(emails))[:10],
                "phones_found": _clean_phones(phones_raw)[:10],
                "page_text_preview": final_text,
            }
        except Exception as e:
            return {"error": f"Failed to fetch page: {e}"}

    async def _find_contact_page(self, soup, base_url, http, html, url):
        """Try to navigate from homepage to contact page."""
        # Method 1: Find contact links in page (try up to 3)
        tried = 0
        for a in soup.find_all("a", href=True):
            link_text = a.get_text().strip().lower()
            href_val = a["href"].lower()
            if any(k.lower() in link_text or k.lower() in href_val for k in self._contact_kw) or "contact" in href_val:
                raw = a["href"]
                follow = (base_url + raw) if raw.startswith("/") else raw if raw.startswith("http") else None
                if follow:
                    try:
                        r = await http.get(follow)
                        if r.status_code == 200 and len(r.text) > 300:
                            return BeautifulSoup(r.text, "html.parser"), r.text, follow
                    except Exception:
                        pass
                    tried += 1
                    if tried >= 3:
                        break

        # Method 2: Try common contact paths
        for path in CONTACT_PATHS:
            try:
                test_url = base_url + path
                r = await http.get(test_url)
                if r.status_code == 200 and len(r.text) > 500:
                    return BeautifulSoup(r.text, "html.parser"), r.text, test_url
            except Exception:
                continue

        return soup, html, url

    def _clean_json(self, text):
        if not text:
            return None
        text = text.strip()
        # Strip markdown code fences
        if "```" in text:
            for marker in ["```json", "```"]:
                if marker in text:
                    start = text.find(marker) + len(marker)
                    end = text.rfind("```")
                    if end > start:
                        text = text[start:end].strip()
                    break
        # Find JSON object boundaries
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j > i:
            text = text[i:j+1]
        return text
