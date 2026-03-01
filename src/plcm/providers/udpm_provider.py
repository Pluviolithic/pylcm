"""Udpm provider implementation."""

import re
import struct
from collections.abc import Callable
from contextlib import suppress
from copy import copy
from dataclasses import dataclass
from multiprocessing import Event, Lock, Queue
from selectors import EVENT_READ, DefaultSelector
from socket import (
    AF_INET,
    INADDR_ANY,
    IP_ADD_MEMBERSHIP,
    IP_MULTICAST_LOOP,
    IP_MULTICAST_TTL,
    IPPROTO_IP,
    IPPROTO_UDP,
    SHUT_RDWR,
    SO_REUSEADDR,
    SO_REUSEPORT,
    SOCK_DGRAM,
    SOL_SOCKET,
    inet_aton,
    socket,
)
from threading import Thread
from urllib.parse import urlparse

from typing_extensions import Self, override

from plcm import LcmConnection, LcmMessage
from plcm.provider import LcmProvider
from plcm.subscription import LcmSubscription

MAGIC_SHORT = b"LC02"
MAGIC_LONG = b"LC03"
FRAGMENTATION_THRESHOLD = 64_000

PROVIDER_NAME = "udpm"
DEFAULT_ADDRESS = "239.255.76.76"
DEFAULT_PORT = 7667
DEFAULT_TTL = 1


@dataclass
class LcmFragmentBuffer:
    data: bytes
    channel: str
    sequence_number: int
    source_address: tuple[str, int]
    fragments_remaining: int
    current_fragment_number: int


class LcmUdpmSubscription(LcmSubscription):
    @override
    def __init__(
        self,
        channel: str,
        callback: Callable[[str, bytes], None],
        unsubscribe: Callable[[Self], None],
    ) -> None:
        self._queue = Queue()
        self._channel = channel
        self._inactive = Event()
        self._callback = callback
        self._unsubscribe = unsubscribe
        self._regex = re.compile(channel)

        self._process_queue_thread_t = Thread(target=self._process_queue_thread)
        self._process_queue_thread_t.start()

    @override
    def receive(self, channel: str, data: bytes) -> None:
        if not self.is_active() or self._regex.match(channel) is None:
            return

        self._queue.put(LcmMessage(channel=channel, data=data))

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
        self._queue.put(None)

        self._process_queue_thread_t.join()

    def _process_queue_thread(self) -> None:
        while self.is_active():
            lcm_msg = self._queue.get()

            if lcm_msg is None:
                return

            self._callback(lcm_msg.channel, lcm_msg.data)


class LcmUdpmConnection(LcmConnection):
    @override
    def __init__(self, url: str) -> None:
        parsed_url = urlparse(url)

        address = (
            parsed_url.hostname if parsed_url.hostname is not None else DEFAULT_ADDRESS
        )
        port = parsed_url.port if parsed_url.port is not None else DEFAULT_PORT

        self._destination_address = (address, port)

        try:
            in_addr = inet_aton(address)
        except ValueError as exc:
            raise ValueError(f"Invalid multicast address: {address}") from exc

        self._sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)

        ttl = (
            re.match(r"ttl=(\d+)", parsed_url.query)
            if parsed_url.query is not None
            else None
        )
        ttl = int(ttl.group(1)) if ttl is not None else DEFAULT_TTL

        self._sock.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
        self._sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self._sock.setsockopt(IPPROTO_IP, IP_MULTICAST_LOOP, 1)
        self._sock.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, ttl)

        self._sock.bind((address, port))

        mreq = struct.pack("4sl", in_addr, INADDR_ANY)
        self._sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)

        self._sequence_number = 0
        self._subscriptions = set()
        self._disconnected = Event()
        self._fragment_buffers = {}

        self._publish_mutex = Lock()
        self._subscriptions_mutex = Lock()

        self._handle_subscriptions_thread_t = Thread(
            target=self._handle_subscriptions_thread
        )
        self._handle_subscriptions_thread_t.start()

    @override
    def publish(self, channel: str, data: bytes) -> None:
        if not self.is_connected():
            raise RuntimeError("Lcm not connected.")

        with self._publish_mutex:
            encoded_channel = channel.encode("ascii") + b"\x00"
            payload = encoded_channel + data

            if len(payload) < FRAGMENTATION_THRESHOLD:
                self._publish_small_payload(payload)
            else:
                self._publish_large_payload(encoded_channel, data)

            self._sequence_number += 1

    @override
    def subscribe(
        self, channel: str, callback: Callable[[str, bytes], None]
    ) -> LcmUdpmSubscription | None:
        if not self.is_connected():
            return None

        subscription = LcmUdpmSubscription(
            channel, callback, self._unsubscribe_callback
        )

        with self._subscriptions_mutex:
            self._subscriptions.add(subscription)

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

    def _unsubscribe_callback(self, subscription: LcmSubscription) -> None:
        with self._subscriptions_mutex:
            self._subscriptions.discard(subscription)

    def _handle_subscriptions_thread(self) -> None:
        sel = DefaultSelector()
        sel.register(self._sock, EVENT_READ, self._read_lcm_msg)

        with suppress(ConnectionError, OSError):
            while self.is_connected():
                events = sel.select(timeout=1)
                for key, mask in events:
                    callback = key.data
                    callback(key.fileobj, mask)

        self.disconnect()

    def _process_lcm_msg(self, lcm_msg: LcmMessage | None) -> None:
        if lcm_msg is None:
            return

        with self._subscriptions_mutex:
            for subscription in self._subscriptions:
                subscription.receive(lcm_msg.channel, lcm_msg.data)

    def _read_small_payload(self, data: bytes) -> LcmMessage | None:  # noqa: PLR6301
        channel = data.split(b"\x00")[0].decode("ascii")
        data = data[len(channel) + 1 :]

        return LcmMessage(channel, data)

    def _read_large_payload_fragment(
        self, data: bytes, source_address: tuple[str, int]
    ) -> LcmMessage | None:
        (
            sequence_number,
            _data_length,
            _fragment_offset,
            fragment_number,
            fragments_in_msg,
        ) = struct.unpack(">IIIHH", data[:16])
        payload = data[16:]

        buffer_key = hash((sequence_number, source_address))
        fragment_buffer = self._fragment_buffers.get(buffer_key, None)

        if fragment_number == 0:
            channel = payload.split(b"\x00")[0]
            payload = payload[len(channel) + 1 :]

            fragment_buffer = LcmFragmentBuffer(
                source_address=source_address,
                sequence_number=sequence_number,
                fragments_remaining=fragments_in_msg,
                channel=channel.decode("ascii"),
                current_fragment_number=fragment_number,
                data=b"",
            )

            self._fragment_buffers[buffer_key] = fragment_buffer
        if (
            fragment_buffer is None
            or fragment_buffer.sequence_number != sequence_number
            or fragment_buffer.current_fragment_number != fragment_number
        ):
            return None

        fragment_buffer.data += payload
        fragment_buffer.fragments_remaining -= 1
        fragment_buffer.current_fragment_number += 1

        if fragment_buffer.fragments_remaining == 0:
            del self._fragment_buffers[buffer_key]

            return LcmMessage(fragment_buffer.channel, fragment_buffer.data)

        return None

    def _read_lcm_msg(self, _sock: socket, _mask: int) -> None:
        if not self.is_connected():
            return

        data, _, _, source_address = self._sock.recvmsg(65_535)

        if data[:4] == MAGIC_SHORT:
            # drop sequence number since unused in this case
            self._process_lcm_msg(self._read_small_payload(data[8:]))
        elif data[:4] == MAGIC_LONG:
            self._process_lcm_msg(
                self._read_large_payload_fragment(data[4:], source_address)
            )

    def _publish_small_payload(self, payload: bytes) -> None:
        self._sock.sendto(
            MAGIC_SHORT
            + self._sequence_number.to_bytes(4, "big", signed=False)
            + payload,
            self._destination_address,
        )

    def _publish_large_payload(self, encoded_channel: bytes, data: bytes) -> None:
        payload_length = len(encoded_channel) + len(data)

        fragment_count = payload_length // FRAGMENTATION_THRESHOLD + min(
            payload_length % FRAGMENTATION_THRESHOLD, 1
        )

        if fragment_count > 65_535:  # noqa: PLR2004
            raise ValueError("Payload is too large for a single lcm message.")

        fragment_offset = 0
        for fragment_idx in range(fragment_count):
            to_publish = b""

            if fragment_idx == 0:
                to_publish += encoded_channel
                fragment_length = FRAGMENTATION_THRESHOLD - len(encoded_channel)
            else:
                fragment_length = min(
                    FRAGMENTATION_THRESHOLD, len(data) - fragment_offset
                )

            to_publish += data[fragment_offset : fragment_offset + fragment_length]

            self._sock.sendto(
                MAGIC_LONG
                + self._sequence_number.to_bytes(4, "big", signed=False)
                + len(data).to_bytes(4, "big", signed=False)
                + fragment_offset.to_bytes(4, "big", signed=False)
                + fragment_idx.to_bytes(2, "big", signed=False)
                + fragment_count.to_bytes(2, "big", signed=False)
                + to_publish,
                self._destination_address,
            )

            fragment_offset += fragment_length


class LcmUdpmProvider(LcmProvider):
    @override
    def __init__(self) -> None:
        self._provider_name = PROVIDER_NAME

    @override
    def connect(self, url: str) -> LcmUdpmConnection:
        parsed_url = urlparse(url)

        if parsed_url.scheme != self._provider_name:
            raise ValueError(
                f"Passed url contains invalid provider. Expected {self._provider_name}"
                f", got {parsed_url.scheme}."
            )

        return LcmUdpmConnection(url)
