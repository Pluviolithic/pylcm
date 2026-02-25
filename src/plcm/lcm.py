"""Primary interface for registering and using providers."""

from urllib.parse import urlparse

from .connection import LcmConnection
from .provider import LcmProvider
from .tcpq_provider import LcmTcpqProvider


class Lcm:
    def __init__(self) -> None:
        """Primary interface for registering and using providers."""
        self._providers = {}

        self.register_provider("tcpq", LcmTcpqProvider)

    def connect(self, url: str) -> LcmConnection | None:
        """Connect to other client(s) using the specified provider.

        Args:
            url: A url containing the provider, address, port number, and various
                other options (where relevant). E.g. tcpq:// or udpm://239.255.76.67:7667?ttl=1
                or providername://127.0.0.1. How those values and options are handled
                and processed is up to the underyling provider implementation.

        Returns:
            The lcm connection instance, if successful.

        Raises:
            ValueError: If provider not declared in passed url.
            RuntimeError: If passed provider is not registered.

        """
        parsed_url = urlparse(url)

        if not parsed_url.scheme:
            raise ValueError(f"No provider declared in connection url: {url}.")

        if parsed_url.scheme not in self._providers:
            raise RuntimeError(f"No {parsed_url.scheme} provider is registered.")

        try:
            return self._providers[parsed_url.scheme].connect(url)
        except (RuntimeError, ValueError):
            return None

    def register_provider(
        self,
        provider_name: str,
        provider: type[LcmProvider],
        override_existing: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        """Register a new provider.

        Args:
            provider_name: The name of the provider. This will be used
                when selecting which provider to use based on the
                provider_name://address:port part of a url.
            provider: The provider to register.
            override_existing: Whether to replace another provider
                already associated with provider_name.

        Raises:
            ValueError: If a provider is already registered under
                the passed provider_name and override_existing is not set.
        """
        if provider_name in self._providers and not override_existing:
            raise ValueError(
                "Provider already exists and `override_existing` not set."
                " Unable to register.",
            )

        self._providers[provider_name] = provider()
