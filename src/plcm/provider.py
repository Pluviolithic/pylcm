"""Definition of an lcm provider."""

from abc import ABC, abstractmethod

from .connection import LcmConnection


class LcmProvider(ABC):
    @abstractmethod
    def __init__(self) -> None:
        """An lcm provider.

        An lcm provider is a simplified interface for
        "connecting" to other clients. The underyling
        implementation is abstracted away into an
        LcmConnection instance.
        """

    @abstractmethod
    def connect(self, url: str) -> LcmConnection:
        """Connect to other client(s).

        This could create a connection to an intermediary (e.g. a relay),
        bind to a socket for direct client-client communication (e.g. udp),
        or initialize any number of other netcode interfaces.

        Args:
            url: A url containing the provider, address, port number, and various
                other options (where relevant). E.g. tcpq:// or udpm://239.255.76.67:7667?ttl=1
                or providername://127.0.0.1. How those values and options are handled
                and processed is up to the underyling provider implementation.

        Returns:
            The resulting LcmConnection instance.

        Raises:
            ValueError: If provided url is invalid or incomplete.
            RuntimeError: If connection was unsuccesful in some manner
                or another.

        """
