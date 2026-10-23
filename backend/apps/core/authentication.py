"""Candidate authentication via secure interview-invitation token.

Candidates have no account. They present `Authorization: Invitation <token>`;
only the SHA-256 hash of the token is stored in the database.
"""
import hashlib

from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CandidatePrincipal:
    """Stand-in for `request.user` on candidate requests."""

    is_authenticated = True
    is_anonymous = False
    is_candidate = True
    is_hr = False
    is_org_admin = False
    is_active = True

    def __init__(self, invitation):
        self.invitation = invitation
        self.pk = invitation.pk

    def __str__(self):
        return f"candidate:{self.invitation.candidate_id}"


class InvitationAuthentication(BaseAuthentication):
    keyword = b"invitation"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword:
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Invalid invitation header.")
        from apps.interviews.models import InterviewInvitation

        try:
            token = parts[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed("Invalid invitation token.")
        try:
            invitation = InterviewInvitation.objects.select_related("session", "candidate", "job").get(
                token_hash=hash_token(token)
            )
        except InterviewInvitation.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid or expired interview link.")
        if not invitation.is_usable():
            raise exceptions.AuthenticationFailed("This interview link has expired or was revoked.")
        return CandidatePrincipal(invitation), invitation

    def authenticate_header(self, request):
        return "Invitation"
