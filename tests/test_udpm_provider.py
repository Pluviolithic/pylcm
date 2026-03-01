from random import randbytes, randint
from threading import Thread
from time import sleep

import pytest
from lcm import LCM

from plcm import Lcm, LcmTcpqProvider

TEST_URL = "udpm://239.255.76.67:7667?ttl=1"
TEST_CHANNEL = "test_channel"


def handle_thread(lc: LCM) -> None:
    for _ in range(100):
        lc.handle()


def test_pylcm_publish_lcm_subscribe() -> None:
    lc = LCM(TEST_URL)
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    valid_sum = 0
    tested_sum = 0

    handle_thread_t = Thread(target=handle_thread, args=(lc,))

    def callback(_channel: str, data: bytes) -> None:
        nonlocal tested_sum
        tested_sum += int.from_bytes(data, "little", signed=False)

    lc.subscribe(TEST_CHANNEL, callback)
    handle_thread_t.start()

    # need a yield for lcm.LCM's subscribe to complete
    sleep(0.1)

    for _ in range(100):
        random_int = randint(0, 1_000)
        valid_sum += random_int
        plc.publish("test_channel", random_int.to_bytes(4, "little", signed=False))

    plc.disconnect()
    handle_thread_t.join()

    assert tested_sum == valid_sum


def test_lcm_publish_pylcm_subscribe() -> None:
    lc = LCM(TEST_URL)
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    valid_sum = 0
    tested_sum = 0

    def callback(_channel: str, data: bytes) -> None:
        nonlocal tested_sum
        tested_sum += int.from_bytes(data, "little", signed=False)

    subscription = plc.subscribe(TEST_CHANNEL, callback)
    assert subscription is not None

    for _ in range(100):
        random_int = randint(0, 1_000)
        valid_sum += random_int
        lc.publish(TEST_CHANNEL, random_int.to_bytes(4, "little", signed=False))

    sleep(0.1)

    plc.disconnect()

    assert tested_sum == valid_sum


def test_pylcm_publish_pylcm_subscribe() -> None:
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    valid_sum = 0
    tested_sum = 0

    def callback(_channel: str, data: bytes) -> None:
        nonlocal tested_sum
        tested_sum += int.from_bytes(data, "little", signed=False)

    subscription = plc.subscribe(TEST_CHANNEL, callback)
    assert subscription is not None

    for _ in range(100):
        random_int = randint(0, 1_000)
        valid_sum += random_int
        plc.publish(TEST_CHANNEL, random_int.to_bytes(4, "little", signed=False))

    sleep(0.1)

    plc.disconnect()

    assert tested_sum == valid_sum


def test_pylcm_unsubscribe() -> None:
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    valid_sum = 0
    tested_sum = 0

    def callback(_channel: str, data: bytes) -> None:
        nonlocal tested_sum
        tested_sum += int.from_bytes(data, "little", signed=False)

    subscription = plc.subscribe(TEST_CHANNEL, callback)
    assert subscription is not None
    assert subscription.is_active()

    for _ in range(100):
        random_int = randint(0, 1_000)
        valid_sum += random_int
        plc.publish(TEST_CHANNEL, random_int.to_bytes(4, "little", signed=False))

    sleep(0.1)

    subscription.unsubscribe()

    sleep(0.1)

    for _ in range(100):
        plc.publish(TEST_CHANNEL, randint(1, 1_000).to_bytes(4, "little", signed=False))

    sleep(0.1)

    assert not subscription.is_active()

    plc.disconnect()

    assert tested_sum == valid_sum


def test_plcm_not_subscribed() -> None:
    lc = LCM(TEST_URL)
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    valid_value = 0
    tested_value = valid_value

    def callback(_channel: str, _data: bytes) -> None:
        nonlocal tested_value
        tested_value += 1

    plc.subscribe(TEST_CHANNEL + "bogus", callback)

    sleep(0.1)

    lc.publish(TEST_CHANNEL, b"\x00\x00\x00\x00")

    sleep(0.1)

    plc.disconnect()

    assert tested_value == valid_value


def test_get_channel() -> None:
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    subscription = plc.subscribe(TEST_CHANNEL, print)

    assert subscription is not None
    assert subscription.get_channel() == TEST_CHANNEL

    plc.disconnect()


def test_invalid_connect_call() -> None:
    provider = LcmTcpqProvider()

    with pytest.raises(ValueError, match="Expected tcpq, got bogus"):
        provider.connect("bogus://")


def test_invalid_usage() -> None:
    plc = Lcm().connect(TEST_URL)

    def callback(_channel: str, _data: bytes) -> None:
        return

    assert plc is not None

    subscription = plc.subscribe(TEST_CHANNEL, callback)

    assert subscription is not None

    for _ in range(5):
        subscription.unsubscribe()

    for _ in range(5):
        plc.disconnect()

    assert plc.subscribe(TEST_CHANNEL, callback) is None

    with pytest.raises(RuntimeError, match="Lcm not connected"):
        plc.publish(TEST_CHANNEL, b"\x00\x00\x00\x00")


def test_pylcm_publish_large_payload() -> None:
    lc = LCM(TEST_URL)
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    large_payload = randbytes(1_000_000)
    received_payload_a = None
    received_payload_b = None

    handle_thread_t = Thread(target=handle_thread, args=(lc,))

    def callback_a(_channel: str, data: bytes) -> None:
        nonlocal received_payload_a
        received_payload_a = data

    def callback_b(_channel: str, data: bytes) -> None:
        nonlocal received_payload_b
        received_payload_b = data

    lc.subscribe(TEST_CHANNEL, callback_a)
    plc.subscribe(TEST_CHANNEL, callback_b)
    handle_thread_t.start()

    # need a yield for lcm.LCM's subscribe to complete
    sleep(0.1)

    for _ in range(150):
        plc.publish(TEST_CHANNEL, large_payload)

    sleep(0.1)

    plc.disconnect()

    assert received_payload_a == large_payload
    assert received_payload_b == large_payload


def test_lcm_publish_large_payload() -> None:
    lc = LCM(TEST_URL)
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    large_payload = randbytes(1_000_000)
    received_payload = None

    def callback(_channel: str, data: bytes) -> None:
        nonlocal received_payload
        received_payload = data

    plc.subscribe(TEST_CHANNEL, callback)

    sleep(0.1)

    for _ in range(100):
        lc.publish(TEST_CHANNEL, large_payload)

    sleep(0.1)

    plc.disconnect()

    assert received_payload == large_payload
