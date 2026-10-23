from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, Organization, User


@admin.register(User)
class HRUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "organization", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Organisation", {"fields": ("role", "organization")}),)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "entity_type", "entity_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
