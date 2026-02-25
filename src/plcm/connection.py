"""Definition of an lcm connection."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

from .subscription import LcmSubscription

MAGIC_SERVER = b"\x28\x76\x17\xfa"
MAGIC_CLIENT = b"\x28\x76\x17\xfb"
PROTOCOL_VERSION = b"\x00\x00\x01\x00"


class MessageType(IntEnum):
    """Indicators to notify a relay of what action is being taken."""

    PUBLISH = 1
    SUBSCRIBE = 2
    UNSUBSCRIBE = 3


@dataclass
class LcmMessage:
    """Simple container for channel and data information."""

    channel: str
    data: bytes


class LcmConnection(ABC):
    @abstractmethod
    def __init__(self, url: str) -> None:
        """An lcm connection.

        An lcm connection represents & handles connections
        to other peers in the system. This could be through
        a tcp relay or peer-to-peer via udp multicast or any
        other protocol.

        Args:
            url: A url containing the provider, address, port number, and various
                other options (where relevant). E.g. tcpq:// or udpm://239.255.76.67:7667?ttl=1
                or providername://127.0.0.1. How those values and options are handled
                and processed is up to the underyling provider implementation.

        Raises:
            ValueError: If provided url is invalid or incomplete.
            RuntimeError: If connection was unsuccesful in some manner
                or another.

        """

    @abstractmethod
    def is_connected(self) -> bool:
        """Determine whether connection is still active.

        Returns:
            Whether the connection is still active.

        """

    @abstractmethod
    def publish(self, channel: str, data: bytes) -> None:
        """Publish data on provided channel over the `connection`.

        Args:
            channel: The channel to publish data on.
            data: The data to publish.

        Raises:
            RuntimeError: When not connected.

        """

    @abstractmethod
    def disconnect(self) -> None:
        """Remove the connection and all subscriptions."""

    @abstractmethod
    def subscribe(
        self,
        channel: str,
        callback: Callable[[str, bytes], None],
    ) -> LcmSubscription | None:
        """Subscribe to messages on a channel.

        Args:
            channel: The channel (or channel regex) to subscribe to.
                The value is passed to `re.compile` for matching,
                so a raw string may be desirable, e.g. r"xyz".
            callback: The callback to call with data obtained on any channels
                that match the provided channel/channel regex. The callback
                is expected to be non-blocking.

        """
