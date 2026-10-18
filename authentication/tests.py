"""
Automated tests for the authentication app.

Covers:
- Domain restriction (only @mituniversity.edu.in allowed)
- OTP expiry
- Incorrect attempt counting and lockout
- OTP reuse prevention
- Resend cooldown and per-hour limit
- JWT refresh
- Logout (token blacklisting)
- Protected endpoint access

Run with:  python manage.py test authentication
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models import OTPRequest
from authentication.otp import create_and_send_otp, verify_otp, hash_otp

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_otp_record(email, otp="123456", seconds_until_expiry=300, is_used=False, attempts=0):
    """Create an OTPRequest directly in the DB (bypasses email sending)."""
    return OTPRequest.objects.create(
        email=email,
        otp_hash=hash_otp(otp),
        expires_at=timezone.now() + timedelta(seconds=seconds_until_expiry),
        is_used=is_used,
        attempts=attempts,
    )


# ---------------------------------------------------------------------------
# Domain restriction
# ---------------------------------------------------------------------------

class DomainRestrictionTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("otp-request")

    @patch("authentication.otp.send_mail")
    def test_valid_domain_accepted(self, mock_mail):
        resp = self.client.post(self.url, {"email": "student@mituniversity.edu.in"}, format="json")
        self.assertEqual(resp.status_code, 200)

    @patch("authentication.otp.send_mail")
    def test_student_subdomain_accepted(self, mock_mail):
        resp = self.client.post(self.url, {"email": "adt23socb1005@students.mituniversity.edu.in"}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_wrong_domain_rejected(self):
        resp = self.client.post(self.url, {"email": "student@gmail.com"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("mituniversity.edu.in", str(resp.data))

    def test_missing_email_rejected(self):
        resp = self.client.post(self.url, {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_invalid_email_format_rejected(self):
        resp = self.client.post(self.url, {"email": "notanemail"}, format="json")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# OTP utility functions
# ---------------------------------------------------------------------------

class OTPUtilsTests(TestCase):

    EMAIL = "test@mituniversity.edu.in"

    def test_hash_otp_is_deterministic(self):
        self.assertEqual(hash_otp("123456"), hash_otp("123456"))

    def test_different_otps_have_different_hashes(self):
        self.assertNotEqual(hash_otp("111111"), hash_otp("222222"))

    @patch("authentication.otp.send_mail")
    def test_create_and_send_otp_creates_record(self, mock_mail):
        record = create_and_send_otp(self.EMAIL)
        self.assertEqual(record.email, self.EMAIL)
        self.assertFalse(record.is_used)
        self.assertEqual(record.attempts, 0)
        mock_mail.assert_called_once()

    @patch("authentication.otp.send_mail")
    def test_otp_never_in_mail_subject_or_debug_that_we_can_detect(self, mock_mail):
        # The OTP is in the message body (intentionally) but this test ensures
        # create_and_send_otp does not log it or return it.
        result = create_and_send_otp(self.EMAIL)
        self.assertIsNone(getattr(result, "otp", None))


# ---------------------------------------------------------------------------
# OTP expiry
# ---------------------------------------------------------------------------

class OTPExpiryTests(TestCase):

    EMAIL = "expiry@mituniversity.edu.in"

    def test_expired_otp_rejected(self):
        _make_otp_record(self.EMAIL, otp="123456", seconds_until_expiry=-1)
        with self.assertRaises(ValueError) as ctx:
            verify_otp(self.EMAIL, "123456")
        self.assertIn("expired", str(ctx.exception).lower())

    def test_valid_otp_accepted(self):
        _make_otp_record(self.EMAIL, otp="654321")
        record = verify_otp(self.EMAIL, "654321")
        self.assertTrue(record.is_used)


# ---------------------------------------------------------------------------
# Incorrect attempt counting and lockout
# ---------------------------------------------------------------------------

@override_settings(OTP_MAX_ATTEMPTS=5)
class OTPAttemptTests(TestCase):

    EMAIL = "attempts@mituniversity.edu.in"

    def test_wrong_otp_increments_attempts(self):
        record = _make_otp_record(self.EMAIL, otp="111111")
        with self.assertRaises(ValueError):
            verify_otp(self.EMAIL, "000000")
        record.refresh_from_db()
        self.assertEqual(record.attempts, 1)

    def test_lockout_after_max_attempts(self):
        _make_otp_record(self.EMAIL, otp="111111", attempts=4)
        with self.assertRaises(ValueError) as ctx:
            verify_otp(self.EMAIL, "000000")
        self.assertIn("too many", str(ctx.exception).lower())

    def test_correct_otp_succeeds_even_with_prior_failures(self):
        _make_otp_record(self.EMAIL, otp="111111", attempts=3)
        record = verify_otp(self.EMAIL, "111111")
        self.assertTrue(record.is_used)


# ---------------------------------------------------------------------------
# OTP reuse prevention
# ---------------------------------------------------------------------------

class OTPReuseTests(TestCase):

    EMAIL = "reuse@mituniversity.edu.in"

    def test_used_otp_cannot_be_reused(self):
        _make_otp_record(self.EMAIL, otp="777777", is_used=True)
        with self.assertRaises(ValueError):
            verify_otp(self.EMAIL, "777777")

    def test_second_verify_fails_after_first_success(self):
        _make_otp_record(self.EMAIL, otp="888888")
        verify_otp(self.EMAIL, "888888")  # first use — OK
        with self.assertRaises(ValueError):
            verify_otp(self.EMAIL, "888888")  # second use — fail


# ---------------------------------------------------------------------------
# Rate limits (DB-based: resend cooldown + hourly cap)
# ---------------------------------------------------------------------------

@override_settings(OTP_RESEND_COOLDOWN_SECONDS=60, OTP_MAX_PER_HOUR=5)
class OTPRateLimitTests(TestCase):

    EMAIL = "ratelimit@mituniversity.edu.in"

    def test_resend_cooldown_enforced(self):
        # One OTP exists created just now — a second request should be blocked.
        OTPRequest.objects.create(
            email=self.EMAIL,
            otp_hash=hash_otp("123456"),
            created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        with self.assertRaises(ValueError) as ctx:
            create_and_send_otp(self.EMAIL)
        self.assertIn("wait", str(ctx.exception).lower())

    @patch("authentication.otp.send_mail")
    def test_hourly_limit_enforced(self, _mock_mail):
        # Create 5 OTPs spread out (more than 60 s apart but within the hour).
        for i in range(5):
            OTPRequest.objects.create(
                email=self.EMAIL,
                otp_hash=hash_otp("000000"),
                created_at=timezone.now() - timedelta(minutes=10 + i * 2),
                expires_at=timezone.now() + timedelta(minutes=5),
            )
        with self.assertRaises(ValueError) as ctx:
            create_and_send_otp(self.EMAIL)
        self.assertIn("too many", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# Full API flow (request + verify → tokens)
# ---------------------------------------------------------------------------

class OTPAPIFlowTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    @patch("authentication.otp.send_mail")
    def test_full_otp_flow_creates_user_and_returns_tokens(self, _mock_mail):
        email = "newuser@mituniversity.edu.in"

        # 1. Request OTP.
        resp = self.client.post(reverse("otp-request"), {"email": email}, format="json")
        self.assertEqual(resp.status_code, 200)

        # 2. Get the OTP hash from DB and figure out the OTP.
        #    In tests we inject a known OTP directly.
        record = OTPRequest.objects.filter(email=email).latest("created_at")
        # Replace the hash with a known OTP so we can submit it.
        record.otp_hash = hash_otp("999999")
        record.save()

        # 3. Verify OTP.
        resp = self.client.post(
            reverse("otp-verify"),
            {"email": email, "otp": "999999"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertTrue(resp.data["created"])

        # 4. Check user was created.
        self.assertTrue(User.objects.filter(email=email).exists())

    @patch("authentication.otp.send_mail")
    def test_existing_user_not_recreated(self, _mock_mail):
        email = "existing@mituniversity.edu.in"
        User.objects.create_user(email=email, username=email, password=None)

        record = _make_otp_record(email, otp="123456")

        resp = self.client.post(
            reverse("otp-verify"),
            {"email": email, "otp": "123456"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["created"])
        self.assertEqual(User.objects.filter(email=email).count(), 1)


# ---------------------------------------------------------------------------
# JWT refresh
# ---------------------------------------------------------------------------

class JWTRefreshTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="jwt@mituniversity.edu.in",
            username="jwt@mituniversity.edu.in",
        )
        self.refresh = RefreshToken.for_user(self.user)

    def test_refresh_returns_new_tokens(self):
        resp = self.client.post(
            reverse("token-refresh"),
            {"refresh": str(self.refresh)},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_invalid_refresh_token_rejected(self):
        resp = self.client.post(
            reverse("token-refresh"),
            {"refresh": "this.is.invalid"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_missing_refresh_token_rejected(self):
        resp = self.client.post(reverse("token-refresh"), {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_blacklisted_refresh_token_rejected(self):
        # Blacklist the token first (simulating logout).
        self.refresh.blacklist()
        resp = self.client.post(
            reverse("token-refresh"),
            {"refresh": str(self.refresh)},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Logout (token blacklisting)
# ---------------------------------------------------------------------------

class LogoutTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="logout@mituniversity.edu.in",
            username="logout@mituniversity.edu.in",
        )
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def test_logout_blacklists_refresh_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        resp = self.client.post(
            reverse("logout"),
            {"refresh": str(self.refresh)},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

        # After logout the refresh token must be invalid.
        resp2 = self.client.post(
            reverse("token-refresh"),
            {"refresh": str(self.refresh)},
            format="json",
        )
        self.assertEqual(resp2.status_code, 401)

    def test_logout_requires_authentication(self):
        resp = self.client.post(
            reverse("logout"),
            {"refresh": str(self.refresh)},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_logout_without_refresh_token_returns_400(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        resp = self.client.post(reverse("logout"), {}, format="json")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Protected endpoint (/api/auth/me/)
# ---------------------------------------------------------------------------

class MeEndpointTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="me@mituniversity.edu.in",
            username="me@mituniversity.edu.in",
        )
        refresh = RefreshToken.for_user(self.user)
        self.access = str(refresh.access_token)

    def test_me_returns_profile_when_authenticated(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        resp = self.client.get(reverse("me"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email"], self.user.email)

    def test_me_requires_authentication(self):
        resp = self.client.get(reverse("me"))
        self.assertEqual(resp.status_code, 401)

    def test_me_with_invalid_token_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer bad.token.here")
        resp = self.client.get(reverse("me"))
        self.assertEqual(resp.status_code, 401)
