from amas.agent import Agent, NotWorkingError
from pyno.ino import ArduinoFlicker, ArduinoLineReader, as_bytes


DEFAULT_FLICKR_ON_RATIO = 0.28


def equal_on_parameters(hz: float, duration_ms: int, on_ratio: float) -> tuple[int, int]:
    """Encode frequency and the total ON budget, with microsecond resolution."""
    from math import isclose, isfinite

    if not isfinite(hz) or not 0.1 <= hz <= 25.5:
        raise ValueError("Flicker frequency must be between 0.1 and 25.5 Hz.")
    frequency = round(hz * 10)
    if not isclose(hz * 10, frequency, rel_tol=0, abs_tol=1e-7):
        raise ValueError("Flicker frequency must be a multiple of 0.1 Hz.")
    if not isinstance(duration_ms, int) or not 1 <= duration_ms <= 65535:
        raise ValueError("Flicker duration must be 1..65535 milliseconds.")
    if not isfinite(on_ratio) or not 0 < on_ratio < 1:
        raise ValueError("flickr-on-ratio must be greater than 0 and less than 1.")
    total_on_us = round(duration_ms * 1000 * on_ratio)
    if not 0 < total_on_us < duration_ms * 1000:
        raise ValueError("The total ON and OFF durations must each be at least 1 microsecond.")
    return frequency, total_on_us


class Flkl(ArduinoFlicker):
    from pyno.ino import ArduinoConnecter

    def __init__(self, connecter: ArduinoConnecter):
        super().__init__(connecter)

    def flick_for(self, pin: int, hz: float, flickr_duration: int, rpin: int, millis: int, pulse_duration: int = 20, *, on_ratio: float | None = None):
        if on_ratio is not None:
            frequency, total_on_us = equal_on_parameters(hz, flickr_duration, on_ratio)
            message = (b"\x18"
                + as_bytes(pin, 1)
                + as_bytes(frequency, 1)
                + as_bytes(flickr_duration, 2)
                + as_bytes(total_on_us, 4)
                + as_bytes(rpin, 1)
                + as_bytes(millis, 2)
            )
            self.connection.write(message)
            return
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

    def flick_for2(self, pin1: int, pin2: int, hz1: float, hz2: float, flickr_duration: int, rpin: int, millis: int, pulse_duration: int = 20, *, on_ratio: float | None = None):
        if on_ratio is not None:
            frequency1, total_on_us = equal_on_parameters(hz1, flickr_duration, on_ratio)
            frequency2, _ = equal_on_parameters(hz2, flickr_duration, on_ratio)
            message = (b"\x1a"
                + as_bytes(pin1, 1)
                + as_bytes(pin2, 1)
                + as_bytes(frequency1, 1)
                + as_bytes(frequency2, 1)
                + as_bytes(flickr_duration, 2)
                + as_bytes(total_on_us, 4)
                + as_bytes(rpin, 1)
                + as_bytes(millis, 2)
            )
            self.connection.write(message)
            return
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
