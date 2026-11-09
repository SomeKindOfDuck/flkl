import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from flkl.monitor import run


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="flkl monitor 日本語-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.default = self.project / "default.yaml"
        self.config = self.root / "検出 設定.yaml"
        self.config.write_text("fs: 2000\n", encoding="utf-8-sig")
        self.output = self.root / "解析 結果"
        self.groups = self.root / "groups.toml"
        self.groups.write_text('single = ["001", "M02"]\nmulti = []\n', encoding="utf-8-sig")
        self.calls = []

    def tdms(self, filename, folder="入力 データ"):
        path = self.root / folder / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"raw TDMS placeholder")
        return path

    def events(self):
        rows = [("FrameSignal-on", 0.0), ("FrameSignal-off", 30.0)]
        for event, start, hz in [("LED", 5.0, 4), ("Sound", 15.0, 6)]:
            for pulse in range(hz * 2):
                time = start + pulse / hz
                rows.extend([(event + "-on", time), (event + "-off", time + 0.02)])
        rows.extend(("Lick-on", t) for t in [5.5, 6.5, 15.3, 16.7])
        return pd.DataFrame(rows, columns=["event", "time"]).sort_values("time")

    def fake_command(self, command, **kwargs):
        self.calls.append(command)
        self.assertTrue(kwargs.get("check"))
        self.assertFalse(kwargs.get("shell", False))
        if command[0].endswith("detect.exe"):
            output = Path(command[command.index("--output") + 1])
            for item in command[1:]:
                if item.lower().endswith(".tdms"):
                    self.events().to_csv(output / f"{Path(item).stem}_binary.csv", index=False)
        return subprocess.CompletedProcess(command, 0)

    def invoke(self, paths, extra=None):
        args = [
            *map(str, paths), "--config", str(self.config), "--output-dir", str(self.output),
            "--group-config", str(self.groups),
            "--detect-command", "C:/Program Files/TDMS/detect.exe",
            "--rscript", "C:/Program Files/R/Rscript.exe",
            *(extra or []),
        ]
        with patch.object(run, "find_command", side_effect=lambda command, option: command), \
             patch.object(run.subprocess, "run", side_effect=self.fake_command), \
             contextlib.redirect_stdout(io.StringIO()):
            run.main(args)

    def test_config_precedence_and_repository_relative_default(self):
        self.default.write_text("fs: 1000\n", encoding="utf-8")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "default.yaml").write_text("fs: 500\n", encoding="utf-8")
        previous = Path.cwd()
        try:
            os.chdir(elsewhere)
            with patch.object(run, "PROJECT_ROOT", self.project):
                self.assertEqual(run.resolve_config(None), self.default)
                self.assertEqual(run.resolve_config(self.config), self.config)
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    run.resolve_config(self.root / "missing.yaml")
        finally:
            os.chdir(previous)

    def test_missing_default_requires_argument_before_processing(self):
        source = self.tdms("001_Phase-01_1_20261109-100000.tdms")
        errors = io.StringIO()
        with patch.object(run, "PROJECT_ROOT", self.project), \
             patch.object(run.subprocess, "run") as command, \
             contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as exit:
            run.main([str(source), "--output-dir", str(self.output)])
        self.assertEqual(exit.exception.code, 1)
        self.assertIn("--config", errors.getvalue())
        command.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_training_yaml_is_not_accepted_as_detection_config(self):
        self.config.write_text("Experimental:\n  flickr-duration: 2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sampling rate"):
            run.resolve_config(self.config)

    def test_multiple_paths_globs_and_duplicate_arguments(self):
        first = self.tdms("001_Phase-01_1_20261109-100000.tdms")
        second = self.tdms("M02_Phase-01_1_20261109-110000.tdms", "別の フォルダ")
        self.assertEqual(
            run.resolve_inputs([str(first.parent / "*.tdms"), str(second), str(first)]),
            [first, second],
        )

    def test_filename_collisions_and_same_day_sessions_are_not_silently_skipped(self):
        first = self.tdms("001_Phase-01_1_20261109-100000.tdms")
        duplicate = self.tdms(first.name, "duplicate")
        with self.assertRaisesRegex(ValueError, "filenames collide"):
            run.resolve_inputs([str(first), str(duplicate)])
        session = self.tdms("001_Phase-01_2_20261109-110000.tdms")
        with self.assertRaisesRegex(ValueError, "one session per subject/date"):
            run.resolve_inputs([str(first), str(session)])

    def test_all_inputs_are_checked_before_conversion(self):
        first = self.tdms("001_Phase-01_1_20261109-100000.tdms")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke([first, self.root / "missing.tdms"])
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output.exists())

    def test_pipeline_handles_separate_directories_and_keeps_existing_sessions(self):
        first = self.tdms("001_Phase-01_1_20261109-100000.tdms")
        second = self.tdms("M02_Phase-01_1_20261109-110000.tdms", "別の フォルダ")
        before = {p: p.read_bytes() for p in (first, second, self.groups)}
        self.invoke([first, second])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0][1:3], [str(first), str(second)])
        self.assertEqual(self.calls[0][3], str(self.config))
        self.assertEqual(self.calls[0][-3:], ["--exclude-events", "RotaryA", "RotaryB"])
        self.assertEqual(self.calls[1][-5:], [
            "--data-dir", str(self.output), "--figure-dir", str(self.output / "fig"), "--force",
        ])
        for path in (first, second):
            binary = pd.read_parquet(self.output / "binary" / f"{path.stem}_binary.parquet")
            pd.testing.assert_frame_equal(binary, self.events().reset_index(drop=True))
            self.assertEqual(list(path.parent.iterdir()), [path])
        summary = pd.read_csv(self.output / "summary.csv", dtype={"subject": str})
        self.assertEqual(set(summary.subject), {"001", "M02"})
        self.assertEqual(set(summary.loc[summary.time_window == "CS", "lick_mean"]), {1.0})
        self.assertFalse(list(self.output.glob("detect-*")))

        # Re-run only one subject: no duplicate summary and no loss of the other.
        self.calls.clear()
        self.invoke([first], ["--no-plot"])
        self.assertEqual(len(self.calls), 1)
        rerun = pd.read_csv(self.output / "summary.csv", dtype={"subject": str})
        pd.testing.assert_frame_equal(rerun, summary)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_detector_failure_stops_the_pipeline(self):
        source = self.tdms("001_Phase-01_1_20261109-100000.tdms")
        def fail(command, **kwargs):
            raise subprocess.CalledProcessError(9, command)
        with patch.object(self, "fake_command", side_effect=fail), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke([source])
        self.assertFalse((self.output / "summary.csv").exists())
        self.assertFalse(list(self.output.glob("detect-*")))
        self.assertEqual(source.read_bytes(), b"raw TDMS placeholder")


if __name__ == "__main__":
    unittest.main()
