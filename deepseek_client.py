"""
DeepSeek Smart Contact Finder v4.0
AI-powered company contact search with multi-strategy web scraping & tool-calling.

Changes from v3.0:
  - COST: switched default model from deprecated `deepseek-chat` to `deepseek-v4-flash`
    (3× cheaper than v4-pro).
  - COST: max tool-loop turns cut from 14 → 7 (AI rarely needs >5).
  - COST: early-exit logic — if email + phone are already found, nudge AI to finalize
    instead of burning more turns.
  - COST: page_preview truncated more aggressively (4000→2000 chars) to reduce token
    bloat sent back to the AI.
  - COST: search results reduced from 15 → 8 (first page almost always has the site).
  - COST: system/instruction prompts compressed (~500 fewer tokens per call).
  - COST: Phase 0 AI name-correction is skipped for simple ASCII names, saving one
    entire API call.
  - PERF: multiple tool calls in a single turn are now executed concurrently via
    asyncio.gather instead of sequentially.

Features:
  - Multi-strategy search (auto-retry with different queries)
  - Aggressive auto-fetch of contact pages (concurrent probing)
  - AI-powered English company name translation (skipped for ASCII names)
  - Structured data (JSON-LD) & <address> tag extraction
  - HTTP retry logic with exponential backoff
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

DEFAULT_MODEL = "deepseek-v4-flash"   # 3× cheaper than v4-pro
MAX_TURNS     = 15                     # generous budget for thorough searches

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

# Common country-code → language keyword map (used when Phase 0 is skipped).
_COUNTRY_KW = {
    "TR": {"contact_page": ["Contact", "İletişim"], "address": ["Address", "Adres"]},
    "DE": {"contact_page": ["Contact", "Kontakt"], "address": ["Address", "Adresse"]},
    "ES": {"contact_page": ["Contact", "Contacto"], "address": ["Address", "Dirección"]},
    "BR": {"contact_page": ["Contact", "Contato"], "address": ["Address", "Endereço"]},
    "PT": {"contact_page": ["Contact", "Contato"], "address": ["Address", "Endereço"]},
    "FR": {"contact_page": ["Contact"], "address": ["Address", "Adresse"]},
    "IT": {"contact_page": ["Contact", "Contatti"], "address": ["Address", "Indirizzo"]},
}

# Bound how many outbound HTTP fetches can run at once, process-wide.
_FETCH_SEMAPHORE = asyncio.Semaphore(12)
# Bound how many contact-path probes run concurrently per company.
_PROBE_CONCURRENCY = 8

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for company contact info. Try query variations.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "fetch_page",
        "description": "Fetch a webpage and extract emails, phones, addresses. Prefer /contact pages.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL to fetch"}
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


def _is_simple_ascii(name):
    """Return True if the name is plain ASCII (no need for AI translation)."""
    try:
        name.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


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
                timeout=12.0, follow_redirects=True,
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
        """Call the AI to correct/translate the company name.
        Skipped for simple ASCII names to save one API call."""

        # Fast path: if name is plain ASCII, skip the API call entirely
        if _is_simple_ascii(raw_name) and country_hint:
            if callback:
                callback(f"⚡ Skipping AI name analysis (ASCII name: '{raw_name}')")
            cc = country_hint.strip().upper()[:2]
            kw = _COUNTRY_KW.get(cc, {"contact_page": DEFAULT_CONTACT_KW, "address": DEFAULT_ADDRESS_KW})
            return {
                "corrected_name": raw_name,
                "company_name_english": raw_name,
                "country": country_hint, "country_code": cc,
                "keywords": kw,
            }

        if callback:
            callback(f"🤖 AI analyzing company name: '{raw_name}'...")

        system = (
            "Given a company name (possibly misspelled or non-Latin) and country hint, output JSON:\n"
            '{"corrected_name":"...","company_name_english":"...","country":"...","country_code":"XX",'
            '"language_code":"en",'
            '"keywords":{"contact_page":["Contact","LocalWord"],"address":["Address","LocalWord"]}}\n'
            "Rules: correct spelling, translate to English (keep brand names as-is), "
            "identify country + ISO code, provide local translations of Contact/Address."
        )
        try:
            resp = await self.client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Company: '{raw_name}'. Country: {country_hint or 'Unknown'}"},
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
                                   model=None, callback=None):
        model = model or DEFAULT_MODEL

        # Phase 0 — fix name + translate
        ai_meta = await self._fix_name_with_ai(buyer_name, country, callback)
        corrected = ai_meta.get("corrected_name", buyer_name)
        english_name = ai_meta.get("company_name_english", "")
        country_english = ai_meta.get("country", country)
        country_code = ai_meta.get("country_code", "")

        # NOTE: these are call-local, not stored on self — safe for concurrent use.
        contact_kw = ai_meta.get("keywords", {}).get("contact_page") or DEFAULT_CONTACT_KW
        address_kw = ai_meta.get("keywords", {}).get("address") or DEFAULT_ADDRESS_KW

        enhanced_prompt = system_prompt + (
            f"\n\nCONTEXT:\n"
            f"- Corrected name: '{corrected}' | English: '{english_name}'\n"
            f"- Country: '{country_english}' ({country_code})\n"
            f"- Use these for company_name_english, country_english, country_code in output.\n"
            f"- Contact keywords: {contact_kw}\n"
            f"- BE EFFICIENT: stop searching once you have email+phone+address.\n"
        )

        messages = [
            {"role": "system", "content": enhanced_prompt},
            {"role": "user", "content": (
                f"Find contact info for '{corrected}' "
                f"(original: '{buyer_name}') in '{country}'."
            )},
        ]
        if callback:
            callback(f"🚀 Starting search for: {corrected}")

        # Track accumulated contact data for early-exit decisions
        found_emails, found_phones = set(), set()

        for turn in range(MAX_TURNS):
            try:
                response = await self.client.chat.completions.create(
                    model=model, messages=messages, tools=TOOLS, tool_choice="auto",
                )
                msg = response.choices[0].message

                if not msg.tool_calls:
                    return (self._clean_json(msg.content), turn) if msg.content else (None, turn)

                messages.append(msg)

                # ── Execute tool calls concurrently ──
                async def _exec_tool(tc):
                    args = json.loads(tc.function.arguments)
                    if tc.function.name == "web_search":
                        q = args.get("query", "")
                        if callback: callback(f"🔎 Turn {turn+1}: Searching '{q}'...")
                        return tc.id, await self._perform_search(q, contact_kw, address_kw, callback=callback)
                    elif tc.function.name == "fetch_page":
                        u = args.get("url", "")
                        if callback: callback(f"🌐 Turn {turn+1}: Scraping '{u}'...")
                        return tc.id, await self._fetch_page_with_retry(u, address_kw)
                    return tc.id, {"error": "Unknown tool"}

                results = await asyncio.gather(*(_exec_tool(tc) for tc in msg.tool_calls))

                for tc_id, result in results:
                    # Track found data for early-exit
                    if isinstance(result, dict):
                        found_emails.update(result.get("emails_found", result.get("all_emails", [])))
                        found_phones.update(result.get("phones_found", result.get("all_phones", [])))
                    elif isinstance(result, list) and result:
                        r0 = result[0] if isinstance(result[0], dict) else {}
                        found_emails.update(r0.get("all_emails", []))
                        found_phones.update(r0.get("all_phones", []))

                    messages.append({"role": "tool", "tool_call_id": tc_id,
                                     "content": json.dumps(result, ensure_ascii=False)})

                # ── Early exit: nudge AI to finalize if we have enough ──
                if found_emails and found_phones and turn >= 2:
                    if callback: callback(f"✅ Turn {turn+1}: Found {len(found_emails)} emails + {len(found_phones)} phones — nudging AI to finalize.")
                    messages.append({"role": "user", "content":
                        "You have found emails and phones. Return the JSON now with all data collected. "
                        f"Set company_name_english='{english_name}', "
                        f"country_english='{country_english}', country_code='{country_code}'."})

            except Exception as e:
                if callback: callback(f"⚠️ API Error: {e}")
                return None, turn

        # Max turns — force final answer
        if callback:
            callback("⏱️ Max turns reached. Forcing final answer...")
        messages.append({"role": "user", "content":
            "STOP. Return JSON now with whatever data you found. Missing fields → null/[]. "
            f"company_name_english='{english_name}', "
            f"country_english='{country_english}', country_code='{country_code}'."})
        try:
            final = await self.client.chat.completions.create(model=model, messages=messages)
            return self._clean_json(final.choices[0].message.content), MAX_TURNS
        except Exception:
            return None, MAX_TURNS

    # ── Web Search (Multi-Strategy, with retry) ──────────────────────────
    async def _run_ddgs_search(self, query, max_results=8):
        if ASYNC_SEARCH:
            async with AsyncDDGS() as ddgs:
                return [r async for r in ddgs.text(query, max_results=max_results)]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: list(DDGS(timeout=30).text(query, max_results=max_results)))

    async def _perform_search(self, query, contact_kw, address_kw, callback=None, max_retries=2):
        # Retry with backoff — DDGS is rate-limit prone.
        results, last_err = None, None
        for attempt in range(max_retries + 1):
            try:
                results = await self._run_ddgs_search(query)
                break
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    if callback: callback(f"   ⚠️ Search attempt {attempt+1} failed ({e}), retrying...")
                    await asyncio.sleep(0.5 * (attempt + 1))
        if results is None:
            return [{"error": f"Search failed after retries: {last_err}. Try a different query."}]

        try:
            if not results:
                return [{"error": "No results. Try a different query."}]

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

            # Only return top 6 search result snippets to save tokens
            output = output[:6]

            # ── Auto-fetch: website homepage + contact page in parallel ──
            page_preview, fetched = "", set()
            if website:
                base_url = _extract_base_url(website)

                # Fire homepage + contact page concurrently
                fetch_tasks = [("homepage", website)]
                if contact_page and contact_page != website:
                    fetch_tasks.append(("contact", contact_page))

                if callback: callback(f"   📄 Auto-fetching {len(fetch_tasks)} page(s) in parallel...")
                fetch_results = await asyncio.gather(
                    *(self._fetch_page_with_retry(url, address_kw) for _, url in fetch_tasks)
                )

                for (label, url), page in zip(fetch_tasks, fetch_results):
                    all_emails.extend(page.get("emails_found", []))
                    all_phones.extend(page.get("phones_found", []))
                    pt = page.get("page_text_preview", "")
                    if label == "homepage":
                        page_preview = pt
                    elif pt:
                        page_preview += f"\n\n--- CONTACT PAGE ---\n{pt}"
                    fetched.add(url)

                # ── Auto-probe: common contact paths, concurrently ──
                if not contact_page:
                    candidate_paths = [p for p in CONTACT_PATHS[:8]
                                        if (base_url + p) not in fetched]
                    if candidate_paths:
                        if callback: callback(f"   🔍 Probing {len(candidate_paths)} contact paths (concurrently)...")
                        found = await self._probe_paths_concurrently(base_url, candidate_paths)
                        if found:
                            probe_url = found
                            if callback: callback(f"   ✅ Found contact page: {probe_url}")
                            contact_page = probe_url
                            cp_data = await self._fetch_page_with_retry(probe_url, address_kw)
                            all_emails.extend(cp_data.get("emails_found", []))
                            all_phones.extend(cp_data.get("phones_found", []))
                            cp_text = cp_data.get("page_text_preview", "")
                            if cp_text:
                                page_preview += f"\n\n--- CONTACT PAGE ---\n{cp_text}"
                            fetched.add(probe_url)
            elif best_dir_url:
                if callback: callback(f"   📄 No official site, fetching directory: {best_dir_url}")
                page = await self._fetch_page_with_retry(best_dir_url, address_kw)
                all_emails.extend(page.get("emails_found", []))
                all_phones.extend(page.get("phones_found", []))
                page_preview = page.get("page_text_preview", "")

            filtered_emails = _filter_emails(all_emails)[:15]
            cleaned_phones = _clean_phones(all_phones)[:10]

            output.insert(0, {
                "CONTACT_INFO_FOUND": bool(filtered_emails or cleaned_phones or page_preview),
                "website": website, "contact_page": contact_page,
                "all_emails": filtered_emails,
                "all_phones": cleaned_phones,
                "page_preview": page_preview[:2000],
                "no_official_site": website is None,
                "instruction": (
                    "USE these emails/phones in your JSON — they are VERIFIED from the website. "
                    "Check page_preview for address (street, postal code, city). "
                    "If no_official_site, try searching '<company> official website'."
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
    async def _fetch_page_with_retry(self, url, address_kw, max_retries=1):
        """Fetch a page with retry logic on failure."""
        last_error = None
        for attempt in range(max_retries + 1):
            result = await self._fetch_page(url, address_kw)
            if "error" not in result:
                return result
            last_error = result.get("error", "")
            if attempt < max_retries:
                await asyncio.sleep(0.5)
        return {"error": last_error, "emails_found": [], "phones_found": [], "page_text_preview": ""}

    # ── Fetch Page ───────────────────────────────────────────────────────
    async def _fetch_page(self, url, address_kw):
        async with _FETCH_SEMAPHORE:
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

                final_text = text[:1800]
                addr_text = " | ".join(address_parts[:5])
                if addr_text:
                    final_text += f"\n\nAddress Info: {addr_text}"

                emails = _filter_emails(emails)

                return {
                    "url": url,
                    "emails_found": list(set(emails))[:15],
                    "phones_found": _clean_phones(phones_raw)[:10],
                    "page_text_preview": final_text,
                    "address_hints": address_parts[:5],
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
