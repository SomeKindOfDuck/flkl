from amas.agent import Agent

from flkl.bhv.share import DEFAULT_FLICKR_ON_RATIO, Flkl, equal_on_parameters


STIMULUS_KEYS = (
    "visual-rewarded", "visual-non-rewarded", "audio-rewarded", "audio-non-rewarded",
)
LEGACY_STIMULUS_KEYS = (
    "rewarded-frequency", "extinction-frequency", "audio-frequency", "audio-rewarded-frequency",
)


def normalize_stimuli(expvars: dict) -> dict:
    """Return Experimental settings with separate rewarded/non-rewarded lists."""
    from math import isfinite

    def frequencies(key, default=()):
        values = expvars.get(key, list(default))
        if not isinstance(values, list) or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) for value in values
        ):
            raise ValueError(f"{key} must be a list of frequencies in Hz (use [] for none).")
        return list(values)

    has_new = any(key in expvars for key in STIMULUS_KEYS)
    has_legacy = any(key in expvars for key in LEGACY_STIMULUS_KEYS)
    if has_new and has_legacy:
        raise ValueError(
            "Do not mix visual-rewarded/visual-non-rewarded/audio-rewarded/audio-non-rewarded "
            "with the old *-frequency stimulus settings."
        )
    if has_legacy:
        visual_rewarded = frequencies("rewarded-frequency", [12, 14, 16])
        visual_non_rewarded = frequencies("extinction-frequency", [6, 8, 10])
        audio = frequencies("audio-frequency", [2, 9, 11, 13, 20])
        audio_rewarded = frequencies("audio-rewarded-frequency")
        if any(hz not in audio for hz in audio_rewarded):
            raise ValueError("audio-rewarded-frequency must be included in audio-frequency.")
        # Preserve the frequencies and their multiplicity within each class.
        audio_rewarded = [hz for hz in audio if hz in audio_rewarded]
        audio_non_rewarded = [hz for hz in audio if hz not in audio_rewarded]
        lists = (visual_rewarded, visual_non_rewarded, audio_rewarded, audio_non_rewarded)
    else:
        lists = tuple(frequencies(key) for key in STIMULUS_KEYS)

    for modality, rewarded, non_rewarded in (
        ("visual", lists[0], lists[1]), ("audio", lists[2], lists[3]),
    ):
        if set(rewarded) & set(non_rewarded):
            raise ValueError(
                f"{modality}-rewarded and {modality}-non-rewarded must not contain the same Hz."
            )

    result = dict(expvars)
    for key in LEGACY_STIMULUS_KEYS:
        result.pop(key, None)
    result.update(zip(STIMULUS_KEYS, lists))
    return result


def show_progress(trial: int, iti: float, modality: int, freq: float):
    mod = ["Visual-Audio", "Visual", "Audio"][modality]
    print(f"Trial: {trial}    ITI: {iti}    Modality: {mod}    Frequency: {freq}")


async def flickr_discrimination(agent: Agent, ino: Flkl, expvars: dict, log_path: str):
    import yaml

    from amas.agent import NotWorkingError
    from numpy import arange
    from numpy.random import uniform
    from utex.agent import AgentAddress
    from utex.scheduler import (SessionMarker, TrialIterator,
                                blockwise_shuffle2, mix, mixn, repeat)

    from flkl.bhv.share import as_millis, flush_message_for

    expvars = normalize_stimuli(expvars)

    reward_pin = expvars.get("reward-pin", 4)
    audio_pin = expvars.get("speaker-pin", 2)
    visual_pin = expvars.get("led-pin", 3)
    ir_pin = expvars.get("ir-pin", 5)

    reward_duration = expvars.get("reward-duration", 0.01)
    flickr_duration = expvars.get("flickr-duration", 2.)
    flickr_on_ratio = expvars.get("flickr-on-ratio", DEFAULT_FLICKR_ON_RATIO)
    stamp_duration = as_millis(0.05)
    initial_stamp_duration = as_millis(0.1)
    last_stamp_duration = as_millis(0.2)

    reward_duration_millis = as_millis(reward_duration)
    flickr_duration_millis = as_millis(flickr_duration)

    flickr_sync_rwd = expvars["visual-rewarded"]
    flickr_sync_ext = expvars["visual-non-rewarded"]
    flickr_sync = mix(
        flickr_sync_rwd,
        flickr_sync_ext,
        expvars.get("reward-ratio", 1),
        expvars.get("extinction-ratio", 1)
    )
    flickr_visual = flickr_sync
    flickr_audio_rwd = expvars["audio-rewarded"]
    flickr_audio = flickr_audio_rwd + expvars["audio-non-rewarded"]
    flickrs = mixn(
        [flickr_sync, flickr_visual, flickr_audio],
        [
            expvars.get("sync-ratio", 1),
            expvars.get("visual-ratio", 1),
            expvars.get("audio-ratio", 1),
        ]
    )

    if not flickrs:
        raise ValueError("No training stimuli are enabled. Check the four stimulus lists and modality ratios.")

    for frequency in set(flickrs):
        equal_on_parameters(frequency, flickr_duration_millis, flickr_on_ratio)

    modalities = mixn([[0], [1], [2]],
                      [
                          len(flickr_sync) * expvars.get("sync-ratio", 1),
                          len(flickr_visual) * expvars.get("visual-ratio", 1),
                          len(flickr_audio) * expvars.get("audio-ratio", 1)
                      ]
    )

    iti_mean = expvars.get("ITI", 15.0)
    iti_range = expvars.get("ITI-range", 5.0)
    trials_per_stim = expvars.get("trials-per-stimulus", 20)
    if isinstance(trials_per_stim, bool) or not isinstance(trials_per_stim, int) or trials_per_stim < 1:
        raise ValueError("trials-per-stimulus must be a positive integer.")

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
                iti = uniform(iti_mean - iti_range, iti_mean + iti_range)
                show_progress(i, iti, modality, flickr)
                await flush_message_for(agent, iti)
                if modality == 0:
                    if flickr in flickr_sync_rwd:
                        ino.flick_for2(visual_pin, audio_pin, flickr, flickr, flickr_duration_millis, reward_pin, reward_duration_millis, on_ratio=flickr_on_ratio)
                    else:
                        ino.flick_for2(visual_pin, audio_pin, flickr, flickr, flickr_duration_millis, 0, reward_duration_millis, on_ratio=flickr_on_ratio)
                elif modality == 1:
                    if flickr in flickr_sync_rwd:
                        ino.flick_for(visual_pin, flickr, flickr_duration_millis, reward_pin, reward_duration_millis, on_ratio=flickr_on_ratio)
                    else:
                        ino.flick_for(visual_pin, flickr, flickr_duration_millis, 0, reward_duration_millis, on_ratio=flickr_on_ratio)
                else:
                    audio_reward_pin = reward_pin if flickr in flickr_audio_rwd else 0
                    ino.flick_for(audio_pin, flickr, flickr_duration_millis, audio_reward_pin, reward_duration_millis, on_ratio=flickr_on_ratio)
                await agent.sleep(flickr_duration + reward_duration)
                ino.high_for(ir_pin, stamp_duration)
            await agent.sleep(1.)
            ino.high_for(ir_pin, last_stamp_duration)

            with open(log_path, "r") as f:
                final_config = yaml.safe_load(f)
            final_config["Experimental"]["finished"] = True
            with open(log_path, "w") as f:
                yaml.dump(final_config, f, default_flow_style=False)

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
    config_data["Experimental"] = normalize_stimuli(config_data.get("Experimental", {}))
    config_data["Experimental"]["finished"] = False
    config_data["Experimental"].setdefault("flickr-on-ratio", DEFAULT_FLICKR_ON_RATIO)

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
        .assign_task(flickr_discrimination, ino=flkl, expvars=config.experimental, log_path=log_path)
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
