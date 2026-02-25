"""Tcpq provider implementation."""

import re
from collections.abc import Callable
from contextlib import suppress
from copy import copy
from multiprocessing import Event, Lock
from socket import MSG_WAITALL, SHUT_RDWR, create_connection
from threading import Thread
from urllib.parse import urlparse

from typing_extensions import Self, override

from .connection import (
    MAGIC_CLIENT,
    MAGIC_SERVER,
    PROTOCOL_VERSION,
    LcmConnection,
    LcmMessage,
    MessageType,
)
from .provider import LcmProvider
from .subscription import LcmSubscription

DEFAULT_URL = "tcpq://127.0.0.1:7700"


class LcmTcpqSubscription(LcmSubscription):
    @override
    def __init__(
        self,
        channel: str,
        callback: Callable[[str, bytes], None],
        unsubscribe: Callable[[Self], None],
    ) -> None:
        self._channel = channel
        self._inactive = Event()
        self._callback = callback
        self._unsubscribe = unsubscribe
        self._regex = re.compile(channel)

    @override
    def receive(self, channel: str, data: bytes) -> None:
        if not self.is_active() or self._regex.match(channel) is None:
            return

        self._callback(channel, data)

    @override
    def is_active(self) -> bool:
        return not self._inactive.is_set()

    @override
    def get_channel(self) -> str:
        return self._channel

    @override
    def unsubscribe(self) -> None:
        if not self.is_active():
            return

        self._inactive.set()
        self._unsubscribe(self)


class LcmTcpqConnection(LcmConnection):
    @override
    def __init__(self, url: str) -> None:
        parsed_url = urlparse(url)
        parsed_default_url = urlparse(DEFAULT_URL)

        address = parsed_url.hostname or parsed_default_url.hostname
        port = parsed_url.port or parsed_default_url.port

        self._sock = create_connection((address, port))  # ty:ignore[invalid-argument-type]
        self._perform_handshake()

        self._subscriptions = set()
        self._subscriptions_mutex = Lock()
        self._disconnected = Event()

        self._handle_subscriptions_thread_t = Thread(
            target=self._handle_subscriptions_thread
        )
        self._handle_subscriptions_thread_t.start()

    def _perform_handshake(self) -> None:
        try:
            self._sock.sendall(MAGIC_CLIENT + PROTOCOL_VERSION)
        except ConnectionError as exc:
            raise RuntimeError("Lcm handshake failed.") from exc

        if self._sock.recv(8, MSG_WAITALL) != MAGIC_SERVER + PROTOCOL_VERSION:
            raise RuntimeError("Received invalid handshake values from relay.")

    def _read_lcm_msg(self) -> LcmMessage:
        _ = self._sock.recv(4, MSG_WAITALL)
        channel_length = int.from_bytes(
            self._sock.recv(4, MSG_WAITALL), "big", signed=False
        )
        channel = self._sock.recv(channel_length, MSG_WAITALL).decode("ascii")
        data_length = int.from_bytes(self._sock.recv(4), "big", signed=False)
        data = self._sock.recv(data_length, MSG_WAITALL)

        return LcmMessage(channel=channel, data=data)

    def _handle_subscriptions_thread(self) -> None:
        while True:
            try:
                lcm_msg = self._read_lcm_msg()
            except (ConnectionError, OSError):
                break

            with self._subscriptions_mutex:
                for subscription in self._subscriptions:
                    subscription.receive(lcm_msg.channel, lcm_msg.data)

        self.disconnect()

    def _unsubscribe_callback(self, subscription: LcmSubscription) -> None:
        with self._subscriptions_mutex:
            self._subscriptions.discard(subscription)

        encoded_channel = subscription.get_channel().encode("ascii")

        try:
            self._sock.sendall(
                MessageType.UNSUBSCRIBE.to_bytes(4, "big", signed=False)
                + len(encoded_channel).to_bytes(4, "big", signed=False)
                + encoded_channel
            )
        except (ConnectionError, OSError):
            self.disconnect()
            return

    @override
    def subscribe(
        self,
        channel: str,
        callback: Callable[[str, bytes], None],
    ) -> LcmSubscription | None:
        if not self.is_connected():
            return None

        subscription = LcmTcpqSubscription(
            channel, callback, self._unsubscribe_callback
        )

        with self._subscriptions_mutex:
            self._subscriptions.add(subscription)

        encoded_channel = channel.encode("ascii")
        try:
            self._sock.sendall(
                MessageType.SUBSCRIBE.to_bytes(4, "big", signed=False)
                + len(encoded_channel).to_bytes(4, "big", signed=False)
                + encoded_channel
            )
        except (ConnectionError, OSError):
            self.disconnect()
            return None

        return subscription

    @override
    def is_connected(self) -> bool:
        return not self._disconnected.is_set()

    @override
    def disconnect(self) -> None:
        if not self.is_connected():
            return

        self._disconnected.set()

        with suppress(OSError):
            self._sock.shutdown(SHUT_RDWR)
            self._sock.close()

        with self._subscriptions_mutex:
            subscriptions = copy(self._subscriptions)
            self._subscriptions = set()

        for subscription in subscriptions:
            subscription.unsubscribe()

        self._handle_subscriptions_thread_t.join()

    @override
    def publish(self, channel: str, data: bytes) -> None:
        if not self.is_connected():
            raise RuntimeError("Lcm not connected.")

        encoded_channel = channel.encode("ascii")

        try:
            self._sock.sendall(
                MessageType.PUBLISH.to_bytes(4, "big", signed=False)
                + len(encoded_channel).to_bytes(4, "big", signed=False)
                + encoded_channel
                + len(data).to_bytes(4, "big", signed=False)
                + data
            )
        except (ConnectionError, OSError):
            self.disconnect()


class LcmTcpqProvider(LcmProvider):
    @override
    def __init__(self) -> None:
        self._provider_name = urlparse(DEFAULT_URL).scheme

    @override
    def connect(self, url: str) -> LcmTcpqConnection:
        parsed_url = urlparse(url)

        if parsed_url.scheme != self._provider_name:
            raise ValueError(
                f"Passed url contains invalid provider. Expected {self._provider_name}"
                f", got {parsed_url.scheme}."
            )

        return LcmTcpqConnection(url)
