# pylcm

This project is a pure-python implementation of
[lcm](https://github.com/lcm-proj/lcm)'s netcode. It is not a drop-in
replacement. Instead, it provides alternative and (ideally) more Pythonic
interfaces. However, it is meant to be interoperable with any other lcm client
over the network.

Over time, some of the tools like lcmgen or lcm-spy may be reimplemented here
in Python, but the primary focus is on the netcode and idiomatic implementations
of that netcode.

# installation

The `plcm` package is available for installation using
[pip](https://pypi.org/project/pip/) or your favorite package manager:

```sh
pip3 install plcm
```

# usage

```py
from plcm import Lcm

def callback(channel: str, data: bytes) -> None:
    print(channel, data)

connection = Lcm().connect("tcpq://")
subscription = connection.subscribe("channelname", callback)

...

connection.publish("channelname", b"\x00\x00\x00\x00")

...

subscription.unsubscribe()
connection.publish("channelname", b"\x00\x00\x00\x00")

...

connection.disconnect()
```
