from django.contrib import admin

from .models import AuthLoginSession, AuthorizationCode, CloudConnection, ManagedOAuthPending


@admin.register(CloudConnection)
class CloudConnectionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "connector", "provider", "account", "status", "updated_at")
    list_filter = ("provider", "connector", "status")
    search_fields = ("account", "account_id", "user__email")
    readonly_fields = ("id", "created_at", "updated_at", "has_refresh_token", "has_access_token")
    exclude = ("refresh_token", "access_token")

    @admin.display(boolean=True, description="Has refresh token")
    def has_refresh_token(self, obj: CloudConnection) -> bool:
        return bool(obj.refresh_token)

    @admin.display(boolean=True, description="Has access token")
    def has_access_token(self, obj: CloudConnection) -> bool:
        return bool(obj.access_token)


@admin.register(AuthLoginSession)
class AuthLoginSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "client_id", "created_at", "expires_at")
    readonly_fields = ("id", "created_at")
    exclude = ("code_challenge",)


@admin.register(AuthorizationCode)
class AuthorizationCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "user", "client_id", "created_at", "expires_at", "consumed_at")
    readonly_fields = ("code", "created_at", "consumed_at")
    exclude = ("code_challenge",)


@admin.register(ManagedOAuthPending)
class ManagedOAuthPendingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "provider", "connector", "created_at", "expires_at")
    readonly_fields = ("id", "created_at", "app_state")
