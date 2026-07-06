"""
ai_engine.py
─────────────────────────────────────────────────────────────
Antigravity :: AI Engine
Handles all OpenAI (or DeepSeek-compatible) interactions:
  1. Personalised cold email generation
  2. Reply classification (interested / not_interested / follow_up)
  3. Contextual auto-response generation

All prompts are carefully engineered for B2B cold outreach.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger("antigravity.ai_engine")

# ── OpenAI client ─────────────────────────────────────────────
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        kwargs: dict = {"api_key": os.environ["OPENAI_API_KEY"]}
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        _openai_client = OpenAI(**kwargs)
    return _openai_client


MODEL        = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMPERATURE  = 0.75
MAX_TOKENS   = 900

REPLY_CATEGORIES = Literal["interested", "not_interested", "follow_up", "unknown"]


# ── Dataclasses ───────────────────────────────────────────────
@dataclass
class GeneratedEmail:
    subject:    str
    html_body:  str
    plain_body: str


@dataclass
class ClassificationResult:
    category:   REPLY_CATEGORIES
    confidence: float
    reasoning:  str


# ─────────────────────────────────────────────────────────────
#  1. COLD EMAIL GENERATION
# ─────────────────────────────────────────────────────────────

_COLD_EMAIL_SYSTEM = """
You are an elite B2B sales copywriter. You craft cold emails that are:
- Concise (under 150 words in the body)
- Highly personalised to the recipient's name and company
- Focused on a single, compelling value proposition
- Written in a natural, professional tone — not salesy
- Structured with: a hook, a brief value pitch, and a clear single CTA

You must output a JSON object with exactly these keys:
  "subject"    : string – compelling email subject line (under 60 chars)
  "html_body"  : string – full HTML email body (use <p> tags, no outer HTML/body tags)
  "plain_body" : string – plain-text version of the body

Output ONLY the raw JSON object. No markdown fences, no preamble.
""".strip()


def generate_cold_email(
    lead_name: str,
    company: str,
    sender_name: str = "",
    value_prop: str = "helping B2B companies automate their outreach and book more meetings",
) -> GeneratedEmail:
    """
    Generate a personalised cold email for a specific lead.

    Parameters
    ----------
    lead_name  : First/full name of the prospect.
    company    : Prospect's company name.
    sender_name: Name of the sender (used inside the email).
    value_prop : One-sentence description of your value proposition.
    """
    client = get_openai_client()
    sender_name = sender_name or os.getenv("SENDER_NAME", "the team")

    user_prompt = (
        f"Write a cold outreach email to {lead_name} at {company}.\n"
        f"Sender name: {sender_name}.\n"
        f"Value proposition: {value_prop}.\n"
        f"Make it feel personal and relevant to {company}."
    )

    response = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _COLD_EMAIL_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
    )

    import json
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)

    email = GeneratedEmail(
        subject=data.get("subject", f"Quick question for {company}"),
        html_body=data.get("html_body", ""),
        plain_body=data.get("plain_body", ""),
    )
    logger.info("Generated cold email for %s @ %s | subject: %s", lead_name, company, email.subject)
    return email


# ─────────────────────────────────────────────────────────────
#  2. REPLY CLASSIFICATION
# ─────────────────────────────────────────────────────────────

_CLASSIFY_SYSTEM = """
You are a B2B email reply classifier. Analyse the reply and classify it into exactly
one of these categories:

  interested      – the prospect wants to learn more, schedule a call, or is clearly positive
  not_interested  – the prospect explicitly declines, is not a fit, or asks to stop contact
  follow_up       – the reply is non-committal, asks for more info, or needs a follow-up
  unknown         – cannot determine intent from the reply

Output ONLY a raw JSON object with keys:
  "category"   : one of the four strings above
  "confidence" : float between 0.0 and 1.0
  "reasoning"  : one sentence explaining the classification
""".strip()


def classify_reply(reply_text: str) -> ClassificationResult:
    """
    Classify an incoming email reply into a lead disposition category.

    Parameters
    ----------
    reply_text : The raw text of the prospect's reply email.
    """
    import json

    client = get_openai_client()

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        max_tokens=200,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user",   "content": f"Email reply:\n\n{reply_text[:2000]}"},
        ],
    )

    raw  = response.choices[0].message.content or "{}"
    data = json.loads(raw)

    result = ClassificationResult(
        category=data.get("category", "unknown"),
        confidence=float(data.get("confidence", 0.5)),
        reasoning=data.get("reasoning", ""),
    )
    logger.info("Classified reply as '%s' (confidence=%.2f)", result.category, result.confidence)
    return result


# ─────────────────────────────────────────────────────────────
#  3. AUTO-RESPONSE GENERATION
# ─────────────────────────────────────────────────────────────

_AUTO_RESPONSE_SYSTEM = """
You are a senior B2B account executive writing follow-up emails.
Given the classification and original reply, write a contextual response.

Rules:
- If interested: enthusiastically confirm interest, propose a concrete next step
  (e.g., "How does Tuesday at 3pm ET work for a 20-min call?")
- If follow_up: provide one relevant piece of value, then gently ask for a meeting
- If not_interested: send a gracious, professional farewell (no hard sell)

Output ONLY a raw JSON object with keys:
  "subject"    : string – reply subject (use Re: convention if possible)
  "html_body"  : string – HTML email body
  "plain_body" : string – plain-text body
""".strip()


def generate_auto_response(
    lead_name: str,
    company: str,
    original_reply: str,
    classification: REPLY_CATEGORIES,
    original_subject: str = "",
) -> GeneratedEmail:
    """
    Generate a contextual auto-response based on a classified reply.
    """
    import json

    client = get_openai_client()
    sender_name = os.getenv("SENDER_NAME", "the team")

    user_prompt = (
        f"Lead: {lead_name} at {company}\n"
        f"Classification: {classification}\n"
        f"Original subject: {original_subject}\n"
        f"Their reply:\n\n{original_reply[:1500]}\n\n"
        f"Sender name: {sender_name}.\n"
        f"Write the appropriate response."
    )

    response = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _AUTO_RESPONSE_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
    )

    raw  = response.choices[0].message.content or "{}"
    data = json.loads(raw)

    email = GeneratedEmail(
        subject=data.get("subject", f"Re: {original_subject}"),
        html_body=data.get("html_body", ""),
        plain_body=data.get("plain_body", ""),
    )
    logger.info("Generated auto-response for %s @ %s (classification=%s)", lead_name, company, classification)
    return email
