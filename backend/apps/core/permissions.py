from rest_framework.permissions import BasePermission


class IsHR(BasePermission):
    """HR managers and admins (staff users)."""

    message = "HR access required."

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_hr", False))


class IsOrgAdmin(BasePermission):
    message = "Administrator access required."

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_org_admin", False))


class IsCandidate(BasePermission):
    """Request authenticated by an interview invitation token."""

    message = "A valid interview link is required."

    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_candidate", False))


class IsHROrCandidate(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and (getattr(u, "is_hr", False) or getattr(u, "is_candidate", False)))
