class AIConfigurationError(Exception):
    """AI provider is not configured (missing provider, key or consent setting)."""


class AIProviderError(Exception):
    """The configured provider failed or returned unusable output."""
