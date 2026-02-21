"""
DeepSeek Smart Contact Finder (AntiGravity Edition v2.1 - FIXED)
===============================================================

AI-powered company contact search with web scraping & tool-calling.

Fixed issues:
- Added TypeVar T (no NameError)
- Removed invalid TypedDict constructors (no TypeError)
- Fixed verified_phones handling (no re-extraction)
- Retry now works for 429/5xx (raises to trigger backoff)
- Safer event loop usage (get_running_loop)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    FrozenSet,
    List,
    Optional,
    Pattern,
    Set,
    Tuple,
    TypedDict,
    Union,
    TypeVar,
)
from urllib.parse import urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from openai import AsyncOpenAI

# ──────────────────────────────────────────────────────────────────────────────
# Type Definitions
# ──────────────────────────────────────────────────────────────────────────────

T = TypeVar("T")


class ConfidenceLevel(str, Enum):
    """Confidence levels for extracted contact data."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceType(str, Enum):
    """Types of pages that can be sources of contact information."""
    HOMEPAGE = "homepage"
    CONTACT = "contact"
    LEGAL = "legal"
    ABOUT = "about"
    IMPRINT = "imprint"
    OTHER = "other"


class SourceEntry(TypedDict):
    """A source entry for contact information."""
    type: str
    url: str
    emails_found: List[str]
    phones_found: List[str]
    address_snippet: Optional[str]


class ContactResult(TypedDict):
    """The final result structure for company contact data."""
    company_name: Optional[str]
    country: Optional[str]
    website: Optional[str]
    contact_page: Optional[str]
    emails: List[str]
    phones: List[str]
    address: Optional[str]
    sources: List[SourceEntry]
    confidence: str
    notes: Optional[str]


class AIMetaData(TypedDict):
    """Metadata returned from AI name correction."""
    corrected_name: str
    country: str
    language_code: str
    keywords: Dict[str, List[str]]


class PageFetchResult(TypedDict):
    """Result from fetching a web page."""
    url: str
    emails_found: List[str]
    phones_found: List[str]
    page_text_preview: str
    address_candidates: List[str]
    fetch_time_ms: Optional[int]
    error: Optional[str]


class SearchResultItem(TypedDict):
    """A single search result item."""
    title: str
    snippet: str
    url: str


class CacheEntry(TypedDict):
    """An entry in the page cache."""
    data: PageFetchResult
    timestamp: float
    ttl: float


ProgressCallback = Callable[[str], None]


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ContactFinderConfig:
    api_key: Optional[str] = None
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_turns: int = 12
    timeout: float = 25.0
    max_retries: int = 3
    retry_delay: float = 1.0
    cache_ttl: float = 3600.0  # 1 hour
    max_concurrent: int = 5
    max_emails: int = 10
    max_phones: int = 10
    max_preview_length: int = 3000
    log_level: int = logging.INFO
    user_agent: Optional[str] = None

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        if self.timeout < 1:
            raise ValueError("timeout must be at least 1 second")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.cache_ttl < 0:
            raise ValueError("cache_ttl must be non-negative")
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

SKIP_DOMAINS: FrozenSet[str] = frozenset([
    "dnb.com", "yellowpages.com", "yelp.com", "bloomberg.com",
    "zoominfo.com", "crunchbase.com", "glassdoor.com", "indeed.com",
    "opencorporates.com", "kompass.com", "b2bhint.com", "volza.com",
    "panjiva.com", "importgenius.com", "zauba.com", "trademap.org",
    "europages.com", "thomasnet.com", "manta.com", "hoovers.com",
    "spoke.com", "corporationwiki.com", "buzzfile.com", "owler.com",
    "datanyze.com", "apollo.io", "sbdb.io", "craft.co",
    "alibaba.com", "made-in-china.com", "globalsources.com",
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "youtube.com", "tiktok.com", "pinterest.com", "reddit.com",
    "scribd.com", "docplayer.net", "slideshare.net",
    "monster.com", "careerbuilder.com", "ziprecruiter.com",
])

JUNK_EMAIL_PATTERNS: List[Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"example@", r"test@", r"sample@", r"your@", r"domain@",
        r"email@", r"user@", r"name@", r"\.png@", r"\.jpg@", r"\.gif@",
        r"noreply@", r"no-reply@", r"donotreply@", r"donotreply@",
        r"@wix\.com", r"@sentry\.", r"@schema\.", r"@wordpress\.",
        r"privacy@", r"legal@", r"abuse@", r"webmaster@localhost",
        r"@example\.", r"@test\.", r"@sample\.", r"@dummy\.",
    ]
]

CONTACT_PAGE_PATHS: FrozenSet[str] = frozenset([
    "/contact", "/contact-us", "/contacts", "/en/contact", "/en/contact-us",
    "/iletisim", "/tr/iletisim", "/kontakt", "/de/kontakt",
    "/contacto", "/es/contacto", "/about/contact", "/about-us/contact",
    "/impressum", "/legal", "/privacy", "/reach-us", "/get-in-touch",
    "/write-to-us", "/customer-service", "/support", "/help/contact",
])

ADDRESS_KEYWORDS: FrozenSet[str] = frozenset([
    "address", "location", "headquarters", "head office", "hq", "office",
    "registered office", "registered address", "postal address",
    "street", "road", "avenue", "boulevard", "place", "square",
    "building", "floor", "suite", "unit", "box", "po box",
    "adres", "adresse", "ubicación", "dirección", "indirizzo", "endereço",
    "kontakt", "impressum", "iletişim", "unternehmen",
])

ADDRESS_MARKER_PATTERNS: List[Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"address\s*:", r"location\s*:", r"headquarters\s*:",
        r"registered\s+office\s*:", r"postal\s+address\s*:",
        r"our\s+office\s*:", r"visit\s+us\s*:", r"find\s+us\s*:",
        r"mailing\s+address\s*:", r"street\s+address\s*:",
    ]
]


# ──────────────────────────────────────────────────────────────────────────────
# System Prompt
# ──────────────────────────────────────────────────────────────────────────────

ANTIGRAVITY_SYSTEM_PROMPT_V2 = """
You are AntiGravity, a forensic company-contact researcher.

MISSION
Find and return VERIFIED company contact details:
- official website (primary domain)
- best contact page URL
- business emails (role-based preferred)
- phone numbers
- postal address (as complete as possible)

TOOLS (ONLY)
- web_search(query): returns search results AND a summary object (index 0) that may include candidate website/contact_page plus snippet hints and a preview.
- fetch_page(url): fetches a page and returns emails_found, phones_found, and page_text_preview.

ABSOLUTE RULES (NO EXCEPTIONS)
1) NEVER ask the user for more information. No questions. No requests for company name or country.
2) NO HALLUCINATIONS: Do not invent emails, phones, addresses, websites, or claims.
3) VERIFIED-ONLY OUTPUT:
   - You may output an email or phone ONLY if it appears in fetch_page output:
     (emails_found / phones_found) OR it is clearly visible in page_text_preview of a fetched page.
   - Emails/phones in web_search snippets are HINTS ONLY and must NOT be output unless verified by fetch_page.
4) OFFICIAL SOURCES PRIORITY:
   - Prefer the company's own domain and its pages (Contact, About, Legal, Imprint, Footer).
   - Directory/lead-gen/social sites are allowed ONLY to discover the official domain. Never use them as final sources.
5) DATA QUALITY:
   - Prefer role emails: info@, sales@, export@, contact@, support@, inquiries@.
   - Exclude junk/placeholder: noreply/no-reply, example/test/sample, privacy@, legal@, image-file artifacts.
6) AMBIGUITY HANDLING:
   - If multiple companies match, choose the one most consistent with company name + country hint.
   - If still uncertain, choose the most likely official site but set confidence="low" and explain why in notes.

MANDATORY WORKFLOW
Step 0) Input validation
- If company name is missing/empty: return the output JSON immediately with nulls/[] and confidence="low" and notes="Missing company name input."
- Do NOT ask for missing input.

Step 1) Discover the official website
- Run web_search with 2–4 targeted queries, e.g.:
  a) "<company> official website <country>"
  b) "<company> contact <country>"
  c) "<company> address <country>"
  d) "<company> email phone <country>"
- Use the web_search summary object (index 0) as the primary guide for candidate website/contact_page.
- Compare other results only to confirm the official domain (avoid directories/social).

Step 2) Fetch and verify
- ALWAYS fetch_page(website) once you have a candidate official website.
- ALSO fetch_page(contact_page) if available.
- If contact_page is unknown, attempt discovery on the SAME domain by:
  - fetching homepage and using its content to locate contact/legal/imprint/about links
  - trying common paths: /contact, /contact-us, /about, /impressum, /legal, /privacy, /support
- Do not fetch random external domains unless the official site is still unknown.

Step 3) Extract, rank, and dedupe
- Collect VERIFIED emails/phones from fetched pages only.
- Rank emails: role-based > general mailbox > named emails.
- Keep the best 1–3 emails; include up to 10 max if asked, otherwise keep it lean.
- Dedupe all emails/phones.

Step 4) Address extraction (from fetched pages only)
- Extract address primarily from:
  - <address> tag
  - footer blocks
  - "Impressum / Legal / Registered Office" sections
  - JSON-LD schema.org Organization/LocalBusiness address fields
- If you only find partial address, output the best snippet and reduce confidence.

Step 5) Evidence and final audit (MANDATORY)
- Build "sources" from every fetched URL that contributed data.
- Every email/phone in the final output MUST appear in at least one source entry (emails_found/phones_found OR clearly visible in preview).
- If you cannot verify it, DO NOT output it.
- If nothing verified: emails=[], phones=[], address=null, confidence="low".

OUTPUT FORMAT (STRICT JSON ONLY)
Return exactly ONE JSON object with the following keys (no extra keys, no markdown, no explanation):

{
  "company_name": string|null,
  "country": string|null,
  "website": string|null,
  "contact_page": string|null,
  "emails": [string],
  "phones": [string],
  "address": string|null,
  "sources": [
    {
      "type": "homepage|contact|legal|about|imprint|other",
      "url": string,
      "emails_found": [string],
      "phones_found": [string],
      "address_snippet": string|null
    }
  ],
  "confidence": "high|medium|low",
  "notes": string|null
}

Return JSON ONLY. No markdown. No extra text.
""".strip()


# ──────────────────────────────────────────────────────────────────────────────
# Utility Functions
# ──────────────────────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ContactFinder")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_random_user_agent() -> str:
    try:
        from fake_useragent import UserAgent
        return UserAgent().random
    except ImportError:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def normalize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme or "https"
        netloc = (parsed.netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if not netloc:
            return None
        return urlunparse((scheme, netloc, parsed.path or "", "", "", ""))
    except Exception:
        return None


def homepage_url(url: Optional[str]) -> Optional[str]:
    """Convert any URL to its homepage root (scheme://netloc/)."""
    n = normalize_url(url)
    if not n:
        return None
    p = urlparse(n)
    return urlunparse((p.scheme, p.netloc, "/", "", "", ""))


def get_root_domain(url: Optional[str]) -> str:
    n = normalize_url(url)
    if not n:
        return ""
    try:
        return urlparse(n).netloc.lower()
    except Exception:
        return ""


def tokenize_for_scoring(text: Optional[str], max_tokens: int = 8) -> List[str]:
    if not text:
        return []
    tokens = re.findall(r"[a-z0-9]{3,}", text.lower())
    return tokens[:max_tokens]


def score_search_result(
    url: str,
    title: str,
    snippet: str,
    name_tokens: List[str],
    country_hint: Optional[str] = None
) -> int:
    url_lower = (url or "").lower()
    if any(domain in url_lower for domain in SKIP_DOMAINS):
        return -999

    score = 0
    domain = get_root_domain(url)
    title_lower = (title or "").lower()
    snippet_lower = (snippet or "").lower()
    country_lower = (country_hint or "").lower()

    for token in name_tokens:
        if token in domain:
            score += 9
        if token in title_lower:
            score += 4
        if token in snippet_lower:
            score += 2

    if country_lower:
        if country_lower in title_lower:
            score += 3
        if country_lower in snippet_lower:
            score += 2

    if any(ext in url_lower for ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]):
        score -= 15

    if "official" in title_lower or "official" in snippet_lower:
        score += 3

    path_segments = url_lower.count("/")
    if path_segments > 4:
        score -= (path_segments - 4)

    return score


# ──────────────────────────────────────────────────────────────────────────────
# Email and Phone Extraction
# ──────────────────────────────────────────────────────────────────────────────

EMAIL_PATTERN: Pattern[str] = re.compile(
    r"(?:[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*|"
    r'"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|'
    r'\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@'
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?",
    re.IGNORECASE
)

PHONE_PATTERNS: List[Pattern[str]] = [
    re.compile(
        r"\+([1-9]\d{0,2})[\s.\-()]*(\d{1,4})[\s.\-()]*(\d{1,4})"
        r"[\s.\-()]*(\d{1,4})[\s.\-()]*(\d{0,4})[\s.\-()]*(\d{0,4})",
        re.VERBOSE
    ),
    re.compile(r"\+\d{2}[\s]\d(?:[\s]\d{2}){4}"),
    re.compile(r"\+?1[\s.\-()]?\(?\d{3}\)?[\s.\-()]?\d{3}[\s.\-()]?\d{4}"),
    re.compile(r"\+44[\s.\-()]?(?:0)?\d{2,4}[\s.\-()]?\d{3,4}[\s.\-()]?\d{3,4}"),
    re.compile(r"\+90[\s.\-()]?\d{3}[\s.\-()]?\d{3}[\s.\-()]?\d{2}[\s.\-()]?\d{2}"),
    re.compile(
        r"(?:tel|phone|fax|telephone|mobile|cell|call)[:\s]+"
        r"([\+]?[\d\s\-\.\(\)/]{7,})",
        re.IGNORECASE
    ),
    re.compile(r"tel:([\+]?[\d\s\-\.\(\)]{7,})"),
]


def is_junk_email(email: str) -> bool:
    email_lower = email.lower()
    return any(p.search(email_lower) for p in JUNK_EMAIL_PATTERNS)


def filter_emails(emails: Optional[List[str]], max_count: int = 10) -> List[str]:
    if not emails:
        return []

    seen: Set[str] = set()
    role_emails: List[str] = []
    other_emails: List[str] = []

    role_priority = [
        "info@", "sales@", "export@", "contact@", "support@",
        "inquiries@", "hello@", "office@", "admin@", "mail@",
    ]

    for email in emails:
        email = (email or "").strip()
        if not email or "@" not in email:
            continue
        if not EMAIL_PATTERN.match(email):
            continue
        if is_junk_email(email):
            continue
        el = email.lower()
        if el in seen:
            continue
        seen.add(el)

        if any(role in el for role in role_priority):
            role_emails.append(email)
        else:
            other_emails.append(email)

    def role_sort_key(e: str) -> int:
        el = e.lower()
        for i, role in enumerate(role_priority):
            if role in el:
                return i
        return len(role_priority)

    role_emails.sort(key=role_sort_key)
    return (role_emails + other_emails)[:max_count]


def clean_phone_number(phone: str) -> Optional[str]:
    if not phone:
        return None

    phone = re.sub(r"^(tel:|phone:|fax:|mobile:)", "", phone, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"[^\d+]", "", phone)
    cleaned = re.sub(r"^\++", "+", cleaned)
    if cleaned.startswith("+"):
        cleaned = "+" + cleaned[1:].replace("+", "")
    else:
        cleaned = cleaned.replace("+", "")

    digits = re.sub(r"\D", "", cleaned)
    if len(digits) >= 10:
        return cleaned
    if len(digits) >= 8 and not cleaned.startswith("+"):
        return cleaned
    return None


def extract_phones(text: str, max_count: int = 10) -> List[str]:
    if not text:
        return []

    phones_raw: List[str] = []

    for pattern in PHONE_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            if isinstance(match, tuple):
                # For the first pattern: country code is first group
                # Reconstruct as +<country><rest...>
                parts = [str(g) for g in match if g]
                if parts:
                    phone = "+" + "".join(parts)
                else:
                    phone = ""
            else:
                phone = str(match)

            if phone:
                phones_raw.append(phone)

    standalone = re.findall(r"\+\d{1,3}[\d\s\-\.\(\)]{7,}", text)
    phones_raw.extend(standalone)

    seen: Set[str] = set()
    result: List[str] = []
    for phone in phones_raw:
        cleaned = clean_phone_number(phone)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)

    return result[:max_count]


def extract_emails(text: str, max_count: int = 10) -> List[str]:
    if not text:
        return []
    emails = EMAIL_PATTERN.findall(text)
    return filter_emails(emails, max_count)


# ──────────────────────────────────────────────────────────────────────────────
# Address Extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_address_from_text(text: str, keywords: FrozenSet[str] = ADDRESS_KEYWORDS) -> List[str]:
    if not text:
        return []

    candidates: List[str] = []
    tl = text.lower()

    for keyword in keywords:
        idx = tl.find(keyword)
        if idx != -1:
            start = max(0, idx - 80)
            end = min(len(text), idx + 250)
            snippet = text[start:end].strip()
            if 20 < len(snippet) < 400:
                candidates.append(snippet)

    for pattern in ADDRESS_MARKER_PATTERNS:
        for match in pattern.finditer(text):
            start = match.start()
            end = min(len(text), start + 300)
            snippet = text[start:end].strip()
            if 20 < len(snippet) < 400:
                candidates.append(snippet)

    seen: Set[str] = set()
    out: List[str] = []
    for c in candidates:
        cl = c.lower()
        if cl not in seen:
            seen.add(cl)
            out.append(c)
    return out


def extract_address_from_html(soup: BeautifulSoup) -> List[str]:
    candidates: List[str] = []

    for addr_tag in soup.find_all("address"):
        text = re.sub(r"\s+", " ", addr_tag.get_text(" ", strip=True))
        if 15 < len(text) < 400:
            candidates.append(text)

    for attr in ["class", "id"]:
        for elem in soup.find_all(attrs={attr: re.compile(r"address|location|contact-info", re.I)}):
            text = re.sub(r"\s+", " ", elem.get_text(" ", strip=True))
            if 20 < len(text) < 500:
                candidates.append(text)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text(strip=True) or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    item_type = " ".join(item_type)
                if any(t in str(item_type).lower() for t in ["organization", "business", "company", "localbusiness"]):
                    addr = item.get("address", {})
                    if isinstance(addr, dict):
                        fields = [
                            addr.get("streetAddress"),
                            addr.get("addressLocality"),
                            addr.get("addressRegion"),
                            addr.get("postalCode"),
                            addr.get("addressCountry"),
                        ]
                        parts = [str(f).strip() for f in fields if f]
                        if parts:
                            address = ", ".join(parts)
                            if 15 < len(address) < 400:
                                candidates.append(address)
        except Exception:
            pass

    for footer in soup.find_all("footer"):
        text = re.sub(r"\s+", " ", footer.get_text(" ", strip=True))
        if 20 < len(text) < 600:
            candidates.append(text)

    return candidates


# ──────────────────────────────────────────────────────────────────────────────
# Caching
# ──────────────────────────────────────────────────────────────────────────────

class PageCache:
    def __init__(self, ttl: float = 3600.0, max_size: int = 100):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[PageFetchResult]:
        async with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if time.time() - entry["timestamp"] > entry["ttl"]:
                del self._cache[key]
                return None
            return entry["data"]

    async def set(self, key: str, data: PageFetchResult, ttl: Optional[float] = None) -> None:
        async with self._lock:
            if len(self._cache) >= self._max_size:
                await self._cleanup_expired()
                if len(self._cache) >= self._max_size:
                    oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["timestamp"])
                    del self._cache[oldest_key]

            self._cache[key] = {"data": data, "timestamp": time.time(), "ttl": ttl or self._ttl}

    async def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._cache.items() if now - v["timestamp"] > v["ttl"]]
        for key in expired:
            del self._cache[key]

    def clear(self) -> None:
        self._cache.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Retry Decorator
# ──────────────────────────────────────────────────────────────────────────────

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: Tuple[type, ...] = (Exception,)
):
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception: Optional[BaseException] = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        await asyncio.sleep(delay)
            assert last_exception is not None
            raise last_exception
        return wrapper
    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# Main Client Class
# ──────────────────────────────────────────────────────────────────────────────

class DeepSeekContactFinder:
    def __init__(self, config: Optional[ContactFinderConfig] = None):
        self.config = config or ContactFinderConfig()

        api_key = self.config.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("Missing DEEPSEEK_API_KEY (env) or config.api_key")

        self._client = AsyncOpenAI(api_key=api_key, base_url=self.config.base_url)
        self._http: Optional[httpx.AsyncClient] = None

        self._cache = PageCache(ttl=self.config.cache_ttl)
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)

        self._logger = setup_logging(self.config.log_level)
        self._stats = {"searches": 0, "pages_fetched": 0, "cache_hits": 0, "cache_misses": 0, "errors": 0}

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            ua = self.config.user_agent or get_random_user_agent()
            self._http = httpx.AsyncClient(
                timeout=self.config.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._cache.clear()
        self._logger.info("Contact finder closed. Stats: %s", self._stats)

    async def __aenter__(self) -> "DeepSeekContactFinder":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @property
    def stats(self) -> Dict[str, int]:
        return self._stats.copy()

    async def _correct_company_name(
        self,
        raw_name: str,
        country_hint: Optional[str],
        callback: Optional[ProgressCallback] = None
    ) -> AIMetaData:
        if callback:
            callback(f"🤖 AI analyzing company name: '{raw_name}'...")

        system_prompt = """You are a data expert specializing in company name validation and correction.

Given a company name (possibly misspelled or incomplete) and a country hint:
1. Correct the company name to its official form
2. Identify the country and primary language
3. Provide translations for 'Contact' and 'Address' in that language

Output JSON ONLY with this structure:
{
  "corrected_name": "Official Company Name",
  "country": "Country Name",
  "language_code": "en",
  "keywords": {
    "contact_page": ["Contact", "İletişim", "Kontakt"],
    "address": ["Address", "Adres", "Adresse"]
  }
}"""

        try:
            response = await self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Company: '{raw_name}'. Country hint: {country_hint or 'Unknown'}"},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
            if callback:
                callback(f"✅ Corrected name: '{data.get('corrected_name', raw_name)}'")
            return data
        except Exception as e:
            self._logger.warning("AI name correction failed: %s", e)
            return {
                "corrected_name": raw_name,
                "country": country_hint or "",
                "language_code": "en",
                "keywords": {
                    "contact_page": ["Contact", "İletişim", "Kontakt"],
                    "address": ["Address", "Adres", "Adresse"],
                },
            }

    def _create_empty_result(self, company_name: Optional[str], country: Optional[str], notes: str) -> ContactResult:
        return {
            "company_name": company_name,
            "country": country,
            "website": None,
            "contact_page": None,
            "emails": [],
            "phones": [],
            "address": None,
            "sources": [],
            "confidence": ConfidenceLevel.LOW.value,
            "notes": notes,
        }

    async def extract_company_data(
        self,
        buyer_name: str = "",
        country: str = "",
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        callback: Optional[ProgressCallback] = None,
    ) -> Tuple[ContactResult, int]:
        system_prompt = (system_prompt or ANTIGRAVITY_SYSTEM_PROMPT_V2).strip()
        buyer_name = (buyer_name or "").strip()
        country = (country or "").strip()
        model = model or self.config.model

        if not buyer_name:
            return self._create_empty_result(None, country, "Missing company name input."), 0

        ai_meta = await self._correct_company_name(buyer_name, country, callback)
        corrected_name = (ai_meta.get("corrected_name") or buyer_name).strip() or buyer_name

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Find contact info for Buyer: '{corrected_name}' "
                f"(original name: '{buyer_name}') located in '{country}'."
            )},
        ]

        if callback:
            callback(f"🚀 Starting search for: {corrected_name}")

        tools = [
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

        for turn in range(self.config.max_turns):
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )

                msg = response.choices[0].message

                if not getattr(msg, "tool_calls", None):
                    final_response = await self._client.chat.completions.create(
                        model=model,
                        messages=messages + [{"role": "assistant", "content": msg.content or ""}],
                        tool_choice="none",
                        response_format={"type": "json_object"},
                    )
                    data = json.loads(final_response.choices[0].message.content or "{}")
                    return data, turn + 1  # type: ignore[return-value]

                messages.append(msg)

                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")

                    if tc.function.name == "web_search":
                        query = (args.get("query") or "").strip()
                        if callback:
                            callback(f"🔎 Turn {turn + 1}: Searching '{query}'...")
                        result = await self._perform_search(query, company_hint=corrected_name, country_hint=country)

                    elif tc.function.name == "fetch_page":
                        url = (args.get("url") or "").strip()
                        if callback:
                            callback(f"🌐 Turn {turn + 1}: Scraping '{url}'...")
                        result = await self._fetch_page(url)

                    else:
                        result = {"error": f"Unknown tool: {tc.function.name}"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

            except Exception as e:
                self._logger.error("API error on turn %d: %s", turn, e)
                self._stats["errors"] += 1
                if callback:
                    callback(f"⚠️ API Error: {e}")
                return self._create_empty_result(corrected_name, country, f"API Error: {e}"), turn + 1

        if callback:
            callback("⏱️ Max turns reached. Forcing final answer...")

        messages.append({
            "role": "user",
            "content": (
                "STOP SEARCHING. Return the JSON object immediately with whatever data you found. "
                "If fields are missing, use null or empty arrays."
            ),
        })

        try:
            final_response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                tool_choice="none",
                response_format={"type": "json_object"},
            )
            data = json.loads(final_response.choices[0].message.content or "{}")
            return data, self.config.max_turns  # type: ignore[return-value]
        except Exception as e:
            return self._create_empty_result(corrected_name, country, f"Final JSON Error: {e}"), self.config.max_turns

    # ── Web Search ────────────────────────────────────────────────────────

    async def _perform_search(self, query: str, company_hint: str = "", country_hint: str = "") -> List[Dict[str, Any]]:
        self._stats["searches"] += 1

        try:
            if not query:
                return [{"error": "Empty query."}]

            results = await self._search_duckduckgo(query, max_results=10)
            if not results:
                return [{"error": "No search results found."}]

            name_tokens = tokenize_for_scoring(company_hint or query)

            candidates: List[Tuple[int, str, str, str]] = []
            output: List[SearchResultItem] = []
            snippet_emails: List[str] = []
            snippet_phones: List[str] = []

            for r in results:
                title = r.get("title", "") or ""
                snippet = r.get("body", r.get("snippet", "")) or ""
                url = r.get("href", r.get("link", "")) or ""
                if not url:
                    continue

                url_n = normalize_url(url)
                if not url_n:
                    continue

                score = score_search_result(url_n, title, snippet, name_tokens, country_hint)
                if score > -999:
                    candidates.append((score, url_n, title, snippet))

                output.append({"title": title, "snippet": snippet, "url": url_n})

                # hints only
                snippet_emails.extend(extract_emails(snippet, self.config.max_emails))
                snippet_phones.extend(extract_phones(snippet, self.config.max_phones))

            candidates.sort(reverse=True, key=lambda x: x[0])

            website = homepage_url(candidates[0][1]) if candidates and candidates[0][0] > -50 else None

            contact_page = None
            if website:
                website_domain = get_root_domain(website)
                for score, url_n, title, snippet in candidates:
                    if get_root_domain(url_n) == website_domain:
                        ul = url_n.lower()
                        if any(k in ul for k in ["contact", "iletisim", "kontakt", "contacto", "impressum", "legal", "about"]):
                            contact_page = url_n
                            break

            targets = [u for u in [contact_page, website] if u]
            verified_emails: List[str] = []
            verified_phones: List[str] = []
            page_preview = ""
            fetched_sources: List[str] = []

            if targets:
                fetch_results = await asyncio.gather(*[self._fetch_page(t) for t in targets], return_exceptions=True)
                for fr in fetch_results:
                    if isinstance(fr, Exception):
                        continue
                    if isinstance(fr, dict) and not fr.get("error"):
                        fetched_sources.append(fr.get("url", ""))
                        verified_emails.extend(fr.get("emails_found", []))
                        verified_phones.extend(fr.get("phones_found", []))
                        if not page_preview:
                            page_preview = fr.get("page_text_preview", "")

            # ✅ Fix: no re-extraction of verified phones. Just normalize + dedupe.
            def _dedupe(items: List[str], max_n: int) -> List[str]:
                seen: Set[str] = set()
                out_list: List[str] = []
                for it in items:
                    if not it:
                        continue
                    if it in seen:
                        continue
                    seen.add(it)
                    out_list.append(it)
                return out_list[:max_n]

            snippet_emails_clean = filter_emails(snippet_emails, self.config.max_emails)
            snippet_phones_clean = _dedupe([p for p in snippet_phones if p], self.config.max_phones)

            verified_emails_clean = filter_emails(verified_emails, self.config.max_emails)
            verified_phones_clean = _dedupe(
                [cp for cp in (clean_phone_number(p) for p in verified_phones) if cp],
                self.config.max_phones
            )

            summary: Dict[str, Any] = {
                "CONTACT_INFO_FOUND": bool(verified_emails_clean or verified_phones_clean or page_preview),
                "website": website,
                "contact_page": contact_page,
                "snippet_emails": snippet_emails_clean,
                "snippet_phones": snippet_phones_clean,
                "verified_emails": verified_emails_clean,
                "verified_phones": verified_phones_clean,
                "page_preview": (page_preview or "")[:self.config.max_preview_length],
                "fetched": fetched_sources,
                "instruction": (
                    "Use verified_emails/verified_phones if present. "
                    "Snippet values are hints only. Address may appear in page_preview."
                ),
            }

            return [summary] + output

        except Exception as e:
            self._logger.error("Search failed: %s", e)
            self._stats["errors"] += 1
            return [{"error": f"Search failed: {e}"}]

    async def _search_duckduckgo(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """DuckDuckGo search with async fallback."""
        try:
            try:
                from duckduckgo_search import AsyncDDGS  # type: ignore
                async with AsyncDDGS() as ddgs:
                    return [r async for r in ddgs.text(query, max_results=max_results)]
            except ImportError:
                try:
                    from ddgs import DDGS  # type: ignore
                except ImportError:
                    from duckduckgo_search import DDGS  # type: ignore

                loop = asyncio.get_running_loop()

                def sync_search() -> List[Dict[str, str]]:
                    with DDGS(timeout=30) as ddgs:  # type: ignore
                        return list(ddgs.text(query, max_results=max_results))  # type: ignore

                return await loop.run_in_executor(None, sync_search)

        except Exception as e:
            self._logger.error("DuckDuckGo search failed: %s", e)
            return []

    # ── Page Fetching ──────────────────────────────────────────────────────

    @retry_with_backoff(max_retries=3, base_delay=1.0, exceptions=(httpx.HTTPError,))
    async def _fetch_page(self, url: str) -> PageFetchResult:
        url_n = normalize_url(url) or ""
        if not url_n:
            return {
                "url": "",
                "emails_found": [],
                "phones_found": [],
                "page_text_preview": "",
                "address_candidates": [],
                "fetch_time_ms": None,
                "error": "Invalid URL",
            }

        cached = await self._cache.get(url_n)
        if cached:
            self._stats["cache_hits"] += 1
            return cached

        self._stats["cache_misses"] += 1
        self._stats["pages_fetched"] += 1

        async with self._semaphore:
            start_time = time.time()
            http = await self._get_http_client()

            try:
                response = await http.get(url_n)
                response.raise_for_status()

                html = response.text or ""
                fetch_time_ms = int((time.time() - start_time) * 1000)

                soup = BeautifulSoup(html, "html.parser")
                base_url = "/".join(url_n.split("/")[:3])

                current_url = url_n
                if not any(x in url_n.lower() for x in ["contact", "iletisim", "kontakt", "contacto", "impressum", "legal", "about"]):
                    soup, html, current_url = await self._find_contact_page(soup, base_url, http, html, url_n)

                emails = set(extract_emails(html, self.config.max_emails))

                for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
                    mailto = (a.get("href", "") or "").replace("mailto:", "").split("?")[0].strip()
                    if mailto and "@" in mailto:
                        emails.add(mailto)

                for cf_email in re.findall(r'data-cfemail="([^"]+)"', html):
                    try:
                        r0 = int(cf_email[:2], 16)
                        decoded = "".join(chr(int(cf_email[i:i+2], 16) ^ r0) for i in range(2, len(cf_email), 2))
                        if "@" in decoded:
                            emails.add(decoded)
                    except Exception:
                        pass

                phones = extract_phones(html, self.config.max_phones)

                for link in soup.find_all("a", href=re.compile(r"^tel:", re.I)):
                    tel = (link.get("href", "") or "").replace("tel:", "").strip()
                    cleaned = clean_phone_number(tel)
                    if cleaned:
                        phones.append(cleaned)

                # dedupe phones preserve order
                seen_p: Set[str] = set()
                phones_out: List[str] = []
                for p in phones:
                    cp = clean_phone_number(p) if isinstance(p, str) else None
                    if cp and cp not in seen_p:
                        seen_p.add(cp)
                        phones_out.append(cp)
                phones_out = phones_out[: self.config.max_phones]

                for el in soup(["script", "style", "noscript", "iframe", "svg"]):
                    el.decompose()

                text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()

                address_candidates = extract_address_from_html(soup)
                address_candidates.extend(extract_address_from_text(text))
                # dedupe addresses
                seen_a: Set[str] = set()
                unique_addresses: List[str] = []
                for addr in address_candidates:
                    al = addr.lower()
                    if al not in seen_a:
                        seen_a.add(al)
                        unique_addresses.append(addr)

                preview = text[: self.config.max_preview_length]
                if unique_addresses:
                    preview += "\n\nPossible Address Info: " + " | ".join(unique_addresses[:3])

                result: PageFetchResult = {
                    "url": current_url,
                    "emails_found": filter_emails(list(emails), self.config.max_emails),
                    "phones_found": phones_out,
                    "page_text_preview": preview,
                    "address_candidates": unique_addresses[:5],
                    "fetch_time_ms": fetch_time_ms,
                    "error": None,
                }

                await self._cache.set(url_n, result)
                return result

            except httpx.HTTPStatusError as e:
                code = e.response.status_code

                # ✅ Retry-able status codes: raise to trigger backoff
                if code in (429, 500, 502, 503, 504):
                    raise

                self._logger.warning("HTTP error fetching %s: HTTP %s", url_n, code)
                result: PageFetchResult = {
                    "url": url_n,
                    "emails_found": [],
                    "phones_found": [],
                    "page_text_preview": "",
                    "address_candidates": [],
                    "fetch_time_ms": None,
                    "error": f"HTTP {code}",
                }
                await self._cache.set(url_n, result)
                return result

            except Exception as e:
                self._logger.error("Error fetching %s: %s", url_n, e)
                result: PageFetchResult = {
                    "url": url_n,
                    "emails_found": [],
                    "phones_found": [],
                    "page_text_preview": "",
                    "address_candidates": [],
                    "fetch_time_ms": None,
                    "error": str(e),
                }
                return result

    async def _find_contact_page(
        self,
        soup: BeautifulSoup,
        base_url: str,
        http: httpx.AsyncClient,
        html: str,
        current_url: str
    ) -> Tuple[BeautifulSoup, str, str]:
        contact_keywords = ["contact", "contact us", "get in touch", "reach us", "iletisim", "kontakt", "contacto", "impressum", "legal", "about"]

        for a in soup.find_all("a", href=True):
            link_text = (a.get_text() or "").strip().lower()
            href = (a.get("href") or "").strip()
            href_lower = href.lower()

            is_contact = any(kw in link_text or kw in href_lower for kw in contact_keywords)
            if not is_contact:
                continue

            if href.startswith("/"):
                follow_url = base_url + href
            elif href.startswith("http"):
                follow_url = href
            else:
                continue

            follow_url_n = normalize_url(follow_url)
            if not follow_url_n:
                continue

            try:
                r = await http.get(follow_url_n)
                if r.status_code == 200 and len(r.text or "") > 300:
                    return BeautifulSoup(r.text, "html.parser"), (r.text or ""), follow_url_n
            except Exception:
                continue

        for path in CONTACT_PAGE_PATHS:
            try:
                test_url = normalize_url(base_url + path)
                if not test_url:
                    continue
                r = await http.get(test_url)
                if r.status_code == 200 and len(r.text or "") > 500:
                    return BeautifulSoup(r.text, "html.parser"), (r.text or ""), test_url
            except Exception:
                continue

        return soup, html, current_url


# ──────────────────────────────────────────────────────────────────────────────
# Backward-compatible wrapper (used by pages/2_Matrix.py)
# ──────────────────────────────────────────────────────────────────────────────

class DeepSeekClient:
    """Backward-compatible wrapper around DeepSeekContactFinder.

    Preserves the old API so existing callers keep working:
        client = DeepSeekClient(api_key=...)
        raw, turns = await client.extract_company_data(system_prompt, name, country, callback=...)
        await client.close()
    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        config = ContactFinderConfig(api_key=api_key)
        self._finder = DeepSeekContactFinder(config)

    async def extract_company_data(
        self,
        system_prompt: str,
        buyer_name: str,
        country: str = "",
        callback: Optional[ProgressCallback] = None,
    ) -> Tuple[Any, int]:
        result, turns = await self._finder.extract_company_data(
            buyer_name=buyer_name,
            country=country,
            system_prompt=system_prompt,
            callback=callback,
        )
        # Return as JSON string (old API returned raw string) + turns
        return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else result, turns

    async def close(self) -> None:
        await self._finder.close()


# ──────────────────────────────────────────────────────────────────────────────
# Convenience Function + CLI
# ──────────────────────────────────────────────────────────────────────────────

async def find_company_contacts(
    company_name: str,
    country: str = "",
    api_key: Optional[str] = None,
    callback: Optional[ProgressCallback] = None,
) -> ContactResult:
    config = ContactFinderConfig(api_key=api_key)
    async with DeepSeekContactFinder(config) as finder:
        result, _ = await finder.extract_company_data(
            buyer_name=company_name,
            country=country,
            callback=callback
        )
        return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DeepSeek Smart Contact Finder (AntiGravity v2.1)")
    parser.add_argument("company", help="Company name to search for")
    parser.add_argument("--country", "-c", default="", help="Country hint")
    parser.add_argument("--api-key", "-k", help="DeepSeek API key (or set DEEPSEEK_API_KEY)")
    parser.add_argument("--output", "-o", help="Output file (JSON)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    def progress_callback(msg: str):
        print(msg)

    async def run():
        result = await find_company_contacts(
            company_name=args.company,
            country=args.country,
            api_key=args.api_key,
            callback=progress_callback if args.verbose else None,
        )
        out = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out)
            print(f"\nResults saved to: {args.output}")
        else:
            print("\n" + out)

    asyncio.run(run())


if __name__ == "__main__":
    main()