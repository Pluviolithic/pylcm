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

    with pytest.raises(ValueError, match="No provider declared"):
        plc.connect("127.0.0.1:7700")

    with pytest.raises(RuntimeError, match="No bogus provider is registered"):
        plc.connect("bogus://")


def test_register_provider() -> None:
    plc = Lcm()
    plc.register_provider("bogus", BogusProvider)

    assert plc.connect("bogus://") is None

    with pytest.raises(ValueError, match="Provider already exists"):
        plc.register_provider("bogus", BogusProvider)

    plc.register_provider("bogus", BogusProvider, override_existing=True)
