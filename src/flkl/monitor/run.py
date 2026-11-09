"""Run the monitor pipeline for explicitly selected TDMS files on Windows/Linux."""

import argparse
import glob
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml

from flkl.monitor import merge, to_parquet


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def resolve_config(path: Path | None) -> Path:
    """An explicit config takes precedence over the repository's default.yaml."""
    if path is None:
        path = PROJECT_ROOT / "default.yaml"
        if not path.is_file():
            raise ValueError(
                f"No default.yaml in {PROJECT_ROOT}. "
                "Specify the TDMS detection settings with --config PATH."
            )
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Detection config does not exist: {path}")
    with path.open(encoding="utf-8-sig") as stream:
        settings = yaml.safe_load(stream)
    fs = settings.get("fs") if isinstance(settings, dict) else None
    if isinstance(fs, bool) or not isinstance(fs, (int, float)) or not math.isfinite(fs) or fs <= 0:
        raise ValueError(f"{path}: TDMS detection config must contain a positive sampling rate 'fs'.")
    return path


def resolve_inputs(patterns: list[str]) -> list[Path]:
    """Expand quoted globs too, since Windows shells need not expand them."""
    paths = []
    for pattern in patterns:
        expanded = os.path.expanduser(pattern)
        matches = [expanded] if Path(expanded).is_file() else sorted(glob.glob(expanded))
        if not matches:
            raise ValueError(f"No TDMS file matched: {pattern}")
        for match in matches:
            path = Path(match).resolve()
            if not path.is_file() or path.suffix.lower() != ".tdms":
                raise ValueError(f"Expected a TDMS file: {path}")
            if path not in paths:
                paths.append(path)

    # The existing progress analysis has one record per subject/date. Do not
    # silently skip another selected file or overwrite a same-named output.
    names, sessions = {}, {}
    for path in paths:
        name = path.stem.casefold()
        if name in names:
            raise ValueError(f"TDMS filenames collide: {names[name]} and {path}")
        names[name] = path
        metadata = merge.parse_identifier(path)
        key = (metadata["subject"], metadata["date"])
        if key in sessions:
            raise ValueError(
                f"Multiple TDMS files for subject={key[0]}, date={key[1]}: "
                f"{sessions[key]} and {path}. The current progress analysis accepts "
                "one session per subject/date; select the intended file."
            )
        sessions[key] = path
    return paths


def find_command(command: str, option: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise ValueError(f"Command not found: {command}. Add it to PATH or specify {option} PATH.")
    return str(Path(resolved).resolve())


def run(args: argparse.Namespace) -> None:
    config = resolve_config(args.detect_config)
    paths = resolve_inputs(args.tdms)
    detector = find_command(args.detect_command, "--detect-command")
    rscript = None if args.no_plot else find_command(args.rscript, "--rscript")
    output_dir = args.output_dir.expanduser().resolve()
    binary_dir = output_dir / "binary"
    figure_dir = output_dir / "fig"
    group_config = (
        args.group_config.expanduser().resolve()
        if args.group_config is not None else output_dir / "group.toml"
    )
    if args.group_config is not None and not group_config.is_file():
        raise ValueError(f"Group config does not exist: {group_config}")

    print(f"[INFO] Detection config: {config}", flush=True)
    print(f"[INFO] Output directory: {output_dir}", flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    binary_dir.mkdir(parents=True, exist_ok=True)

    # Keep all derived files away from the input directory, including temporary
    # CSVs. Commands are argument lists, so spaces/Unicode need no shell escaping.
    env = dict(os.environ, PYTHONUTF8="1")
    parquet_paths = []
    with tempfile.TemporaryDirectory(prefix="detect-", dir=output_dir) as temp:
        subprocess.run(
            [detector, *map(str, paths), str(config), "--output", temp,
             "--exclude-events", "RotaryA", "RotaryB"],
            check=True, env=env,
        )
        for path in paths:
            csv_path = Path(temp) / f"{path.stem}_binary.csv"
            if not csv_path.is_file():
                raise ValueError(f"detect did not create the expected file: {csv_path}")
            parquet_paths.append(to_parquet.convert(csv_path, binary_dir))

    # Explicitly selected sessions are recalculated; other sessions are retained.
    merge.main([
        *map(str, parquet_paths), "--output-dir", str(output_dir),
        "--group-config", str(group_config), "--overwrite",
    ])

    if args.no_plot:
        return
    if not all((output_dir / name).is_file() for name in ("summary.csv", "recent.csv")):
        print("[INFO] No trial summary was produced; skipping plots.")
        return
    subprocess.run(
        [rscript, str(Path(__file__).with_name("draw_progress.R")),
         "--data-dir", str(output_dir), "--figure-dir", str(figure_dir), "--force"],
        check=True, env=env,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert selected TDMS files, update training summaries, and draw progress plots."
    )
    parser.add_argument("tdms", nargs="+", help="TDMS file(s) or quoted wildcard pattern(s)")
    parser.add_argument(
        "--config", "--detect-config", dest="detect_config", type=Path,
        help="Detection YAML. Default: default.yaml in the flkl repository; required if absent.",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=Path("monitor-output"),
        help="Directory for binary/, summary.csv, recent.csv, group.toml, and fig/. Default: ./monitor-output",
    )
    parser.add_argument(
        "--group-config", type=Path,
        help="Existing group TOML. Default: group.toml in --output-dir (created interactively).",
    )
    parser.add_argument(
        "--detect-command", default="detect",
        help="detect executable name or path. Default: detect on PATH",
    )
    parser.add_argument(
        "--rscript", default="Rscript",
        help="Rscript executable name or path. Default: Rscript on PATH",
    )
    parser.add_argument("--no-plot", action="store_true", help="Convert and summarize without running R")
    args = parser.parse_args(argv)
    try:
        run(args)
    except (OSError, ValueError, yaml.YAMLError, EOFError) as exc:
        parser.exit(1, f"[ERROR] {exc}\n")
    except subprocess.CalledProcessError as exc:
        parser.exit(1, f"[ERROR] {exc.cmd[0]} failed (exit code {exc.returncode}).\n")


if __name__ == "__main__":
    main()
