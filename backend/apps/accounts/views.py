from rest_framework import filters, mixins, viewsets
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.ai.client import ai_status
from apps.core.audit import log_action
from apps.core.defaults import deep_merge, get_org_settings, validate_org_settings
from apps.core.permissions import IsHR, IsOrgAdmin
from apps.core.throttles import LoginRateThrottle

from .models import AuditLog, User
from .serializers import (
    AuditLogSerializer,
    LoginSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ -> {access, refresh, user}. Rate limited."""

    serializer_class = LoginSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        username = str(request.data.get("username", ""))[:150]
        user = User.objects.filter(username=username).select_related("organization").first()
        org = user.organization if user else None
        try:
            response = super().post(request, *args, **kwargs)
        except APIException:
            log_action(request, "auth.login_failed", None, org=org, metadata={"username": username})
            raise
        log_action(request, "auth.login", user, org=org, actor=user, metadata={"username": username})
        return response


class MeView(APIView):
    permission_classes = [IsHR]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserViewSet(viewsets.ModelViewSet):
    """Admin-only HR user management (scoped to the admin's organisation)."""

    permission_classes = [IsOrgAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["username", "email", "first_name", "last_name"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return User.objects.filter(organization=self.request.user.organization).order_by("username")

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action == "partial_update":
            return UserUpdateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save(organization=self.request.user.organization)
        log_action(self.request, "user.create", user, metadata={"role": user.role})

    def perform_update(self, serializer):
        if serializer.instance.pk == self.request.user.pk and (
            serializer.validated_data.get("is_active") is False or serializer.validated_data.get("role") not in (None, "admin")
        ):
            from rest_framework.exceptions import ValidationError

            raise ValidationError("You cannot deactivate or demote your own account.")
        user = serializer.save()
        log_action(self.request, "user.update", user, metadata={"fields": sorted(serializer.validated_data.keys())})


class OrganizationSettingsView(APIView):
    """GET (HR) / PATCH (admin) organisation settings: weights, AI, voice, retention."""

    def get_permissions(self):
        return [IsOrgAdmin()] if self.request.method == "PATCH" else [IsHR()]

    def get(self, request):
        org = request.user.organization
        return Response({"settings": get_org_settings(org), "ai_status": ai_status(org)})

    def patch(self, request):
        org = request.user.organization
        incoming = request.data.get("settings", request.data)
        if not isinstance(incoming, dict):
            return Response({"detail": "settings must be an object"}, status=400)
        merged = deep_merge(get_org_settings(org), incoming)
        try:
            validate_org_settings(merged)
        except (ValueError, KeyError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=400)
        org.settings = merged
        org.save(update_fields=["settings"])
        log_action(request, "settings.update", org, metadata={"sections": sorted(incoming.keys())})
        return Response({"settings": merged, "ai_status": ai_status(org)})


class AuditLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsOrgAdmin]
    serializer_class = AuditLogSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["action", "entity_type", "entity_id"]

    def get_queryset(self):
        return AuditLog.objects.filter(organization=self.request.user.organization).select_related("actor")
