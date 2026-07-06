"""
sender.py
─────────────────────────────────────────────────────────────
Antigravity :: Email Delivery Layer
Wraps the Resend SDK with structured error handling, retry
logic, and rich logging so every send attempt is fully audited.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import resend
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("antigravity.sender")

# ── Configuration ─────────────────────────────────────────────
resend.api_key = os.environ["RESEND_API_KEY"]

SENDER_NAME  = os.getenv("SENDER_NAME",  "Outreach")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")
FROM_ADDRESS = f"{SENDER_NAME} <{SENDER_EMAIL}>"

MAX_RETRIES   = 3
RETRY_BACKOFF = 2   # seconds (doubles each attempt)


# ── Result dataclass ──────────────────────────────────────────
@dataclass
class SendResult:
    success:    bool
    message_id: Optional[str] = None
    error:      Optional[str] = None
    attempts:   int = 1


# ── Core send function ────────────────────────────────────────
def send_email(
    to: str,
    subject: str,
    html_body: str,
    plain_body: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> SendResult:
    """
    Send a single email via Resend with automatic retry on
    transient failures (5xx / connection errors).

    Parameters
    ----------
    to         : Recipient email address.
    subject    : Email subject line.
    html_body  : HTML version of the email body.
    plain_body : Optional plain-text fallback.
    reply_to   : Optional reply-to address (defaults to sender).

    Returns
    -------
    SendResult with success flag, Resend message_id, and any error.
    """
    params: resend.Emails.SendParams = {
        "from":    FROM_ADDRESS,
        "to":      [to],
        "subject": subject,
        "html":    html_body,
    }

    if plain_body:
        params["text"] = plain_body

    if reply_to:
        params["reply_to"] = [reply_to]

    last_error: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Sending email to %s (attempt %d/%d)", to, attempt, MAX_RETRIES)
            response = resend.Emails.send(params)
            message_id = response.get("id") or getattr(response, "id", None)
            logger.info("✓ Email delivered  to=%s  id=%s", to, message_id)
            return SendResult(success=True, message_id=str(message_id), attempts=attempt)

        except resend.exceptions.ResendError as exc:
            last_error = f"ResendError [{exc.status_code}]: {exc.message}"  # type: ignore[attr-defined]
            logger.warning("Resend API error (attempt %d): %s", attempt, last_error)

            # Don't retry on client errors (4xx)
            if hasattr(exc, "status_code") and 400 <= exc.status_code < 500:  # type: ignore[attr-defined]
                break

        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("Unexpected send error (attempt %d): %s", attempt, last_error)

        if attempt < MAX_RETRIES:
            sleep_time = RETRY_BACKOFF ** attempt
            logger.info("Retrying in %ds…", sleep_time)
            time.sleep(sleep_time)

    logger.error("✗ Failed to send email to %s after %d attempts: %s", to, MAX_RETRIES, last_error)
    return SendResult(success=False, error=last_error, attempts=MAX_RETRIES)


# ── Batch send helper ─────────────────────────────────────────
def send_batch(
    messages: list[dict],
    delay_seconds: float = 1.5,
) -> list[SendResult]:
    """
    Send multiple emails sequentially with a configurable delay
    between sends to respect rate limits.

    Each dict in `messages` must have keys: to, subject, html_body.
    Optional keys: plain_body, reply_to.
    """
    results: list[SendResult] = []

    for idx, msg in enumerate(messages, start=1):
        logger.info("Batch send %d/%d → %s", idx, len(messages), msg.get("to"))
        result = send_email(
            to=msg["to"],
            subject=msg["subject"],
            html_body=msg["html_body"],
            plain_body=msg.get("plain_body"),
            reply_to=msg.get("reply_to"),
        )
        results.append(result)

        if idx < len(messages):
            time.sleep(delay_seconds)

    successes = sum(1 for r in results if r.success)
    logger.info("Batch complete: %d/%d sent successfully.", successes, len(messages))
    return results
