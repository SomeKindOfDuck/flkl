import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from flkl.bhv import share, test as test_task, train


ROOT = Path(__file__).resolve().parents[1]


class SerialCapture:
    def __init__(self):
        self.packets = []

    def write(self, packet):
        self.packets.append(packet)
        return len(packet)


class FakeAgent:
    def __init__(self):
        self.active = True
        self.messages = []

    def working(self):
        return self.active

    async def sleep(self, duration):
        pass

    def send_to(self, address, message):
        self.messages.append((address, message.name))

    def finish(self):
        self.active = False


class EqualOnTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="flkl-waveform-")
        cls.addClassCleanup(cls.temp.cleanup)
        if shutil.which("g++") is None:
            raise RuntimeError("g++ is required for firmware waveform tests")
        cls.firmware = Path(cls.temp.name) / "firmware_sim"
        subprocess.run(
            ["g++", "-std=c++11", "-O2", str(ROOT / "tests/firmware_sim.cpp"), "-o", str(cls.firmware)],
            check=True, capture_output=True, text=True,
        )

    def setUp(self):
        self.serial = SerialCapture()
        self.ino = share.Flkl(SimpleNamespace(connection=self.serial))

    def waveform(self, packet, start=0):
        result = subprocess.run(
            [str(self.firmware), packet.hex(), str(start)],
            check=True, capture_output=True, text=True, timeout=10,
        )
        rising, pulses = {}, {}
        for line in result.stdout.splitlines():
            pin, time, high = map(int, line.split())
            if high:
                self.assertNotIn(pin, rising)
                rising[pin] = time
            else:
                pulses.setdefault(pin, []).append((rising.pop(pin), time))
        self.assertEqual(rising, {}, "All pins must finish LOW")
        return pulses

    def assert_on_budget(self, pulses, budget):
        total = sum(end - start for start, end in pulses)
        # A simulated micros() tick is 4 us; each edge can round to a tick.
        self.assertLessEqual(abs(total - budget), 8 * len(pulses))

    def test_exact_plans_include_partial_periods_and_wire_frequency_limits(self):
        result = subprocess.run(
            [str(self.firmware), "--check-plans"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        self.assertIn("exact ON-budget plans passed", result.stdout)

    def test_total_on_time_and_frequency_for_single_output(self):
        for ratio in (0.28, 0.5):
            for hz in (1, 2, 3, 4, 6, 9, 11, 12, 14, 15, 17, 20, 25.5):
                with self.subTest(ratio=ratio, hz=hz):
                    self.ino.flick_for(3, hz, 2000, 4, 10, on_ratio=ratio)
                    pulses = self.waveform(self.serial.packets[-1])
                    self.assertEqual(len(pulses[3]), int(2 * hz))
                    self.assert_on_budget(pulses[3], round(2000000 * ratio))
                    origin = pulses[3][0][0]
                    for index, (start, end) in enumerate(pulses[3]):
                        self.assertLessEqual(abs(start - origin - index * 1000000 / hz), 4)
                    self.assertEqual(len(pulses[4]), 1)
                    self.assertGreaterEqual(pulses[4][0][0] - origin, 2000000)
                    self.assertAlmostEqual(pulses[4][0][1] - pulses[4][0][0], 10000, delta=4)

    def test_async_outputs_get_the_same_on_budget(self):
        for hz1, hz2 in ((9, 1), (9, 4), (9, 14), (9, 17)):
            with self.subTest(hz1=hz1, hz2=hz2):
                self.ino.flick_for2(3, 2, hz1, hz2, 2000, 0, 10, on_ratio=0.28)
                pulses = self.waveform(self.serial.packets[-1])
                self.assertEqual(set(pulses), {2, 3})
                self.assertEqual(len(pulses[3]), hz1 * 2)
                self.assertEqual(len(pulses[2]), hz2 * 2)
                self.assert_on_budget(pulses[3], 560000)
                self.assert_on_budget(pulses[2], 560000)
                self.assertEqual(pulses[3][0][0], pulses[2][0][0])

    def test_sync_outputs_remain_synchronous(self):
        self.ino.flick_for2(3, 2, 14, 14, 2000, 0, 10, on_ratio=0.28)
        pulses = self.waveform(self.serial.packets[-1])
        self.assertEqual(pulses[3], pulses[2])
        self.assert_on_budget(pulses[3], 560000)

    def test_partial_periods_preserve_total_on_time(self):
        for duration_ms, hz in ((1733, 9), (2150, 14), (49, 20), (1000, 0.1)):
            with self.subTest(duration_ms=duration_ms, hz=hz):
                self.ino.flick_for(3, hz, duration_ms, 0, 10, on_ratio=0.28)
                pulses = self.waveform(self.serial.packets[-1])
                self.assert_on_budget(pulses[3], round(duration_ms * 1000 * 0.28))

    def test_clock_wraparound(self):
        self.ino.flick_for2(3, 2, 14, 9, 2000, 4, 10, on_ratio=0.28)
        pulses = self.waveform(self.serial.packets[-1], start=2**32 - 1000)
        self.assert_on_budget(pulses[3], 560000)
        self.assert_on_budget(pulses[2], 560000)
        self.assertGreaterEqual(pulses[4][0][0] - pulses[3][0][0], 2000000)

    def test_invalid_settings_are_rejected_before_serial_write(self):
        for ratio in (0, 1, -0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                self.ino.flick_for(3, 14, 2000, 0, 10, on_ratio=ratio)
        for hz in (0, -1, 25.6, 9.15, float("nan"), float("inf")):
            with self.subTest(hz=hz), self.assertRaises(ValueError):
                self.ino.flick_for2(3, 2, 9, hz, 2000, 0, 10, on_ratio=0.28)
        self.assertEqual(self.serial.packets, [])

    def test_existing_fixed_width_command_still_works(self):
        self.ino.flick_for(3, 14, 2000, 0, 10)
        self.assertEqual(self.serial.packets[-1][0], 0x13)
        pulses = self.waveform(self.serial.packets[-1])
        self.assertEqual(len(pulses[3]), 28)
        for start, end in pulses[3]:
            self.assertAlmostEqual(end - start, 20000, delta=16)

    def test_task_settings_reach_every_trial(self):
        for module, filename, expected_trials in (
            (train, "train-sample.yaml", 180), (test_task, "test-sample.yaml", 380)
        ):
            for ratio in (None, 0.28, 0.5):
                with self.subTest(task=module.__name__, ratio=ratio):
                    config = yaml.safe_load((ROOT / "config" / filename).read_text())
                    if ratio is None:
                        config["Experimental"].pop("flickr-on-ratio")
                    else:
                        config["Experimental"]["flickr-on-ratio"] = ratio
                    log = Path(self.temp.name) / "task.yaml"
                    log.write_text(yaml.safe_dump(config))
                    self.serial.packets.clear()
                    waits, shown = [], []

                    async def wait(agent, duration):
                        waits.append(duration)

                    args = {"log_path": str(log)} if module is train else {}
                    with patch.object(share, "flush_message_for", wait), patch.object(module, "show_progress", side_effect=lambda *args: shown.append(args)):
                        asyncio.run(module.flickr_discrimination(FakeAgent(), self.ino, config["Experimental"], **args))
                    packets = [p for p in self.serial.packets if p[0] in (0x18, 0x1a)]
                    self.assertEqual(len(packets), expected_trials)
                    budget = round(2000000 * (0.28 if ratio is None else ratio))
                    for packet in packets:
                        offset = 5 if packet[0] == 0x18 else 7
                        self.assertEqual(int.from_bytes(packet[offset:offset+4], "little"), budget)
                    self.assertEqual(waits, [row[1] for row in shown])
                    if module is train:
                        self.assertTrue(yaml.safe_load(log.read_text())["Experimental"]["finished"])

    def test_training_audio_rewards_follow_selected_frequencies(self):
        for rewarded in (None, [], [4, 9], [4, 9, 14]):
            with self.subTest(audio_rewarded=rewarded):
                config = yaml.safe_load((ROOT / "config/train-sample.yaml").read_text())
                exp = config["Experimental"]
                for key in train.STIMULUS_KEYS:
                    exp.pop(key, None)
                exp.update({
                    "rewarded-frequency": [14],
                    "extinction-frequency": [4],
                    "audio-frequency": [4, 9, 14],
                    "trials-per-stimulus": 2,
                    "reward-pin": 6,
                    "reward-duration": 0.025,
                })
                if rewarded is None:
                    exp.pop("audio-rewarded-frequency", None)
                else:
                    exp["audio-rewarded-frequency"] = rewarded
                log = Path(self.temp.name) / "audio-rewards.yaml"
                log.write_text(yaml.safe_dump(config))
                self.serial.packets.clear()

                async def wait(agent, duration):
                    pass

                with patch.object(share, "flush_message_for", wait), patch.object(train, "show_progress"):
                    asyncio.run(train.flickr_discrimination(FakeAgent(), self.ino, exp, str(log)))

                counts = {}
                for packet in self.serial.packets:
                    if packet[0] == 0x1a:
                        condition = ("sync", packet[3] / 10)
                    elif packet[0] == 0x18:
                        condition = ("audio" if packet[1] == 2 else "visual", packet[2] / 10)
                    else:
                        continue
                    counts[condition] = counts.get(condition, 0) + 1
                    hz = condition[1]
                    should_reward = hz in (rewarded or []) if condition[0] == "audio" else hz == 14
                    pulses = self.waveform(packet)
                    if should_reward:
                        self.assertEqual(len(pulses[6]), 1)
                        stimulus_pin = 2 if condition[0] == "audio" else 3
                        self.assertGreaterEqual(pulses[6][0][0] - pulses[stimulus_pin][0][0], 2000000)
                        self.assertAlmostEqual(pulses[6][0][1] - pulses[6][0][0], 25000, delta=4)
                    else:
                        self.assertNotIn(6, pulses)
                self.assertEqual(counts, {
                    ("sync", 4): 2, ("sync", 14): 2,
                    ("visual", 4): 2, ("visual", 14): 2,
                    ("audio", 4): 2, ("audio", 9): 2, ("audio", 14): 2,
                })
                saved = yaml.safe_load(log.read_text())["Experimental"]
                self.assertTrue(saved["finished"])
                if rewarded is not None:
                    self.assertEqual(saved["audio-rewarded-frequency"], rewarded)

    def test_invalid_audio_reward_selection_stops_before_stimuli(self):
        for rewarded in ([20], None, 15, "15"):
            with self.subTest(audio_rewarded=rewarded):
                config = yaml.safe_load((ROOT / "config/train-sample.yaml").read_text())
                for key in train.STIMULUS_KEYS:
                    config["Experimental"].pop(key, None)
                config["Experimental"]["audio-frequency"] = [3, 6, 9, 12, 15]
                config["Experimental"]["audio-rewarded-frequency"] = rewarded
                log = Path(self.temp.name) / "invalid-audio-rewards.yaml"
                log.write_text(yaml.safe_dump(config))
                original = log.read_bytes()
                with self.assertRaisesRegex(ValueError, "audio-rewarded-frequency"):
                    asyncio.run(train.flickr_discrimination(FakeAgent(), self.ino, config["Experimental"], str(log)))
                self.assertEqual(self.serial.packets, [])
                self.assertEqual(log.read_bytes(), original)

    def test_four_stimulus_lists_control_presentations_and_rewards(self):
        cases = (
            (
                {"visual-rewarded": [14], "visual-non-rewarded": [4],
                 "audio-rewarded": [4, 9], "audio-non-rewarded": [14]},
                {("sync", 14, True): 2, ("sync", 4, False): 2,
                 ("visual", 14, True): 2, ("visual", 4, False): 2,
                 ("audio", 4, True): 2, ("audio", 9, True): 2, ("audio", 14, False): 2},
            ),
            ({"audio-rewarded": [12, 15]},
             {("audio", 12, True): 2, ("audio", 15, True): 2}),
            ({"visual-rewarded": [], "visual-non-rewarded": [],
              "audio-rewarded": [12, 15], "audio-non-rewarded": []},
             {("audio", 12, True): 2, ("audio", 15, True): 2}),
            ({"audio-non-rewarded": [3, 6]},
             {("audio", 3, False): 2, ("audio", 6, False): 2}),
            ({"visual-rewarded": [14]},
             {("sync", 14, True): 2, ("visual", 14, True): 2}),
            ({"visual-non-rewarded": [4]},
             {("sync", 4, False): 2, ("visual", 4, False): 2}),
        )
        for stimulus_settings, expected in cases:
            with self.subTest(stimuli=stimulus_settings):
                config = yaml.safe_load((ROOT / "config/train-sample.yaml").read_text())
                exp = config["Experimental"]
                for key in train.STIMULUS_KEYS:
                    exp.pop(key, None)
                exp.update(stimulus_settings)
                exp["trials-per-stimulus"] = 2
                log = Path(self.temp.name) / "four-stimulus-lists.yaml"
                log.write_text(yaml.safe_dump(config))
                self.serial.packets.clear()

                async def wait(agent, duration):
                    pass

                with patch.object(share, "flush_message_for", wait), patch.object(train, "show_progress"):
                    asyncio.run(train.flickr_discrimination(FakeAgent(), self.ino, exp, str(log)))
                actual = {}
                for packet in self.serial.packets:
                    if packet[0] == 0x1a:
                        modality, hz = "sync", packet[3] / 10
                    elif packet[0] == 0x18:
                        modality, hz = ("audio" if packet[1] == 2 else "visual"), packet[2] / 10
                    else:
                        continue
                    pulses = self.waveform(packet)
                    condition = (modality, hz, exp["reward-pin"] in pulses)
                    actual[condition] = actual.get(condition, 0) + 1
                self.assertEqual(actual, expected)
                self.assertTrue(yaml.safe_load(log.read_text())["Experimental"]["finished"])

    def test_invalid_four_list_settings_stop_before_stimuli(self):
        cases = (
            {"audio-rewarded": [15], "audio-non-rewarded": [15]},
            {"visual-rewarded": [14], "visual-non-rewarded": [14]},
            {"audio-rewarded": None},
            {"audio-rewarded": ["15"]},
            {"audio-rewarded": [-1]},
            {"audio-rewarded": [15], "audio-frequency": [15]},
            {"audio-rewarded": [15], "trials-per-stimulus": 0},
            {key: [] for key in train.STIMULUS_KEYS},
        )
        for stimulus_settings in cases:
            with self.subTest(stimuli=stimulus_settings):
                config = yaml.safe_load((ROOT / "config/train-sample.yaml").read_text())
                for key in train.STIMULUS_KEYS:
                    config["Experimental"].pop(key, None)
                config["Experimental"].update(stimulus_settings)
                log = Path(self.temp.name) / "invalid-four-stimulus-lists.yaml"
                log.write_text(yaml.safe_dump(config))
                original = log.read_bytes()
                with self.assertRaises(ValueError):
                    asyncio.run(train.flickr_discrimination(FakeAgent(), self.ino, config["Experimental"], str(log)))
                self.assertEqual(self.serial.packets, [])
                self.assertEqual(log.read_bytes(), original)

    def test_legacy_stimuli_are_converted_in_startup_log(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "legacy.yaml"
            config = yaml.safe_load((ROOT / "config/train-sample.yaml").read_text())
            exp = config["Experimental"]
            for key in train.STIMULUS_KEYS:
                exp.pop(key, None)
            exp.update({"rewarded-frequency": [14], "extinction-frequency": [4],
                        "audio-frequency": [3, 6, 12, 15], "audio-rewarded-frequency": [12, 15]})
            source.write_text(yaml.safe_dump(config))
            original = source.read_bytes()
            cwd = Path.cwd()
            try:
                os.chdir(temp)
                with patch.object(sys, "argv", ["train", "CHECK", str(source)]), patch("pyno.com.check_connected_board_info", return_value=[]):
                    with self.assertRaisesRegex(RuntimeError, "No Arduino boards"):
                        train.main()
                log = next(Path("log").glob("CHECK-*.yaml"))
                saved = yaml.safe_load(log.read_text())["Experimental"]
                self.assertEqual({key: saved[key] for key in train.STIMULUS_KEYS}, {
                    "visual-rewarded": [14], "visual-non-rewarded": [4],
                    "audio-rewarded": [12, 15], "audio-non-rewarded": [3, 6],
                })
                self.assertFalse(set(train.LEGACY_STIMULUS_KEYS) & saved.keys())
                self.assertEqual(source.read_bytes(), original)
            finally:
                os.chdir(cwd)

    def test_default_stimulus_settings_are_saved_in_startup_log(self):
        for module, name in ((train, "train"), (test_task, "test")):
            with self.subTest(task=name), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "source.yaml"
                config = yaml.safe_load((ROOT / "config" / f"{name}-sample.yaml").read_text())
                config["Experimental"].pop("flickr-on-ratio")
                if module is train:
                    config["Experimental"].pop("audio-rewarded", None)
                source.write_text(yaml.safe_dump(config))
                original = source.read_bytes()
                cwd = Path.cwd()
                try:
                    os.chdir(temp)
                    with patch.object(sys, "argv", [name, "CHECK", str(source)]), patch("pyno.com.check_connected_board_info", return_value=[]):
                        with self.assertRaisesRegex(RuntimeError, "No Arduino boards"):
                            module.main()
                    logs = list(Path("log").glob("CHECK-*.yaml"))
                    self.assertEqual(len(logs), 1)
                    self.assertEqual(yaml.safe_load(logs[0].read_text())["Experimental"]["flickr-on-ratio"], 0.28)
                    if module is train:
                        saved = yaml.safe_load(logs[0].read_text())["Experimental"]
                        self.assertEqual(saved["audio-rewarded"], [])
                        self.assertTrue(set(train.STIMULUS_KEYS) <= saved.keys())
                    self.assertEqual(source.read_bytes(), original)
                finally:
                    os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
