"""
DeepSeek Smart Contact Finder v3.0
AI-powered company contact search with multi-strategy web scraping & tool-calling.

Changes from v2.0:
  - FIX: contact/address keywords are now passed as call-local parameters instead of
    mutable instance state, so a single DeepSeekClient can safely handle multiple
    companies concurrently (e.g. via asyncio.gather) without cross-contamination.
  - PERF: contact-path probing (/contact, /about, /impressum, ...) now runs
    concurrently (bounded) instead of one-at-a-time with an early break.
  - PERF: web search now retries with backoff (DDGS is rate-limit prone).
  - PERF: a global semaphore caps concurrent outbound HTTP fetches so bulk runs
    don't hammer targets or trip your own rate limits.
  - Removed the unused/dead `_find_contact_page` method (was never called).

Features:
  - Multi-strategy search (auto-retry with different queries)
  - Aggressive auto-fetch of contact pages (now concurrent probing)
  - AI-powered English company name translation
  - Structured data (JSON-LD) & <address> tag extraction
  - HTTP retry logic with exponential backoff
  - Social media link extraction
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

# ── Constants ────────────────────────────────────────────────────────────────

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
    'tiktok.com', 'pinterest.com', 'wikipedia.org', 'reddit.com',
])

SOCIAL_DOMAINS = {
    'facebook.com': 'facebook', 'linkedin.com': 'linkedin',
    'instagram.com': 'instagram', 'twitter.com': 'twitter',
    'x.com': 'twitter',
}

JUNK_EMAIL_WORDS = ['example', 'test', 'sample', 'your@', 'domain', 'wix',
                    'wordpress', 'sentry', 'schema', 'noreply', 'no-reply',
                    '.png', '.jpg', '.gif', 'sentry.io', 'cloudflare',
                    'placeholder', '@example', '@test']

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

CONTACT_PATHS = [
    "/contact", "/contact-us", "/contacts", "/en/contact", "/en/contact-us",
    "/iletisim", "/tr/iletisim", "/kontakt", "/de/kontakt",
    "/contacto", "/es/contacto", "/about/contact", "/about-us/contact",
    "/contact.html", "/contactus", "/reach-us", "/get-in-touch",
    "/about", "/about-us", "/en/about", "/en/about-us",
    "/impressum", "/imprint",
]

PHONE_PATTERNS = [
    r'\d{10,15}\+', r'\+\d{10,15}',
    r'\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}',
    r'\+\d{1,3}[\s\-]?\(\d+\)[\s\-]?[\d\s\.\-]+',
    r'(?:tel|phone|fax|call|mobile|whatsapp|gsm|telefon|telefono)[\s:]+([+\d\s\-()./]+)',
    r'0\d{9,12}',
    r'(?:\+90|0)?\s?[2-5]\d{2}\s?\d{3}\s?\d{2}\s?\d{2}',
    r'(?:\+\d{1,3})?\s?\(0?\d{2,4}\)\s?[\d\s\.\-]{6,}',
    r'href="tel:([^"]+)"',
    r'href="whatsapp://send\?phone=(\d+)"',
]

DEFAULT_CONTACT_KW = ["Contact", "İletişim", "Kontakt", "Contacto", "Contato"]
DEFAULT_ADDRESS_KW = ["Address", "Adres", "Adresse", "Dirección", "Endereço"]

# Bound how many outbound HTTP fetches can run at once, process-wide.
_FETCH_SEMAPHORE = asyncio.Semaphore(8)
# Bound how many contact-path probes run concurrently per company.
_PROBE_CONCURRENCY = 5

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the internet for company contact details, websites, emails, phones. Use different query variations for better results.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query — try variations like '<company> <country>', '<company> contact email', '<company> official website'"}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "fetch_page",
        "description": "Fetch a webpage and extract contact info (emails, phones, addresses). Always fetch the contact page if you find one.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL to fetch — prefer /contact, /contact-us, /about pages"}
        }, "required": ["url"]}
    }},
]


# ── Utility Functions ────────────────────────────────────────────────────────

def _filter_emails(emails):
    """Deduplicate and remove junk emails."""
    cleaned = set()
    for e in emails:
        e = e.strip().lower()
        if e and not any(w in e for w in JUNK_EMAIL_WORDS):
            if not e.endswith('.css') and not e.endswith('.js') and '@' in e:
                cleaned.add(e)
    return list(cleaned)


def _clean_phones(raw_phones):
    """Deduplicate and normalize phone numbers."""
    seen, out = set(), []
    for p in raw_phones:
        cleaned = re.sub(r'[^\d+]', '', str(p))
        if cleaned.startswith('00') and len(cleaned) > 10:
            cleaned = '+' + cleaned[2:]
        if len(cleaned) >= 10 and cleaned not in seen:
            seen.add(cleaned)
            if not cleaned.startswith('+') and len(cleaned) > 10:
                cleaned = '+' + cleaned
            out.append(cleaned)
    return out


def _extract_base_url(url):
    """Extract base URL (protocol + domain) from a full URL."""
    parts = url.split('/')
    if len(parts) >= 3:
        return '/'.join(parts[:3])
    return url


# ── Main Client ──────────────────────────────────────────────────────────────

class DeepSeekClient:
    """AI-powered company contact finder using DeepSeek + web search/scraping.

    Safe to reuse across concurrent calls to extract_company_data() — no
    call-specific state is stored on `self`; per-company context (keywords)
    is threaded through method arguments instead.
    """

    def __init__(self, api_key=None, base_url="https://api.deepseek.com"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=base_url)
        self._http = None

    async def _get_http(self):
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=25.0, follow_redirects=True,
                headers={
                    "User-Agent": _random_ua(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── Phase 0: AI Name Correction + Translation ────────────────────────
    async def _fix_name_with_ai(self, raw_name, country_hint, callback=None):
        if callback:
            callback(f"🤖 AI analyzing company name: '{raw_name}'...")

        system = (
            "You are a world-class business intelligence analyst. Given a company name "
            "(possibly misspelled, abbreviated, or in a non-Latin script) and a country hint:\n\n"
            "1. **Correct** the company name to its proper, official spelling.\n"
            "2. **Translate** the company name into professional English. For example:\n"
            "   - 'DEMIRDÖKÜM' → 'Iron Casting' (but keep brand name as-is if it's a brand)\n"
            "   - 'Çelik Halat' → 'Steel Cable'\n"
            "   - If it's already English or a brand name, keep it as-is.\n"
            "3. **Identify** the country (in English) and its ISO 2-letter code.\n"
            "4. **Provide** translations for 'Contact' and 'Address' in the company's primary language.\n\n"
            "Output JSON ONLY:\n"
            '{"corrected_name":"...","company_name_english":"...","country":"...","country_code":"XX",'
            '"language_code":"en",'
            '"keywords":{"contact_page":["Contact","LocalWord"],"address":["Address","LocalWord"]}}'
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
                eng = data.get('company_name_english', '')
                corr = data.get('corrected_name', raw_name)
                callback(f"✅ Corrected: '{corr}' | English: '{eng}' | Country: {data.get('country', '?')} ({data.get('country_code', '?')})")
            return data
        except Exception as e:
            if callback:
                callback(f"⚠️ AI name analysis failed: {e}")
            return {"corrected_name": raw_name, "company_name_english": raw_name,
                    "country": country_hint or "", "country_code": "",
                    "keywords": {"contact_page": DEFAULT_CONTACT_KW, "address": DEFAULT_ADDRESS_KW}}

    # ── Main Pipeline ────────────────────────────────────────────────────
    async def extract_company_data(self, system_prompt, buyer_name, country,
                                   model="deepseek-chat", callback=None):
        # Phase 0 — fix name + translate
        ai_meta = await self._fix_name_with_ai(buyer_name, country, callback)
        corrected = ai_meta.get("corrected_name", buyer_name)
        english_name = ai_meta.get("company_name_english", "")
        country_english = ai_meta.get("country", country)
        country_code = ai_meta.get("country_code", "")

        # NOTE: these are call-local now, not stored on self — safe for concurrent
        # calls sharing one DeepSeekClient instance.
        contact_kw = ai_meta.get("keywords", {}).get("contact_page") or DEFAULT_CONTACT_KW
        address_kw = ai_meta.get("keywords", {}).get("address") or DEFAULT_ADDRESS_KW

        enhanced_prompt = system_prompt + (
            f"\n\nIMPORTANT CONTEXT FROM PHASE 0 ANALYSIS:\n"
            f"- Corrected company name: '{corrected}'\n"
            f"- English translation: '{english_name}'\n"
            f"- Country (English): '{country_english}'\n"
            f"- Country code: '{country_code}'\n"
            f"- Use these values in your final JSON output for company_name_english, "
            f"country_english, and country_code fields.\n"
            f"- Contact page keywords in local language: {contact_kw}\n"
        )

        messages = [
            {"role": "system", "content": enhanced_prompt},
            {"role": "user", "content": (
                f"Find contact information for company: '{corrected}' "
                f"(original name: '{buyer_name}') located in '{country}'."
            )},
        ]
        if callback:
            callback(f"🚀 Starting search for: {corrected}")

        for turn in range(14):
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
                        result = await self._perform_search(q, contact_kw, address_kw, callback=callback)
                    elif tc.function.name == "fetch_page":
                        u = args.get("url", "")
                        if callback: callback(f"🌐 Turn {turn+1}: Scraping '{u}'...")
                        result = await self._fetch_page_with_retry(u, address_kw)
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
            "data you found. If fields are missing, use null or empty arrays. "
            f"IMPORTANT: Set company_name_english to '{english_name}', "
            f"country_english to '{country_english}', country_code to '{country_code}'."})
        try:
            final = await self.client.chat.completions.create(model=model, messages=messages)
            return self._clean_json(final.choices[0].message.content), 14
        except Exception:
            return None, 14

    # ── Web Search (Multi-Strategy, with retry) ──────────────────────────
    async def _run_ddgs_search(self, query, max_results=15):
        if ASYNC_SEARCH:
            async with AsyncDDGS() as ddgs:
                return [r async for r in ddgs.text(query, max_results=max_results)]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: list(DDGS(timeout=30).text(query, max_results=max_results)))

    async def _perform_search(self, query, contact_kw, address_kw, callback=None, max_retries=2):
        # Retry the search itself — DDGS is prone to transient rate-limit errors,
        # and previously a single hiccup here killed the whole tool call.
        results, last_err = None, None
        for attempt in range(max_retries + 1):
            try:
                results = await self._run_ddgs_search(query)
                break
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    if callback: callback(f"   ⚠️ Search attempt {attempt+1} failed ({e}), retrying...")
                    await asyncio.sleep(1.5 * (attempt + 1))
        if results is None:
            return [{"error": f"Search failed after retries: {last_err}. Try a different query."}]

        try:
            if not results:
                return [{"error": "No search results found. Try a different query variation."}]

            all_emails, all_phones = [], []
            website, contact_page = None, None
            best_dir_url = None
            social_links = {}
            output = []

            for r in results:
                snippet = r.get("body", r.get("snippet", ""))
                title, url = r.get("title", ""), r.get("href", r.get("link", ""))
                url_lower = url.lower()
                is_dir = any(d in url_lower for d in SKIP_DOMAINS)

                for domain, platform in SOCIAL_DOMAINS.items():
                    if domain in url_lower and platform not in social_links:
                        social_links[platform] = url

                if not is_dir and not contact_page:
                    if any(kw.lower() in url_lower for kw in contact_kw) or "contact" in url_lower:
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

            # ── Auto-fetch: website homepage ──
            page_preview, fetched = "", set()
            if website:
                if callback: callback(f"   📄 Auto-fetching homepage: {website}")
                page = await self._fetch_page_with_retry(website, address_kw)
                all_emails.extend(page.get("emails_found", []))
                all_phones.extend(page.get("phones_found", []))
                page_preview = page.get("page_text_preview", "")
                fetched.add(website)

                base_url = _extract_base_url(website)

                if contact_page and contact_page not in fetched:
                    if callback: callback(f"   📞 Auto-fetching contact page: {contact_page}")
                    cp_data = await self._fetch_page_with_retry(contact_page, address_kw)
                    all_emails.extend(cp_data.get("emails_found", []))
                    all_phones.extend(cp_data.get("phones_found", []))
                    cp_text = cp_data.get("page_text_preview", "")
                    if cp_text:
                        page_preview += f"\n\n--- CONTACT PAGE CONTENT ---\n{cp_text}"
                    fetched.add(contact_page)

                # ── Auto-probe: common contact paths, concurrently ──
                # Previously this tried up to 8 paths one-at-a-time, breaking on
                # first success — worst case 8 sequential round trips. Now we
                # fire a bounded batch concurrently and take the first hit.
                if not contact_page:
                    candidate_paths = [p for p in CONTACT_PATHS[:8]
                                        if (base_url + p) not in fetched]
                    if candidate_paths:
                        if callback: callback(f"   🔍 Probing {len(candidate_paths)} contact paths on {base_url} (concurrently)...")
                        found = await self._probe_paths_concurrently(base_url, candidate_paths)
                        if found:
                            probe_url = found
                            if callback: callback(f"   ✅ Found contact page at: {probe_url}")
                            contact_page = probe_url
                            cp_data = await self._fetch_page_with_retry(probe_url, address_kw)
                            all_emails.extend(cp_data.get("emails_found", []))
                            all_phones.extend(cp_data.get("phones_found", []))
                            cp_text = cp_data.get("page_text_preview", "")
                            if cp_text:
                                page_preview += f"\n\n--- CONTACT PAGE CONTENT ---\n{cp_text}"
                            fetched.add(probe_url)
            elif best_dir_url:
                if callback: callback(f"   📄 No official site found, fetching directory: {best_dir_url}")
                page = await self._fetch_page_with_retry(best_dir_url, address_kw)
                all_emails.extend(page.get("emails_found", []))
                all_phones.extend(page.get("phones_found", []))
                page_preview = page.get("page_text_preview", "")

            output.insert(0, {
                "CONTACT_INFO_FOUND": bool(all_emails or all_phones or page_preview),
                "website": website, "contact_page": contact_page,
                "all_emails": _filter_emails(all_emails)[:15],
                "all_phones": _clean_phones(all_phones)[:10],
                "social_links": social_links,
                "page_preview": page_preview[:4000],
                "no_official_site": website is None,
                "instruction": (
                    "USE THESE VALUES IN YOUR JSON RESPONSE. "
                    "The emails and phones listed above were extracted directly from the company's website and are VERIFIED. "
                    "Include ALL of them in your output. "
                    "Look for address in page_preview — check for street names, postal codes, city names. "
                    "If you still need more data, try: "
                    "1) fetch_page on a different page of the website (e.g. /about, /impressum) "
                    "2) web_search with a different query like '<company> email phone address' "
                    "If no_official_site is true, try web_search with '<company> official website' or '<company> <country> contact'."
                ),
            })
            return output
        except Exception as e:
            return [{"error": f"Search failed: {e}. Try a different query."}]

    async def _probe_paths_concurrently(self, base_url, paths):
        """Check candidate contact-page paths concurrently; return the first
        that looks valid (200 + substantial body), or None."""
        http = await self._get_http()
        sem = asyncio.Semaphore(_PROBE_CONCURRENCY)

        async def check(path):
            probe_url = base_url + path
            async with sem:
                try:
                    resp = await http.get(probe_url)
                    if resp.status_code == 200 and len(resp.text) > 500:
                        return probe_url
                except Exception:
                    pass
            return None

        results = await asyncio.gather(*(check(p) for p in paths))
        for r in results:
            if r:
                return r
        return None

    # ── Fetch Page with Retry ────────────────────────────────────────────
    async def _fetch_page_with_retry(self, url, address_kw, max_retries=2):
        """Fetch a page with retry logic on failure."""
        last_error = None
        for attempt in range(max_retries + 1):
            result = await self._fetch_page(url, address_kw)
            if "error" not in result:
                return result
            last_error = result.get("error", "")
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))  # Backoff: 1.5s, 3s
        return {"error": last_error, "emails_found": [], "phones_found": [], "page_text_preview": ""}

    # ── Fetch Page ───────────────────────────────────────────────────────
    async def _fetch_page(self, url, address_kw):
        async with _FETCH_SEMAPHORE:  # cap process-wide concurrent fetches
            try:
                http = await self._get_http()
                resp = await http.get(url)
                resp.raise_for_status()
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")

                # ── Extract emails ──
                emails = list(set(EMAIL_RE.findall(html)))

                for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
                    mailto = a.get("href", "").replace("mailto:", "").split("?")[0].strip()
                    if "@" in mailto and mailto not in emails:
                        emails.append(mailto)

                for cf in re.findall(r'data-cfemail="([^"]+)"', html):
                    try:
                        r = int(cf[:2], 16)
                        decoded = "".join(chr(int(cf[i:i+2], 16) ^ r) for i in range(2, len(cf), 2))
                        if "@" in decoded and decoded not in emails:
                            emails.append(decoded)
                    except Exception:
                        pass

                for e in EMAIL_RE.findall(soup.get_text(separator=" ")):
                    if e not in emails:
                        emails.append(e)

                emails = _filter_emails(emails)

                # ── Extract phones ──
                phones_raw = []
                for pat in PHONE_PATTERNS:
                    for m in re.findall(pat, html, re.IGNORECASE):
                        if isinstance(m, str):
                            phones_raw.append(m)
                for link in soup.find_all("a", href=re.compile(r"^tel:")):
                    phones_raw.append(link.get("href", "").replace("tel:", "").strip())
                for link in soup.find_all("a", href=re.compile(r"whatsapp", re.I)):
                    href = link.get("href", "")
                    nums = re.findall(r'\d{10,15}', href)
                    phones_raw.extend(nums)

                for el in soup(["script", "style", "noscript", "svg", "path"]):
                    el.decompose()
                text = re.sub(r"\s+", " ", soup.get_text(separator=" "))

                # ── Extract addresses ──
                address_parts = []

                for addr_tag in soup.find_all("address"):
                    addr_text = re.sub(r"\s+", " ", addr_tag.get_text(separator=" ")).strip()
                    if len(addr_text) > 10:
                        address_parts.append(f"HTML <address>: {addr_text}")

                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        ld = json.loads(script.string or "")
                        if isinstance(ld, dict):
                            addr = ld.get("address", ld.get("location", {}).get("address", {}))
                            if isinstance(addr, dict):
                                parts = [addr.get("streetAddress", ""),
                                         addr.get("addressLocality", ""),
                                         addr.get("addressRegion", ""),
                                         addr.get("postalCode", ""),
                                         addr.get("addressCountry", "")]
                                full_addr = ", ".join(p for p in parts if p)
                                if full_addr:
                                    address_parts.append(f"Structured: {full_addr}")
                            elif isinstance(addr, str) and len(addr) > 5:
                                address_parts.append(f"Structured: {addr}")
                            for field in ["email", "telephone", "phone", "faxNumber"]:
                                val = ld.get(field)
                                if val:
                                    if "@" in str(val) and val not in emails:
                                        emails.append(val)
                                    elif re.sub(r'\D', '', str(val)) and len(re.sub(r'\D', '', str(val))) >= 7:
                                        phones_raw.append(str(val))
                    except Exception:
                        pass

                addr_markers = ["address", "location", "headquarter", "hq", "office",
                               "street", "road", "avenue", "suite", "floor", "p.o. box",
                               "postal", "zip code"]
                addr_markers.extend(k.lower() for k in address_kw)
                text_lower = text.lower()
                for marker in addr_markers:
                    idx = text_lower.find(marker)
                    if idx != -1:
                        candidate = text[max(0, idx-30):min(len(text), idx+200)].strip()
                        if len(candidate) > 10:
                            address_parts.append(candidate)

                footer = soup.find("footer")
                if footer:
                    ft = re.sub(r"\s+", " ", footer.get_text(separator=" ").strip())
                    if 10 < len(ft) < 600:
                        address_parts.append(f"Footer: {ft}")
                        emails.extend(_filter_emails(EMAIL_RE.findall(ft)))
                        for pat in PHONE_PATTERNS[:4]:
                            for m in re.findall(pat, ft, re.IGNORECASE):
                                if isinstance(m, str):
                                    phones_raw.append(m)

                social = {}
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "").lower()
                    for domain, platform in SOCIAL_DOMAINS.items():
                        if domain in href and platform not in social:
                            social[platform] = a.get("href", "")

                final_text = text[:3500]
                addr_text = " | ".join(address_parts[:5])
                if addr_text:
                    final_text += f"\n\nPossible Address Info: {addr_text}"
                if social:
                    final_text += f"\n\nSocial Media: {json.dumps(social)}"

                emails = _filter_emails(emails)

                return {
                    "url": url,
                    "emails_found": list(set(emails))[:15],
                    "phones_found": _clean_phones(phones_raw)[:10],
                    "page_text_preview": final_text,
                    "address_hints": address_parts[:5],
                    "social_links": social,
                }
            except httpx.HTTPStatusError as e:
                return {"error": f"HTTP {e.response.status_code} fetching {url}"}
            except httpx.ConnectError:
                return {"error": f"Connection failed for {url} — site may be down"}
            except Exception as e:
                return {"error": f"Failed to fetch page: {e}"}

    def _clean_json(self, text):
        if not text:
            return None
        text = text.strip()
        if "```" in text:
            for marker in ["```json", "```"]:
                if marker in text:
                    start = text.find(marker) + len(marker)
                    end = text.rfind("```")
                    if end > start:
                        text = text[start:end].strip()
                    break
        i, j = text.find("{"), text.rfind("}")
        if i != -1 and j > i:
            text = text[i:j+1]
        return text
