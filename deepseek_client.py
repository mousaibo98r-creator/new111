"""
DeepSeek Smart Contact Finder — Pro Edition
AI-powered company contact search with web scraping & tool-calling.

Features:
  - AI name correction (multilingual)
  - Multi-query DuckDuckGo search (12 results)
  - Automatic contact page discovery (link scan + common paths)
  - Cloudflare email decoding, mailto: extraction, JSON-LD parsing
  - International phone extraction (25+ patterns)
  - Retry with exponential backoff on HTTP failures
  - In-session page cache to avoid duplicate fetches
  - Robust JSON cleaning (handles markdown wrappers)
"""

import os, json, re, asyncio, time, httpx
from openai import AsyncOpenAI
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse

# ── Search Engine Imports ────────────────────────────────────────────────────
try:
    from duckduckgo_search import AsyncDDGS
    ASYNC_SEARCH = True
except ImportError:
    ASYNC_SEARCH = False
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

# ── Optional User Agent Rotation ─────────────────────────────────────────────
try:
    from fake_useragent import UserAgent
    _UA = UserAgent()
    _random_ua = lambda: _UA.random
except ImportError:
    _random_ua = lambda: (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

# ── Domains to Always Skip ──────────────────────────────────────────────────
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
    'tiktok.com', 'pinterest.com', 'reddit.com', 'wikipedia.org',
    'slideshare.net', 'docplayer.net', 'monster.com', 'careerbuilder.com',
])

# ── Junk Email Patterns ─────────────────────────────────────────────────────
JUNK_EMAIL_WORDS = [
    'example', 'test', 'sample', 'your@', 'domain', 'wix',
    'wordpress', 'sentry', 'schema', 'noreply', 'no-reply',
    '.png', '.jpg', '.gif', 'donotreply', 'webmaster@localhost',
    '@example.', '@test.', '@sample.', '@dummy.',
]

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# ── Contact Page Paths to Try ────────────────────────────────────────────────
CONTACT_PATHS = [
    "/contact", "/contact-us", "/contacts", "/en/contact", "/en/contact-us",
    "/iletisim", "/tr/iletisim", "/kontakt", "/de/kontakt",
    "/contacto", "/es/contacto", "/about/contact", "/about-us/contact",
    "/impressum", "/legal", "/reach-us", "/get-in-touch",
    "/about", "/about-us", "/support", "/customer-service",
]

# ── Phone Extraction Patterns (international) ────────────────────────────────
PHONE_PATTERNS = [
    # International: +CC XXXXXXXXX
    re.compile(r'\+[1-9]\d{0,2}[\s.\-()]*\d{1,4}[\s.\-()]*\d{1,4}[\s.\-()]*\d{1,4}[\s.\-()]*\d{0,4}'),
    # Spaced European: +XX X XX XX XX XX
    re.compile(r'\+\d{2}[\s]\d(?:[\s]\d{2}){4}'),
    # US/Canada: +1 (XXX) XXX-XXXX
    re.compile(r'\+?1[\s.\-()]?\(?\d{3}\)?[\s.\-()]?\d{3}[\s.\-()]?\d{4}'),
    # UK: +44 XXXX XXXXXX
    re.compile(r'\+44[\s.\-()]?(?:0)?\d{2,4}[\s.\-()]?\d{3,4}[\s.\-()]?\d{3,4}'),
    # Turkey: +90 XXX XXX XX XX
    re.compile(r'\+90[\s.\-()]?\d{3}[\s.\-()]?\d{3}[\s.\-()]?\d{2}[\s.\-()]?\d{2}'),
    # Germany: +49 XXXX XXXXXXX
    re.compile(r'\+49[\s.\-()]?\d{2,5}[\s.\-()]?\d{3,8}'),
    # Russia/CIS: +7 XXX XXX XX XX
    re.compile(r'\+7[\s.\-()]?\d{3}[\s.\-()]?\d{3}[\s.\-()]?\d{2}[\s.\-()]?\d{2}'),
    # Middle East: +971, +966, +962, etc.
    re.compile(r'\+9[6-7]\d[\s.\-()]?\d{1,2}[\s.\-()]?\d{3,4}[\s.\-()]?\d{3,4}'),
    # China: +86 XXX XXXX XXXX
    re.compile(r'\+86[\s.\-()]?\d{3}[\s.\-()]?\d{4}[\s.\-()]?\d{4}'),
    # India: +91 XXXXX XXXXX
    re.compile(r'\+91[\s.\-()]?\d{5}[\s.\-()]?\d{5}'),
    # Generic labeled: tel: / phone: / fax: / mobile:
    re.compile(r'(?:tel|phone|fax|call|mobile|telephone)[:\s]+([\+\d\s\-()./]{7,})', re.I),
    # tel: URI
    re.compile(r'tel:([\+]?[\d\s\-.\(\)]{7,})'),
    # Local numbers with area code: 0XXX XXX XXXX
    re.compile(r'0\d{9,12}'),
    # Turkish local: 0XXX XXX XX XX
    re.compile(r'(?:\+90|0)?\s?[2-5]\d{2}\s?\d{3}\s?\d{2}\s?\d{2}'),
    # Parenthesized area code
    re.compile(r'(?:\+\d{1,3})?\s?\(0?\d{2,4}\)\s?[\d\s.\-]{6,}'),
]

# ── Tool Definitions for DeepSeek ────────────────────────────────────────────
TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": (
            "Search the internet for company contact details, websites, emails, and phones. "
            "Returns search results AND a pre-fetched summary with verified emails/phones from top pages."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "fetch_page",
        "description": (
            "Fetch a webpage and extract contact info (emails, phones, address hints). "
            "Automatically follows links to contact/about pages if the URL is a homepage."
        ),
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL to fetch"}
        }, "required": ["url"]}
    }},
]


# ── Utility Functions ────────────────────────────────────────────────────────

def _normalize_url(url):
    """Normalize a URL: add scheme, lowercase netloc, strip www."""
    if not url or not url.strip():
        return None
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        p = urlparse(url)
        netloc = (p.netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if not netloc:
            return None
        return urlunparse((p.scheme or "https", netloc, p.path or "", "", "", ""))
    except Exception:
        return None


def _homepage_url(url):
    """Extract the homepage root from any URL."""
    n = _normalize_url(url)
    if not n:
        return None
    p = urlparse(n)
    return f"{p.scheme}://{p.netloc}/"


def _filter_emails(emails):
    """Deduplicate and remove junk emails."""
    seen = set()
    out = []
    for e in emails:
        e = (e or "").strip()
        if not e or "@" not in e:
            continue
        el = e.lower()
        if el in seen:
            continue
        if any(w in el for w in JUNK_EMAIL_WORDS):
            continue
        seen.add(el)
        out.append(e)

    # Prioritize role-based emails
    role_prefixes = ['info@', 'sales@', 'export@', 'contact@', 'support@',
                     'inquiries@', 'hello@', 'office@', 'admin@', 'mail@']
    role = [e for e in out if any(e.lower().startswith(p) for p in role_prefixes)]
    other = [e for e in out if e not in role]
    return (role + other)[:10]


def _clean_phones(raw_phones):
    """Deduplicate and normalize phone numbers."""
    seen, out = set(), []
    for p in raw_phones:
        # Clean: keep only digits and leading +
        p_str = str(p).strip()
        cleaned = re.sub(r'^(tel:|phone:|fax:|mobile:)', '', p_str, flags=re.I).strip()
        cleaned = re.sub(r'[^\d+]', '', cleaned)
        # Fix multiple + signs
        if cleaned.startswith('+'):
            cleaned = '+' + cleaned[1:].replace('+', '')
        else:
            cleaned = cleaned.replace('+', '')
        digits = re.sub(r'\D', '', cleaned)
        if len(digits) >= 8 and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out[:10]


def _extract_phones_from_text(text):
    """Extract phone numbers from text using all patterns."""
    if not text:
        return []
    phones = []
    for pattern in PHONE_PATTERNS:
        for m in pattern.findall(text):
            if isinstance(m, tuple):
                phone = ''.join(str(g) for g in m if g)
            else:
                phone = str(m).strip()
            if phone and len(re.sub(r'\D', '', phone)) >= 7:
                phones.append(phone)
    # Also get standalone international numbers
    for m in re.findall(r'\+\d{1,3}[\d\s.\-()]{7,}', text):
        phones.append(m.strip())
    return phones


# ── Page Cache ───────────────────────────────────────────────────────────────

class _PageCache:
    """Simple in-memory cache for fetched pages (avoids duplicate fetches)."""
    def __init__(self, ttl=600):
        self._cache = {}
        self._ttl = ttl

    def get(self, url):
        key = (url or "").lower().strip()
        entry = self._cache.get(key)
        if entry and (time.time() - entry["ts"]) < self._ttl:
            return entry["data"]
        return None

    def set(self, url, data):
        key = (url or "").lower().strip()
        self._cache[key] = {"data": data, "ts": time.time()}

    def clear(self):
        self._cache.clear()


# ══════════════════════════════════════════════════════════════════════════════
# DeepSeekClient — the main public class
# ══════════════════════════════════════════════════════════════════════════════

class DeepSeekClient:
    """AI-powered company contact finder using DeepSeek + web search/scraping."""

    def __init__(self, api_key=None, base_url="https://api.deepseek.com"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=base_url)
        self._http = None
        self._cache = _PageCache(ttl=600)
        self._contact_kw = ["Contact", "İletişim", "Kontakt", "Contacto",
                            "Contact Us", "Get in Touch", "Reach Us"]
        self._address_kw = ["Address", "Adres", "Adresse", "Dirección",
                            "Indirizzo", "Endereço"]

    async def _get_http(self):
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=25.0,
                follow_redirects=True,
                headers={
                    "User-Agent": _random_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8,de;q=0.7,es;q=0.6,ar;q=0.5",
                },
            )
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._cache.clear()

    # ── Phase 0: AI Name Correction ──────────────────────────────────────
    async def _fix_name_with_ai(self, raw_name, country_hint, callback=None):
        if callback:
            callback(f"🤖 AI analyzing company name: '{raw_name}'...")

        system = (
            "You are a data expert specializing in company name validation.\n"
            "Given a company name (possibly misspelled or incomplete) and a country hint:\n"
            "1. Correct the company name to its official form.\n"
            "2. Identify the country and primary language.\n"
            "3. Provide translations for 'Contact' and 'Address' in that language.\n\n"
            "Output JSON ONLY:\n"
            '{"corrected_name":"Official Company Name","country":"Country",'
            '"language_code":"xx",'
            '"keywords":{"contact_page":["Contact","LocalWord"],'
            '"address":["Address","LocalWord"]}}'
        )
        try:
            resp = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content":
                        f"Company: '{raw_name}'. Country hint: {country_hint or 'Unknown'}"},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            corrected = data.get("corrected_name", raw_name)
            if callback:
                callback(f"✅ Corrected name: '{corrected}'")
            return data
        except Exception:
            return {
                "corrected_name": raw_name,
                "country": country_hint or "",
                "language_code": "en",
                "keywords": {
                    "contact_page": self._contact_kw,
                    "address": self._address_kw,
                },
            }

    # ── Main Pipeline ────────────────────────────────────────────────────
    async def extract_company_data(self, system_prompt, buyer_name, country,
                                   model="deepseek-chat", callback=None):
        """Run full AI contact-finding pipeline. Returns (raw_json_str, turns)."""
        # Phase 0 — AI name correction
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

        max_turns = 14
        for turn in range(max_turns):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                msg = response.choices[0].message

                # No tool calls = final answer
                if not msg.tool_calls:
                    if msg.content:
                        return self._clean_json(msg.content), turn + 1
                    return None, turn + 1

                messages.append(msg)

                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")

                    if tc.function.name == "web_search":
                        q = (args.get("query") or "").strip()
                        if callback:
                            callback(f"🔎 Turn {turn+1}: Searching '{q}'...")
                        result = await self._perform_search(q)

                    elif tc.function.name == "fetch_page":
                        u = (args.get("url") or "").strip()
                        if callback:
                            callback(f"🌐 Turn {turn+1}: Scraping '{u}'...")
                        result = await self._fetch_page(u)

                    else:
                        result = {"error": f"Unknown tool: {tc.function.name}"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

            except Exception as e:
                if callback:
                    callback(f"⚠️ API Error on turn {turn+1}: {e}")
                # Don't give up immediately — try to get partial results
                if turn >= 2:
                    break
                await asyncio.sleep(1)
                continue

        # Max turns reached — force final JSON answer
        if callback:
            callback("⏱️ Max turns reached. Forcing final answer...")
        messages.append({
            "role": "user",
            "content": (
                "STOP SEARCHING. Return the JSON object immediately with whatever "
                "data you have found so far. If fields are missing, use null or "
                "empty arrays. Do NOT add any explanation — JSON ONLY."
            ),
        })
        try:
            final = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                tool_choice="none",
            )
            return self._clean_json(final.choices[0].message.content), max_turns
        except Exception:
            return None, max_turns

    # ══════════════════════════════════════════════════════════════════════
    # Web Search
    # ══════════════════════════════════════════════════════════════════════

    async def _perform_search(self, query):
        """Search DuckDuckGo + auto-fetch top pages for verified data."""
        try:
            results = await self._ddg_search(query, max_results=12)
            if not results:
                return [{"error": "No search results found."}]

            all_emails, all_phones = [], []
            website, contact_page = None, None
            output = []

            for r in results:
                snippet = r.get("body", r.get("snippet", "")) or ""
                title = r.get("title", "") or ""
                url = r.get("href", r.get("link", "")) or ""
                url_lower = url.lower()

                # Skip directory/social sites
                is_dir = any(d in url_lower for d in SKIP_DOMAINS)

                # Identify contact page
                if not is_dir and not contact_page:
                    contact_kw_lower = [k.lower() for k in self._contact_kw]
                    if any(kw in url_lower for kw in contact_kw_lower) or "contact" in url_lower:
                        contact_page = url

                # Identify main website (first non-directory result)
                if not website and url and not is_dir:
                    website = url

                # Extract hints from snippets
                all_emails.extend(EMAIL_RE.findall(snippet))
                all_phones.extend(_extract_phones_from_text(snippet))

                output.append({"title": title, "snippet": snippet, "url": url})

            # Auto-fetch the top pages to get verified data
            page_preview = ""
            fetched = set()
            verified_emails, verified_phones = [], []

            for target in [contact_page, website]:
                if target and target not in fetched:
                    fetched.add(target)
                    page = await self._fetch_page(target)
                    if not page.get("error"):
                        verified_emails.extend(page.get("emails_found", []))
                        verified_phones.extend(page.get("phones_found", []))
                        if not page_preview:
                            page_preview = page.get("page_text_preview", "")

            # Build summary object (index 0)
            snippet_emails = _filter_emails(all_emails)
            snippet_phones = _clean_phones(all_phones)
            v_emails = _filter_emails(verified_emails)
            v_phones = _clean_phones(verified_phones)

            summary = {
                "CONTACT_INFO_FOUND": bool(v_emails or v_phones or page_preview),
                "website": _homepage_url(website) if website else None,
                "contact_page": contact_page,
                "snippet_emails_HINTS_ONLY": snippet_emails,
                "snippet_phones_HINTS_ONLY": snippet_phones,
                "verified_emails": v_emails,
                "verified_phones": v_phones,
                "page_preview": (page_preview or "")[:3000],
                "fetched_urls": list(fetched),
                "instruction": (
                    "IMPORTANT: Use verified_emails and verified_phones if present. "
                    "Snippet values are unverified HINTS — only use if no verified data. "
                    "Look for address in page_preview. "
                    "If you need more data, call fetch_page on other URLs."
                ),
            }

            return [summary] + output

        except Exception as e:
            return [{"error": f"Search failed: {e}"}]

    async def _ddg_search(self, query, max_results=12):
        """DuckDuckGo search with async/sync fallback."""
        try:
            if ASYNC_SEARCH:
                async with AsyncDDGS() as ddgs:
                    return [r async for r in ddgs.text(query, max_results=max_results)]
            else:
                return list(DDGS(timeout=30).text(query, max_results=max_results))
        except Exception:
            return []

    # ══════════════════════════════════════════════════════════════════════
    # Page Fetching (with retry + cache)
    # ══════════════════════════════════════════════════════════════════════

    async def _fetch_page(self, url):
        """Fetch a page, extract emails/phones/address, with retry and cache."""
        url_n = _normalize_url(url)
        if not url_n:
            return {"error": "Invalid URL", "url": url}

        # Check cache first
        cached = self._cache.get(url_n)
        if cached:
            return cached

        # Retry with backoff (3 attempts)
        last_error = None
        for attempt in range(3):
            try:
                result = await self._fetch_page_inner(url_n)
                self._cache.set(url_n, result)
                return result
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code in (429, 500, 502, 503, 504):
                    last_error = e
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                # Non-retryable HTTP error
                result = {"error": f"HTTP {code}", "url": url_n,
                          "emails_found": [], "phones_found": [],
                          "page_text_preview": ""}
                self._cache.set(url_n, result)
                return result
            except Exception as e:
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue

        result = {"error": f"Failed after 3 retries: {last_error}", "url": url_n,
                  "emails_found": [], "phones_found": [], "page_text_preview": ""}
        return result

    async def _fetch_page_inner(self, url):
        """Core page fetch logic (no retry, no cache)."""
        http = await self._get_http()
        resp = await http.get(url)
        resp.raise_for_status()
        html = resp.text or ""
        soup = BeautifulSoup(html, "html.parser")
        base_url = "/".join(url.split("/")[:3])

        # Auto-navigate to contact page if we're on the homepage
        current_url = url
        if not any(x in url.lower() for x in
                   ["contact", "iletisim", "kontakt", "contacto",
                    "impressum", "legal", "about", "reach", "support"]):
            soup, html, current_url = await self._find_contact_page(
                soup, base_url, http, html, url
            )

        # ── Extract Emails ───────────────────────────────────────────
        emails = set(EMAIL_RE.findall(html))

        # mailto: links
        for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
            mailto = (a.get("href", "") or "").replace("mailto:", "").split("?")[0].strip()
            if "@" in mailto:
                emails.add(mailto)

        # Cloudflare protected emails
        for cf in re.findall(r'data-cfemail="([^"]+)"', html):
            try:
                r = int(cf[:2], 16)
                decoded = "".join(
                    chr(int(cf[i:i+2], 16) ^ r) for i in range(2, len(cf), 2)
                )
                if "@" in decoded:
                    emails.add(decoded)
            except Exception:
                pass

        # Emails from visible text (catches obfuscated ones)
        text_content = soup.get_text(separator=" ")
        for e in EMAIL_RE.findall(text_content):
            emails.add(e)

        emails = _filter_emails(list(emails))

        # ── Extract Phones ───────────────────────────────────────────
        phones_raw = _extract_phones_from_text(html)

        # tel: links
        for link in soup.find_all("a", href=re.compile(r"^tel:", re.I)):
            tel = (link.get("href", "") or "").replace("tel:", "").strip()
            if tel:
                phones_raw.append(tel)

        phones = _clean_phones(phones_raw)

        # ── Extract Text Preview ─────────────────────────────────────
        for el in soup(["script", "style", "noscript", "iframe", "svg"]):
            el.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()

        # ── Extract Address ──────────────────────────────────────────
        address_parts = []

        # From JSON-LD structured data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld_data = json.loads(script.get_text(strip=True) or "{}")
                items = ld_data if isinstance(ld_data, list) else [ld_data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = str(item.get("@type", "")).lower()
                    if any(t in item_type for t in
                           ["organization", "business", "company", "localbusiness",
                            "corporation", "store", "restaurant"]):
                        addr = item.get("address", {})
                        if isinstance(addr, dict):
                            parts = [
                                addr.get("streetAddress"),
                                addr.get("addressLocality"),
                                addr.get("addressRegion"),
                                addr.get("postalCode"),
                                addr.get("addressCountry"),
                            ]
                            addr_str = ", ".join(str(p).strip() for p in parts if p)
                            if addr_str and len(addr_str) > 10:
                                address_parts.append(f"JSON-LD: {addr_str}")
                        # Also check for email/phone in JSON-LD
                        for key in ["email", "telephone", "phone"]:
                            val = item.get(key)
                            if val:
                                if "@" in str(val):
                                    emails.append(str(val))
                                elif re.sub(r'\D', '', str(val)):
                                    phones_raw.append(str(val))
            except Exception:
                pass

        # From <address> tags
        for addr_tag in soup.find_all("address"):
            addr_text = re.sub(r"\s+", " ", addr_tag.get_text(" ", strip=True))
            if 15 < len(addr_text) < 400:
                address_parts.append(addr_text)

        # From text markers
        addr_markers = ["address", "location", "headquarters", "head office",
                        "hq", "office", "registered", "p.o. box",
                        "street", "road", "avenue", "suite", "floor"]
        addr_markers.extend(k.lower() for k in self._address_kw)
        text_lower = text.lower()
        for marker in addr_markers:
            idx = text_lower.find(marker)
            if idx != -1:
                candidate = text[max(0, idx-50):min(len(text), idx+200)].strip()
                if 15 < len(candidate) < 400:
                    address_parts.append(candidate)

        # From footer
        footer = soup.find("footer")
        if footer:
            ft = re.sub(r"\s+", " ", footer.get_text(separator=" ").strip())
            if 20 < len(ft) < 600:
                address_parts.append(f"Footer: {ft}")

        # Dedupe address parts
        seen_addr = set()
        unique_addr = []
        for a in address_parts:
            al = a.lower()[:80]
            if al not in seen_addr:
                seen_addr.add(al)
                unique_addr.append(a)

        # Build preview
        final_text = text[:3000]
        if unique_addr:
            final_text += "\n\nPossible Address Info: " + " | ".join(unique_addr[:4])

        return {
            "url": current_url,
            "emails_found": _filter_emails(list(set(emails)))[:10],
            "phones_found": _clean_phones(phones_raw + phones)[:10],
            "page_text_preview": final_text,
            "address_candidates": unique_addr[:5],
        }

    # ── Contact Page Discovery ───────────────────────────────────────────

    async def _find_contact_page(self, soup, base_url, http, html, url):
        """Try to navigate from homepage to the contact page."""

        # Method 1: Scan ALL links for contact-like ones (don't stop at first)
        candidates = []
        for a in soup.find_all("a", href=True):
            link_text = (a.get_text() or "").strip().lower()
            href_val = (a.get("href") or "").strip()
            href_lower = href_val.lower()

            # Skip external links, anchors, javascript
            if href_val.startswith("#") or href_val.startswith("javascript"):
                continue

            is_contact = (
                any(k.lower() in link_text for k in self._contact_kw) or
                any(k.lower() in href_lower for k in self._contact_kw) or
                "contact" in href_lower or "iletisim" in href_lower or
                "kontakt" in href_lower or "contacto" in href_lower
            )
            if is_contact:
                if href_val.startswith("/"):
                    full_url = base_url + href_val
                elif href_val.startswith("http"):
                    full_url = href_val
                else:
                    continue
                candidates.append(full_url)

        # Try each candidate (up to 3)
        for candidate_url in candidates[:3]:
            try:
                r = await http.get(candidate_url)
                if r.status_code == 200 and len(r.text or "") > 300:
                    return BeautifulSoup(r.text, "html.parser"), r.text, candidate_url
            except Exception:
                continue

        # Method 2: Try well-known contact paths
        for path in CONTACT_PATHS:
            try:
                test_url = base_url + path
                r = await http.get(test_url)
                if r.status_code == 200 and len(r.text or "") > 500:
                    return BeautifulSoup(r.text, "html.parser"), r.text, test_url
            except Exception:
                continue

        return soup, html, url

    # ── JSON Cleaning ────────────────────────────────────────────────────

    def _clean_json(self, text):
        """Robustly extract JSON from AI response (handles markdown wrappers)."""
        if not text:
            return None
        text = text.strip()

        # Remove markdown JSON code blocks
        if "```" in text:
            # Try ```json ... ``` first
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        # Try to find JSON object boundaries
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start:end+1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Last resort: return as-is
        return text
