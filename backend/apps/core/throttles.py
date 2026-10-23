from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class UploadRateThrottle(UserRateThrottle):
    scope = "upload"


class CandidateRateThrottle(SimpleRateThrottle):
    """Throttle per invitation (not per IP) so shared networks are not penalised."""

    scope = "candidate"

    def get_cache_key(self, request, view):
        inv = getattr(request, "auth", None)
        if inv is None or not hasattr(inv, "pk"):
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(inv.pk)}
