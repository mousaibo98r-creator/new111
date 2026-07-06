"""
main.py
─────────────────────────────────────────────────────────────
Antigravity :: Orchestration Engine
The central controller that wires together db.py, ai_engine.py,
and sender.py into three high-level workflows:

  1. run_campaign()       – Generate + send cold emails to all
                            leads with status = 'pending'
  2. process_reply()      – Classify an inbound reply, update lead
                            status, and send an auto-response
  3. run_follow_up()      – Send follow-ups to leads with
                            status = 'follow_up'

Run from the terminal:
    python main.py --mode campaign
    python main.py --mode follow_up
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

import ai_engine
import db
import sender

load_dotenv()

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("antigravity.main")

SENDER_NAME  = os.getenv("SENDER_NAME",  "Outreach Team")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "outreach@yourdomain.com")

VALUE_PROP = os.getenv(
    "VALUE_PROP",
    "helping B2B companies automate their outreach and book more qualified meetings",
)


# ═══════════════════════════════════════════════════════════════
#  WORKFLOW 1 – COLD EMAIL CAMPAIGN
# ═══════════════════════════════════════════════════════════════

def run_campaign(dry_run: bool = False) -> dict:
    """
    Fetch all 'pending' leads, generate a personalised cold email
    for each, send it, and update the lead status + log.

    Parameters
    ----------
    dry_run : If True, generate emails but do NOT send or update DB.

    Returns
    -------
    Summary dict with sent / failed / skipped counts.
    """
    logger.info("═══ CAMPAIGN START (dry_run=%s) ═══", dry_run)
    leads = db.get_all_leads(status_filter="pending")
    logger.info("Found %d pending leads.", len(leads))

    stats = {"sent": 0, "failed": 0, "skipped": 0}

    for lead in leads:
        lead_id  = lead["id"]
        name     = lead["name"]
        company  = lead["company"]
        email    = lead["email"]

        try:
            # 1. Generate personalised email
            generated = ai_engine.generate_cold_email(
                lead_name=name,
                company=company,
                sender_name=SENDER_NAME,
                value_prop=VALUE_PROP,
            )

            if dry_run:
                logger.info("[DRY RUN] Would send to %s | Subject: %s", email, generated.subject)
                stats["skipped"] += 1
                continue

            # 2. Send via Resend
            result = sender.send_email(
                to=email,
                subject=generated.subject,
                html_body=generated.html_body,
                plain_body=generated.plain_body,
                reply_to=SENDER_EMAIL,
            )

            if result.success:
                # 3a. Update lead status
                db.update_lead_status(lead_id, "sent")

                # 3b. Log the send event
                db.create_log(
                    email=email,
                    event_type="email_sent",
                    lead_id=lead_id,
                    subject=generated.subject,
                    body_preview=generated.plain_body[:500],
                    metadata={"resend_id": result.message_id, "attempts": result.attempts},
                )
                stats["sent"] += 1
                logger.info("✓ Sent to %s <%s>", name, email)

            else:
                # 3c. Log the failure
                db.create_log(
                    email=email,
                    event_type="email_failed",
                    lead_id=lead_id,
                    subject=generated.subject,
                    metadata={"error": result.error, "attempts": result.attempts},
                )
                stats["failed"] += 1
                logger.error("✗ Failed to send to %s: %s", email, result.error)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error processing lead %s: %s", email, exc)
            db.create_log(
                email=email,
                event_type="email_failed",
                lead_id=lead_id,
                metadata={"error": str(exc)},
            )
            stats["failed"] += 1

    logger.info(
        "═══ CAMPAIGN COMPLETE | sent=%d  failed=%d  skipped=%d ═══",
        stats["sent"], stats["failed"], stats["skipped"],
    )
    return stats


# ═══════════════════════════════════════════════════════════════
#  WORKFLOW 2 – REPLY PROCESSING
# ═══════════════════════════════════════════════════════════════

def process_reply(
    email: str,
    reply_text: str,
    original_subject: str = "",
    send_auto_response: bool = True,
) -> dict:
    """
    Process an incoming reply from a prospect:
      - Classify the reply with AI
      - Update lead status in DB
      - Optionally send a contextual auto-response

    Parameters
    ----------
    email               : The prospect's email address.
    reply_text          : Full text of their reply.
    original_subject    : Subject of the email they're replying to.
    send_auto_response  : If True, generate + send an auto-response.

    Returns
    -------
    Dict with classification and auto_response_sent flag.
    """
    logger.info("Processing reply from %s", email)

    lead = db.get_lead_by_email(email)
    if not lead:
        logger.warning("No lead found for %s – logging without lead_id.", email)

    lead_id = lead["id"] if lead else None
    name    = lead["name"]    if lead else "there"
    company = lead["company"] if lead else "your company"

    # 1. Classify reply
    classification = ai_engine.classify_reply(reply_text)

    # 2. Map classification → lead status
    status_map = {
        "interested":     "interested",
        "not_interested": "not_interested",
        "follow_up":      "follow_up",
        "unknown":        "replied",
    }
    new_status = status_map.get(classification.category, "replied")

    if lead_id:
        db.update_lead_status(lead_id, new_status)

    # 3. Log classification
    db.create_log(
        email=email,
        event_type="reply_classified",
        lead_id=lead_id,
        body_preview=reply_text[:500],
        ai_classification=classification.category,
        ai_confidence=classification.confidence,
        metadata={"reasoning": classification.reasoning},
    )

    result = {"classification": classification.category, "auto_response_sent": False}

    # 4. Generate + send auto-response (skip if not_interested)
    if send_auto_response and classification.category != "not_interested":
        try:
            auto_email = ai_engine.generate_auto_response(
                lead_name=name,
                company=company,
                original_reply=reply_text,
                classification=classification.category,
                original_subject=original_subject,
            )

            send_result = sender.send_email(
                to=email,
                subject=auto_email.subject,
                html_body=auto_email.html_body,
                plain_body=auto_email.plain_body,
                reply_to=SENDER_EMAIL,
            )

            if send_result.success:
                db.create_log(
                    email=email,
                    event_type="auto_response_sent",
                    lead_id=lead_id,
                    subject=auto_email.subject,
                    body_preview=auto_email.plain_body[:500],
                    metadata={"resend_id": send_result.message_id},
                )
                result["auto_response_sent"] = True

        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send auto-response to %s: %s", email, exc)

    logger.info(
        "Reply processed: email=%s  category=%s  auto_sent=%s",
        email, classification.category, result["auto_response_sent"],
    )
    return result


# ═══════════════════════════════════════════════════════════════
#  WORKFLOW 3 – FOLLOW-UP CAMPAIGN
# ═══════════════════════════════════════════════════════════════

def run_follow_up(dry_run: bool = False) -> dict:
    """
    Send a follow-up email to all leads currently in 'follow_up'
    status.  Uses the same generation pipeline as run_campaign()
    but with a follow-up-specific prompt.
    """
    logger.info("═══ FOLLOW-UP START (dry_run=%s) ═══", dry_run)
    leads = db.get_all_leads(status_filter="follow_up")
    logger.info("Found %d follow-up leads.", len(leads))

    stats = {"sent": 0, "failed": 0, "skipped": 0}

    for lead in leads:
        lead_id = lead["id"]
        name    = lead["name"]
        company = lead["company"]
        email   = lead["email"]

        try:
            follow_up_prop = f"following up to see if {company} would benefit from {VALUE_PROP}"
            generated = ai_engine.generate_cold_email(
                lead_name=name,
                company=company,
                sender_name=SENDER_NAME,
                value_prop=follow_up_prop,
            )

            if dry_run:
                logger.info("[DRY RUN] Follow-up to %s | Subject: %s", email, generated.subject)
                stats["skipped"] += 1
                continue

            result = sender.send_email(
                to=email,
                subject=f"Re: {generated.subject}",
                html_body=generated.html_body,
                plain_body=generated.plain_body,
                reply_to=SENDER_EMAIL,
            )

            event = "email_sent" if result.success else "email_failed"
            db.create_log(
                email=email,
                event_type=event,
                lead_id=lead_id,
                subject=generated.subject,
                body_preview=generated.plain_body[:500],
                metadata={"resend_id": result.message_id, "type": "follow_up"},
            )

            if result.success:
                stats["sent"] += 1
            else:
                stats["failed"] += 1

        except Exception as exc:  # noqa: BLE001
            logger.exception("Error in follow-up for %s: %s", email, exc)
            stats["failed"] += 1

    logger.info(
        "═══ FOLLOW-UP COMPLETE | sent=%d  failed=%d  skipped=%d ═══",
        stats["sent"], stats["failed"], stats["skipped"],
    )
    return stats


# ═══════════════════════════════════════════════════════════════
#  CLI ENTRYPOINT
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="antigravity",
        description="Antigravity B2B Cold Email Outreach – Orchestration CLI",
    )
    parser.add_argument(
        "--mode",
        choices=["campaign", "follow_up"],
        required=True,
        help="Which workflow to run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Generate emails but do NOT send or update DB.",
    )
    args = parser.parse_args()

    if args.mode == "campaign":
        stats = run_campaign(dry_run=args.dry_run)
    elif args.mode == "follow_up":
        stats = run_follow_up(dry_run=args.dry_run)

    logger.info("Final stats: %s", stats)
    sys.exit(0 if stats.get("failed", 0) == 0 else 1)


if __name__ == "__main__":
    main()
