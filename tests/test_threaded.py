from threading import Thread
from time import sleep

from lcm import LCM

from plcm import Lcm, LcmConnection

TEST_URL = "tcpq://127.0.0.1:7700"
TEST_CHANNEL = "test_channel"


def handle_thread(lc: LCM) -> None:
    for _ in range(5_000):
        lc.handle()


def publish_thread(plc: LcmConnection, data: bytes) -> None:
    plc.publish(TEST_CHANNEL, data)


def test_threaded() -> None:
    lc = LCM(TEST_URL)
    plc = Lcm().connect(TEST_URL)

    assert plc is not None

    valid_sum = 12_497_500
    tested_sum = 0

    handle_thread_t = Thread(target=handle_thread, args=(lc,))

    def callback(_channel: str, data: bytes) -> None:
        nonlocal tested_sum
        tested_sum += int.from_bytes(data, "little", signed=False)

    lc.subscribe(TEST_CHANNEL, callback)
    handle_thread_t.start()

    sleep(0.1)

    for idx in range(5_000):
        Thread(
            target=publish_thread, args=(plc, idx.to_bytes(4, "little", signed=False))
        ).start()

    handle_thread_t.join()

    plc.disconnect()

    assert tested_sum == valid_sum
