"""
Authentication views.

Five endpoints, all plain APIView subclasses — no mixins, no viewsets.
Each view is self-contained and reads like a short story.
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .otp import create_and_send_otp, verify_otp
from .rate_limit import is_rate_limited
from .serializers import OTPRequestSerializer, OTPVerifySerializer, UserProfileSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_client_ip(request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For if set."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class OTPRequestView(APIView):
    """
    POST /api/auth/otp/request/

    Accept an email address, validate the domain, apply rate limits, and
    send a one-time code.

    Rate limits (IP-based, single-process):
    - 10 requests per IP per 10 minutes
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # IP-level rate limit: 10 OTP requests per 10 minutes per IP.
        ip = _get_client_ip(request)
        if is_rate_limited(ip, max_requests=10, window_seconds=600):
            return Response(
                {"detail": "Too many OTP requests from this IP. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = OTPRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]

        try:
            create_and_send_otp(email)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except Exception:
            logger.exception("Failed to send OTP to %s", email)
            return Response(
                {"detail": "Failed to send OTP. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "OTP sent. Please check your email."},
            status=status.HTTP_200_OK,
        )


class OTPVerifyView(APIView):
    """
    POST /api/auth/otp/verify/

    Verify the OTP.  On success, create the user if they don't exist yet and
    return JWT access + refresh tokens.

    Rate limits (IP-based, single-process):
    - 20 verification attempts per IP per 10 minutes
    """

    permission_classes = [AllowAny]

    def post(self, request):
        ip = _get_client_ip(request)
        if is_rate_limited(ip, max_requests=20, window_seconds=600):
            return Response(
                {"detail": "Too many verification attempts. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = OTPVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]

        try:
            verify_otp(email, otp)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Get or create the user (first login auto-registers).
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": email},
        )

        # Issue JWT tokens.
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "created": created,
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    """
    POST /api/auth/token/refresh/

    Exchange a valid refresh token for a new access token (and a rotated
    refresh token, because ROTATE_REFRESH_TOKENS=True).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
            new_access = str(refresh.access_token)
            # Rotation: blacklist the old token and generate a new one.
            refresh.blacklist()
            new_refresh = str(RefreshToken.for_user(
                User.objects.get(id=refresh["user_id"])
            ))
        except TokenError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({"access": new_access, "refresh": new_refresh})


class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Blacklist the supplied refresh token so it can no longer be used.
    Requires a valid access token in the Authorization header.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """
    GET /api/auth/me/

    Return the authenticated user's basic profile.
    Requires a valid Bearer access token.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)
