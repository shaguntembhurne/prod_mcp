"""
OTP helper utilities.

These are plain functions — no classes, no service layer — so they are easy
to read, test, and modify.
"""

import hashlib
import random
import string
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import OTPRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OTP generation and hashing
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    """Return a random 6-digit string (zero-padded)."""
    return "".join(random.choices(string.digits, k=6))


def hash_otp(otp: str) -> str:
    """Return hex-encoded SHA-256 of the OTP.  We never store the raw value."""
    return hashlib.sha256(otp.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Rate-limit checks
# ---------------------------------------------------------------------------
#
# NOTE: These checks are implemented using database queries and work correctly
# in a single-process setup (including multiple threads in the same process).
# In a multi-process or distributed deployment you should replace these with a
# shared cache (e.g. Redis) so all processes see the same counters.
#

def check_resend_cooldown(email: str) -> bool:
    """
    Return True if the email is still within the resend cooldown window.

    The caller should reject the request when this returns True.
    """
    cooldown_start = timezone.now() - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
    return OTPRequest.objects.filter(
        email=email,
        created_at__gte=cooldown_start,
    ).exists()


def check_hourly_limit(email: str) -> bool:
    """
    Return True if the email has already hit the per-hour OTP request cap.

    The caller should reject the request when this returns True.
    """
    one_hour_ago = timezone.now() - timedelta(hours=1)
    count = OTPRequest.objects.filter(
        email=email,
        created_at__gte=one_hour_ago,
    ).count()
    return count >= settings.OTP_MAX_PER_HOUR


# ---------------------------------------------------------------------------
# Core OTP flow
# ---------------------------------------------------------------------------

def create_and_send_otp(email: str) -> OTPRequest:
    """
    Generate a new OTP, persist a hashed copy, and send it by email.

    Raises ValueError if rate limits are exceeded.
    """
    if check_resend_cooldown(email):
        raise ValueError(
            f"Please wait {settings.OTP_RESEND_COOLDOWN_SECONDS} seconds before requesting a new OTP."
        )
    if check_hourly_limit(email):
        raise ValueError("Too many OTP requests. Please try again later.")

    otp = generate_otp()
    expires_at = timezone.now() + timedelta(seconds=settings.OTP_EXPIRY_SECONDS)

    otp_record = OTPRequest.objects.create(
        email=email,
        otp_hash=hash_otp(otp),
        expires_at=expires_at,
    )

    _send_otp_email(email, otp)
    # Never log the OTP itself.
    logger.info("OTP sent to %s (record id=%s)", email, otp_record.id)
    return otp_record


def _send_otp_email(email: str, otp: str) -> None:
    """Send the OTP to the user's email address."""
    subject = "Your MIT University login code"
    message = (
        f"Your one-time login code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRY_SECONDS // 60} minutes.\n"
        "If you did not request this, you can safely ignore this email."
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def verify_otp(email: str, otp: str):
    """
    Verify the OTP for an email address.

    Returns the matching OTPRequest on success.
    Raises ValueError with a user-safe message on any failure.

    On success the OTPRequest is marked as used so it cannot be reused.
    On failure the attempt counter is incremented; if it reaches the maximum
    the OTP is permanently invalidated.
    """
    # Fetch the most recent unused OTP for this email.
    record = (
        OTPRequest.objects.filter(email=email, is_used=False)
        .order_by("-created_at")
        .first()
    )

    if record is None:
        raise ValueError("No active OTP found for this email. Please request a new one.")

    if record.is_expired():
        raise ValueError("This OTP has expired. Please request a new one.")

    if record.is_exhausted():
        raise ValueError("Too many incorrect attempts. Please request a new OTP.")

    if record.otp_hash != hash_otp(otp):
        record.attempts += 1
        record.save(update_fields=["attempts"])
        remaining = settings.OTP_MAX_ATTEMPTS - record.attempts
        if remaining <= 0:
            raise ValueError("Too many incorrect attempts. Please request a new OTP.")
        raise ValueError(f"Incorrect OTP. {remaining} attempt(s) remaining.")

    # Correct OTP — mark it consumed.
    record.is_used = True
    record.save(update_fields=["is_used"])
    logger.info("OTP verified for %s (record id=%s)", email, record.id)
    return record
