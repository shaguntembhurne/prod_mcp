"""
Serializers for authentication endpoints.

Kept in one file because there are only a handful and they are closely related.
"""

from django.conf import settings
from rest_framework import serializers


class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower().strip()
        domain = value.split("@")[-1]
        allowed = getattr(settings, "ALLOWED_EMAIL_DOMAIN", "mituniversity.edu.in")
        if domain != allowed and not domain.endswith("." + allowed):
            raise serializers.ValidationError(
                f"Only @{allowed} addresses (e.g. @students.{allowed}) are accepted."
            )
        return value


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)

    def validate_email(self, value):
        return value.lower().strip()

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must be 6 digits.")
        return value


class UserProfileSerializer(serializers.Serializer):
    """Read-only profile returned by GET /api/auth/me/"""

    id = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField()
