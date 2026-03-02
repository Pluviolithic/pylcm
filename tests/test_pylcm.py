import pytest
from typing_extensions import override

from plcm import Lcm, LcmConnection, LcmProvider


class BogusProvider(LcmProvider):
    @override
    def __init__(self) -> None:
        return

    @override
    def connect(self, url: str) -> LcmConnection:
        raise RuntimeError("Bogus runtime error.")


def test_invalid_provider() -> None:
    plc = Lcm()

    # In Python3.10, 127.0.0.1 gets parsed as the `scheme` value,
    # which is not the case in 3.11+. When Python3.10 reaches
    # EOL, support can be dropped for this and the test made
    # more precise / correct.
    with pytest.raises((ValueError, RuntimeError), match="provider"):
        plc.connect("127.0.0.1:7700")

    with pytest.raises(RuntimeError, match="No bogus provider is registered"):
        plc.connect("bogus://")


def test_register_provider() -> None:
    plc = Lcm()
    plc.register_provider("bogus", BogusProvider)

    with pytest.raises(RuntimeError, match="Bogus runtime error"):
        plc.connect("bogus://")

    with pytest.raises(ValueError, match="Provider already exists"):
        plc.register_provider("bogus", BogusProvider)

    plc.register_provider("bogus", BogusProvider, override_existing=True)
