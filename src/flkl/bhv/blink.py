from amas.agent import Agent

from flkl.bhv.share import Flkl


async def blink_pin(
    agent: Agent,
    flkl: Flkl,
    n_blinks: int,
    interval: float,
    duration: float,
    pin: int,
):
    from amas.agent import NotWorkingError
    from utex.agent import AgentAddress
    from utex.scheduler import SessionMarker

    from flkl.bhv.share import as_millis

    duration_millis = as_millis(duration)

    try:
        for blink_index in range(n_blinks):
            if not agent.working():
                break

            print(f"Blink = {blink_index + 1} / {n_blinks}")

            await agent.sleep(interval)
            flkl.high_for(pin, duration_millis)
            await agent.sleep(duration)

        agent.send_to(AgentAddress.OBSERVER.value, SessionMarker.NEND)
        agent.finish()

    except NotWorkingError:
        pass


def main():
    import argparse

    from amas.connection import Register
    from amas.env import Environment
    from pyno.com import check_connected_board_info
    from pyno.ino import ArduinoConnecter, ArduinoSetting, Mode, PinMode
    from utex.agent import Observer, self_terminate
    from utex.scheduler import SessionMarker

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--pin",
        "-p",
        default=4,
        type=int,
        help="Output pin to blink",
    )
    parser.add_argument(
        "--duration",
        "-d",
        required=True,
        type=float,
        help="Duration of each blink in seconds",
    )
    parser.add_argument(
        "--interval",
        "-i",
        required=True,
        type=float,
        help="Interval before each blink in seconds",
    )
    parser.add_argument(
        "--number-of-blinks",
        "--number-of-blink",
        "-n",
        dest="number_of_blinks",
        required=True,
        type=int,
        help="Number of pin blinks",
    )

    args = parser.parse_args()

    available_boards = check_connected_board_info()

    if len(available_boards) == 0:
        raise RuntimeError(
            "No Arduino boards were detected. Please check the connection and try again."
        )
    elif len(available_boards) > 1:
        raise RuntimeError(
            "Multiple Arduino boards were detected. Please connect only one board and try again."
        )

    board = available_boards[0]

    setting = ArduinoSetting.derive_from_portinfo(board)
    setting.apply_setting(
        {
            "baudrate": 115200,
            "mode": Mode.user,
            "sketch": "./ino",
        }
    )

    connector = ArduinoConnecter(setting)
    connector.write_sketch()

    flkl = Flkl(connector.connect())

    for output_pin in range(0, 14):
        flkl.pin_mode(output_pin, PinMode.OUTPUT)

    controller = (
        Agent("CONTROLLER")
        .assign_task(
            blink_pin,
            flkl=flkl,
            n_blinks=args.number_of_blinks,
            interval=args.interval,
            duration=args.duration,
            pin=args.pin,
        )
        .assign_task(self_terminate)
    )

    observer = Observer()

    agents = [controller, observer]
    register = Register(agents)
    env = Environment(agents)

    try:
        env.run()
    except KeyboardInterrupt:
        observer.send_all(SessionMarker.ABEND)
        observer.finish()


if __name__ == "__main__":
    main()
