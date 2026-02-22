"""SMTP email sender."""

from __future__ import annotations

from email.message import EmailMessage
import logging
import os
import smtplib


def _truthy(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def send_email(subject: str, text_body: str, html_body: str) -> bool:
    """Send digest email. Returns True when successfully sent."""
    logger = logging.getLogger("goi_finder.emailer")

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "")
    email_to = [item.strip() for item in os.getenv("EMAIL_TO", "").split(",") if item.strip()]
    email_from = os.getenv("EMAIL_FROM", "").strip() or smtp_user
    use_starttls = _truthy(os.getenv("SMTP_STARTTLS"), default=True)

    if not smtp_host or not email_to or not email_from:
        logger.warning(
            "Email skipped: set SMTP_HOST, EMAIL_TO, and EMAIL_FROM/SMTP_USER in environment."
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = ", ".join(email_to)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if use_starttls:
                smtp.starttls()
                smtp.ehlo()
            if smtp_user and smtp_pass:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        logger.info("Digest email sent to %s", ", ".join(email_to))
        return True
    except Exception as exc:  # pragma: no cover - network behavior
        logger.exception("Failed to send email: %s", exc)
        return False
