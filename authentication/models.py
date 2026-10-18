"""
Custom user model and OTP model.

We extend AbstractUser so we keep all of Django's built-in auth machinery
(permissions, admin, etc.) while being free to add fields later.

OTPRequest stores each OTP issued to an email address.  The table is the
single source of truth for expiry, attempt counting, and resend throttling.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """
    Minimal custom user model.

    Using email as the primary identifier; username is still required by
    AbstractUser but we set it to the email address on creation so it stays
    unique without extra work.
    """

    email = models.EmailField(unique=True)

    # We use email to log in, not username.
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email


class OTPRequest(models.Model):
    """
    One row per OTP issued.

    Fields
    ------
    email       : the address the OTP was sent to
    otp_hash    : SHA-256 hash of the 6-digit code — never stored in plain text
    created_at  : when this OTP was generated
    expires_at  : when it stops being valid
    is_used     : True once the OTP has been verified successfully
    attempts    : number of wrong guesses so far
    """

    email = models.EmailField(db_index=True)
    otp_hash = models.CharField(max_length=64)  # hex-encoded SHA-256
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def is_exhausted(self):
        from django.conf import settings
        return self.attempts >= settings.OTP_MAX_ATTEMPTS

    def __str__(self):
        return f"OTP for {self.email} at {self.created_at:%Y-%m-%d %H:%M:%S}"
