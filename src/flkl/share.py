from amas.agent import Agent, NotWorkingError
from pyno.ino import ArduinoFlicker, ArduinoLineReader, as_bytes


class Flkl(ArduinoFlicker):
    from pyno.ino import ArduinoConnecter

    def __init__(self, connecter: ArduinoConnecter):
        super().__init__(connecter)

    def flick_for(self, pin: int, hz: float, flickr_duration: int, rpin: int, millis: int, pulse_duration: int = 20):
        hz = int(hz * 10)
        message = (b"\x13"
            + as_bytes(pin, 1)
            + as_bytes(hz, 1)
            + as_bytes(flickr_duration, 2)
            + as_bytes(pulse_duration, 2)
            + as_bytes(rpin, 1)
            + as_bytes(millis, 2)
        )
        self.connection.write(message)

    def flick_on(self, pin: int, hz: float, flickr_duration: int, pulse_duration: int = 20):
        hz = int(hz * 10)
        message = b"\x14" + as_bytes(pin, 1) + as_bytes(hz, 1) + as_bytes(flickr_duration, 2) + as_bytes(pulse_duration, 2)
        self.connection.write(message)

    def flick_for2(self, pin1: int, pin2: int, hz1: float, hz2: float, flickr_duration: int, rpin: int, millis: int, pulse_duration: int = 20):
        hz1 = int(hz1 * 10)
        hz2 = int(hz2 * 10)
        message = (
            b"\x15"
            + as_bytes(pin1, 1)
            + as_bytes(pin2, 1)
            + as_bytes(hz1, 1)
            + as_bytes(hz2, 1)
            + as_bytes(flickr_duration, 2)
            + as_bytes(pulse_duration, 2)
            + as_bytes(rpin, 1)
            + as_bytes(millis, 2)
        )
        self.connection.write(message)

    def flick_on2(self, pin1: int, pin2: int, hz1: float, hz2: float, flickr_duration: int, pulse_duration: int = 20):
        hz1 = int(hz1 * 10)
        hz2 = int(hz2 * 10)
        message = (
            b"\x16"
            + as_bytes(pin1, 1)
            + as_bytes(pin2, 1)
            + as_bytes(hz1, 1)
            + as_bytes(hz2, 1)
            + as_bytes(flickr_duration, 2)
            + as_bytes(pulse_duration, 2)
        )
        self.connection.write(message)

    def high_for(self, pin: int, millis: int):
        message = b"\x17" + as_bytes(pin, 1) + as_bytes(millis, 2)
        self.connection.write(message)


def as_millis(s: float) -> int:
    return int(s * 1000)


async def flush_message_for(agent: Agent, duration: float):
    from time import perf_counter

    while duration >= 0.0 and agent.working():
        s = perf_counter()
        await agent.try_recv(duration)
        e = perf_counter()
        duration -= e - s
