from amas.agent import Agent

from flkl.bhv.share import Flkl


def show_progress(trial: int, iti: float, modality: int, vhz: float, ahz: float):
    mod = ["Sync", "Async", "Visual", "Audio"][modality]
    print(f"Trial: {trial}    ITI: {iti}    Modality: {mod}    Vhz: {vhz}    Ahz: {ahz}")


async def flickr_discrimination(agent: Agent, ino: Flkl, expvars: dict):
    from itertools import product

    from amas.agent import NotWorkingError
    from numpy import arange
    from numpy.random import uniform
    from utex.agent import AgentAddress
    from utex.scheduler import (SessionMarker, TrialIterator,
                                blockwise_shuffle2, mix, mixn, repeat)

    from flkl.bhv.share import as_millis, flush_message_for

    reward_pin = expvars.get("reward-pin", 4)
    audio_pin = expvars.get("speaker-pin", 2)
    visual_pin = expvars.get("led-pin", 3)
    ir_pin = expvars.get("ir-pin", 5)

    reward_duration = expvars.get("reward-duration", 0.01)
    flickr_duration = expvars.get("flickr-duration", 2.)
    stamp_duration = as_millis(0.05)
    initial_stamp_duration = as_millis(0.1)
    last_stamp_duration = as_millis(0.2)

    reward_duration_millis = as_millis(reward_duration)
    flickr_duration_millis = as_millis(flickr_duration)

    dummy_flickr = [0]
    flickr_async_test = expvars.get("test-frequency", 9)
    flickr_sync_rwd = expvars.get("rewarded-frequency", [12, 14])
    flickr_sync_ext = expvars.get("extinction-frequency", [4, 6, 9])

    flickr_sync = mix(
        flickr_sync_rwd,
        flickr_sync_ext,
        expvars.get("reward-ratio", 3),
        expvars.get("extinction-ratio", 2)
    )
    flickr_visual = flickr_sync
    flickr_audio = expvars.get("audio-frequency", [4, 9, 14])

    flickr_async = [tuple(flickr) for flickr in expvars.get("async-flickrs", [[9, 1], [9, 4], [9, 14], [9, 17]])]
    flickr_sync = list(zip(flickr_sync, flickr_sync))
    flickr_visual = list(product(flickr_visual, dummy_flickr))
    flickr_audio = list(product(dummy_flickr, flickr_audio))

    flickrs = mixn(
        [flickr_sync, flickr_async, flickr_visual, flickr_audio],
        [
            expvars.get("sync-ratio", 1),
            expvars.get("async-ratio", 2),
            expvars.get("visual-ratio", 1),
            expvars.get("audio-ratio", 2),
        ]
    )

    modalities = mixn([[0], [1], [2], [3]],
                      [
                          len(flickr_sync) * expvars.get("sync-ratio", 1),
                          len(flickr_async) * expvars.get("async-ratio", 2),
                          len(flickr_visual) * expvars.get("visual-ratio", 1),
                          len(flickr_audio) * expvars.get("audio-ratio", 2)
                      ]
    )

    iti_mean = expvars.get("ITI", 7.0)
    iti_range = expvars.get("ITI-range", 3.0)
    trials_per_stim = expvars.get("trials-per-stimulus", 10)

    flickr_per_trial, modality_per_trial = blockwise_shuffle2(
        repeat(flickrs, trials_per_stim),
        repeat(modalities, trials_per_stim),
        len(flickrs)
    )

    trials = TrialIterator(modality_per_trial, flickr_per_trial)

    try:
        while agent.working():
            ino.high_for(ir_pin, initial_stamp_duration)
            for i, modality, flickr in trials:
                vhz, ahz = flickr
                iti = uniform(iti_mean - iti_range, iti_mean + iti_range)
                show_progress(i, iti, modality, vhz, ahz)
                await flush_message_for(agent, iti)
                if modality == 0 or modality == 1:
                    if vhz in flickr_sync_rwd:
                        ino.flick_for2(visual_pin, audio_pin, vhz, ahz, flickr_duration_millis, reward_pin, reward_duration_millis)
                    else:
                        ino.flick_for2(visual_pin, audio_pin, vhz, ahz, flickr_duration_millis, 0, reward_duration_millis)
                elif modality == 2:
                    if vhz in flickr_sync_rwd:
                        ino.flick_for(visual_pin, vhz, flickr_duration_millis, reward_pin, reward_duration_millis)
                    else:
                        ino.flick_for(visual_pin, vhz, flickr_duration_millis, 0, reward_duration_millis)
                else:
                    ino.flick_for(audio_pin, ahz, flickr_duration_millis, 0, reward_duration_millis)
                await agent.sleep(flickr_duration + reward_duration)
                ino.high_for(ir_pin, stamp_duration)
            await agent.sleep(1.)
            ino.high_for(ir_pin, last_stamp_duration)
            agent.send_to(AgentAddress.OBSERVER.value, SessionMarker.NEND)
            agent.finish()
    except NotWorkingError:
        pass


def main():
    import argparse
    from datetime import datetime
    from os import mkdir
    from os.path import exists, join
    from typing import Optional

    import yaml
    from amas.agent import Agent
    from amas.connection import Register
    from amas.env import Environment
    from pyno.com import check_connected_board_info
    from pyno.ino import (ArduinoConnecter, ArduinoLineReader, ArduinoSetting,
                          Mode, PinMode)
    from utex.agent import AgentAddress, Observer, Recorder, self_terminate
    from utex.clap import Config
    from utex.fs import get_current_file_abspath, namefile
    from utex.scheduler import SessionMarker


    parser = argparse.ArgumentParser(description="Run the flickr discrimination task.")
    parser.add_argument("subject", help="Subject ID")
    parser.add_argument("yaml", help="Path to YAML config file")
    args = parser.parse_args()

    subject = args.subject
    yaml_path = args.yaml

    with open(yaml_path, "r") as f:
        config_data = yaml.safe_load(f)

    log_dir = "./log"
    if not exists(log_dir):
        mkdir(log_dir)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    log_filename = f"{subject}-{timestamp}.yaml"
    log_path = join(log_dir, log_filename)

    with open(log_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)

    config = Config(log_path)
    com_output_config: Optional[dict] = config.comport.get("output")
    if com_output_config is None:
        raise ValueError("`com_output_config` are not defined.")
    com_output_config.update({"mode": Mode.user})

    if com_output_config is None:
        raise Exception()

    available_boards = check_connected_board_info()

    if len(available_boards) == 0:
        raise RuntimeError("No Arduino boards were detected. Please check the connection and try again.")
    elif len(available_boards) > 1:
        raise RuntimeError("Multiple Arduino boards were detected. Please connect only one board and try again.")

    board = available_boards[0]

    setting = ArduinoSetting.derive_from_portinfo(board)
    setting.apply_setting(com_output_config)
    serial_number = com_output_config.get("serial-number")
    print(f"Uploading sketch to controller arduino {serial_number}")
    ArduinoConnecter(setting).write_sketch()
    flkl = Flkl(ArduinoConnecter(setting).connect())
    [flkl.pin_mode(i, PinMode.OUTPUT) for i in range(0, 14)]

    controller = (
        Agent("CONTROLLER")
        .assign_task(flickr_discrimination, ino=flkl, expvars=config.experimental)
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
