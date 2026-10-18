from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTPRequest


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "username", "is_staff", "date_joined", "last_login")
    search_fields = ("email", "username")
    ordering = ("-date_joined",)


@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "expires_at", "is_used", "attempts")
    list_filter = ("is_used",)
    search_fields = ("email",)
    readonly_fields = ("otp_hash",)  # never edit hashes manually
    ordering = ("-created_at",)
