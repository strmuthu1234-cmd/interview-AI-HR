import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    # Scoring weights, AI/voice/retention preferences. See apps.core.defaults.
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        HR_MANAGER = "hr_manager", "HR Manager"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.HR_MANAGER)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="users", null=True, blank=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        indexes = [models.Index(fields=["organization", "role"])]

    @property
    def is_hr(self):
        """True for any authenticated staff user (HR manager or admin)."""
        return self.is_active and self.role in (self.Role.ADMIN, self.Role.HR_MANAGER)

    @property
    def is_org_admin(self):
        return self.is_active and self.role == self.Role.ADMIN

    is_candidate = False


class AuditLog(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    actor_label = models.CharField(max_length=50, blank=True)  # "candidate" / "system" when no user
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
