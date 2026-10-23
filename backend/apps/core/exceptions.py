import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.ai.errors import AIConfigurationError, AIProviderError

log = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    if isinstance(exc, AIConfigurationError):
        return Response(
            {"detail": str(exc), "code": "ai_not_configured"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, AIProviderError):
        log.warning("AI provider error: %s", exc)
        return Response({"detail": str(exc), "code": "ai_provider_error"}, status=status.HTTP_502_BAD_GATEWAY)
    return exception_handler(exc, context)
