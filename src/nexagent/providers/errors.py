"""Provider-specific error types."""


class ProviderError(RuntimeError):
    """Base error for model-provider failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when a configured local provider cannot be reached."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an unusable response."""
