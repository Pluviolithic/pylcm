"""Definition of an lcm subscription."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from typing_extensions import Self


class LcmSubscription(ABC):
    @abstractmethod
    def __init__(
        self,
        channel: str,
        callback: Callable[[str, bytes], None],
        unsubscribe: Callable[[Self], None],
    ) -> None:
        """An lcm subscription.

        An lcm subscription represents a specific
        subscription to a channel, which is essentially a
        channel string / regex and a callback. Whenever
        data is received on a channel that matches the
        channel string / regex, the callback is called
        with the obtained channel and data.

        Args:
            channel: The channel (or channel regex) to subscribe to.
                The value is passed to `re.compile` for matching,
                so a raw string may be desirable, e.g. r"xyz".
            callback: The callback to call with data obtained on any
                channels that match the provided channel/channel regex.
                The callback is expected to be non-blocking.
            unsubscribe: The callback to call when unsubscribing.
                Usually will be a means to remove references to
                the subscription in an lcm provider or connection.

        """

    @abstractmethod
    def receive(self, channel: str, data: bytes) -> None:
        """Receive data, validate channel, and pass to callback.

        Args:
            channel: The channel to validate and process.
            data: The data to process if the channel matches
                this subscription's criteria.

        """

    @abstractmethod
    def is_active(self) -> bool:
        """Determine whether subscription is still active.

        Returns:
            Whether the subscription is still active.

        """

    @abstractmethod
    def get_channel(self) -> str:
        """Obtain the channel string this subscription was initialized with.

        Returns:
            The channel string used to create this subscription.

        """

    @abstractmethod
    def unsubscribe(self) -> None:
        """Stop this subscription from receiving messages."""
