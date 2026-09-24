"""訓練経過の作図用データを作成する

data/behavior/にあるbinary csv(tdmsから変換したもの)を読み、
まだ処理していないセッションを追加して以下の2つのファイルを更新する。

- recent.csv  : 個体ごとに直近N(default: 10)セッションの生イベントデータ
- summary.csv : 全個体・全セッションの、刺激×時間窓ごとの平均lick rate
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

STIM_DURATION = 2.0
MIN_ITI = 5.0
PRE_CS = STIM_DURATION
POST_CS = 2 * STIM_DURATION

TIME_WINDOWS = {
    "Pre-CS": (-PRE_CS, 0.0),
    "CS": (0.0, STIM_DURATION),
    "US": (STIM_DURATION, POST_CS),
}

METADATA_COLUMNS = ["subject", "date", "condition", "phase", "session"]
KEY_COLUMNS = ["subject", "date"]


def load_group_config(path: Path) -> dict[str, list[str]]:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    if not path.exists():
        group_config = {"single": [], "multi": []}
        save_group_config(group_config, path)
        return group_config

    with path.open("rb") as f:
        data = tomllib.load(f)

    return {
        "single": list(data.get("single", [])),
        "multi": list(data.get("multi", [])),
    }


def save_group_config(group_config: dict[str, list[str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def format_list(values: list[str]) -> str:
        items = ", ".join(f'"{value}"' for value in dict.fromkeys(values))
        return f"[{items}]"

    text = "\n".join(
        [
            f"single = {format_list(group_config.get('single', []))}",
            f"multi = {format_list(group_config.get('multi', []))}",
            "",
        ]
    )

    path.write_text(text, encoding="utf-8")


def resolve_condition(
    subject: str,
    group_config: dict[str, list[str]],
    group_config_path: Path,
) -> str:
    in_single = subject in group_config.get("single", [])
    in_multi = subject in group_config.get("multi", [])

    if in_single and in_multi:
        raise ValueError(
            f"Subject {subject} is included in both single and multi groups."
        )

    if in_single:
        return "Single"

    if in_multi:
        return "Multi"

    while True:
        answer = input(
            f"Subject '{subject}' is not found in {group_config_path}. "
            "Choose group [single/multi]: "
        ).strip().lower()

        if answer in {"single", "s"}:
            group_config.setdefault("single", []).append(subject)
            save_group_config(group_config, group_config_path)
            return "Single"

        if answer in {"multi", "m"}:
            group_config.setdefault("multi", []).append(subject)
            save_group_config(group_config, group_config_path)
            return "Multi"

        print("Please enter 'single' or 'multi'.")


def parse_identifier(path: Path) -> dict:
    # {subject}_{phase}_{session}_{date}-{time}_binary.csv
    identifier = path.stem.split("_")

    if len(identifier) < 4:
        raise ValueError(
            f"Invalid filename format: {path.name}. "
            "Expected at least subject_phase_session_date..."
        )

    return {
        "subject": identifier[0],
        "date": identifier[3].split("-")[0],
        "phase": identifier[1],
        "session": int(identifier[2]),
    }


def load_binary_csv(path: Path, condition: str, metadata: dict) -> pd.DataFrame:
    df = pd.read_csv(path)

    missing_cols = {"time", "event"} - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"{path} does not contain required column(s): "
            + ", ".join(sorted(missing_cols))
        )

    df["time"] = df["time"] - df["time"].min(skipna=True)

    for key, value in {**metadata, "condition": condition}.items():
        df[key] = value

    return df[METADATA_COLUMNS + ["time", "event"]]


def detect_trial_onsets(events: pd.DataFrame, min_iti: float = MIN_ITI) -> np.ndarray:
    # 視覚・聴覚刺激のonset間隔がmin_iti秒以上空いた箇所を試行の境界とみなし、
    # 各試行の最初のonset時刻(=CS onset)を返す
    onsets = np.sort(
        events.loc[events["event"].isin(["LED-on", "Sound-on"]), "time"].to_numpy()
    )

    if len(onsets) == 0:
        return onsets

    gap = np.diff(onsets, prepend=-np.inf)
    return onsets[gap >= min_iti]


def count_in(times: np.ndarray, starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    # timesはソート済みであること。各[start, end)に含まれる要素数を返す
    return np.searchsorted(times, ends, side="left") - np.searchsorted(
        times, starts, side="left"
    )


def classify_stimulus(visual_freq: pd.Series, audio_freq: pd.Series) -> pd.Series:
    conditions = [
        (visual_freq > 0) & (audio_freq > 0) & (visual_freq == audio_freq),
        (visual_freq > 0) & (audio_freq > 0),
        visual_freq > 0,
        audio_freq > 0,
    ]
    choices = ["Synchronous", "Asynchronous", "Visual-only", "Audio-only"]
    return pd.Series(
        np.select(conditions, choices, default="None"), index=visual_freq.index
    )


def summarize_trials(events: pd.DataFrame) -> pd.DataFrame:
    """1セッション分のイベントから、試行×時間窓ごとのlick rateを計算する"""
    cs_on = detect_trial_onsets(events)

    # 記録の端で窓が欠ける試行は除外する
    t_min, t_max = events["time"].min(), events["time"].max()
    cs_on = cs_on[(cs_on - PRE_CS >= t_min) & (cs_on + POST_CS <= t_max)]

    if len(cs_on) == 0:
        return pd.DataFrame()

    def times_of(event: str) -> np.ndarray:
        return np.sort(events.loc[events["event"] == event, "time"].to_numpy())

    led_on, sound_on, lick_on = times_of("LED-on"), times_of("Sound-on"), times_of("Lick-on")

    trials = pd.DataFrame(
        {
            "trial": np.arange(1, len(cs_on) + 1),
            "visual_freq": count_in(led_on, cs_on - PRE_CS, cs_on + POST_CS) / STIM_DURATION,
            "audio_freq": count_in(sound_on, cs_on - PRE_CS, cs_on + POST_CS) / STIM_DURATION,
        }
    )

    windows = []
    for name, (start, end) in TIME_WINDOWS.items():
        window = trials.copy()
        window["time_window"] = name
        window["lick"] = count_in(lick_on, cs_on + start, cs_on + end) / (end - start)
        windows.append(window)

    trial_licks = pd.concat(windows, ignore_index=True)

    trial_licks["stimulus_type"] = classify_stimulus(
        trial_licks["visual_freq"], trial_licks["audio_freq"]
    )
    trial_licks = trial_licks[trial_licks["stimulus_type"] != "None"]

    # 非同期刺激では聴覚刺激の周波数を主とする
    trial_licks["major_freq"] = np.where(
        trial_licks["stimulus_type"].isin(["Synchronous", "Visual-only"]),
        trial_licks["visual_freq"],
        trial_licks["audio_freq"],
    )

    return trial_licks


def summarize_session(events: pd.DataFrame) -> pd.DataFrame:
    """1セッション分のイベントから、刺激×時間窓ごとの平均lick rateを計算する"""
    trial_licks = summarize_trials(events)

    if trial_licks.empty:
        return pd.DataFrame()

    summary = (
        trial_licks
        .groupby(
            ["stimulus_type", "visual_freq", "audio_freq", "major_freq", "time_window"],
            as_index=False,
        )
        .agg(
            n_trials=("lick", "size"),
            lick_mean=("lick", "mean"),
            lick_sd=("lick", "std"),
        )
    )
    summary["lick_se"] = summary["lick_sd"] / np.sqrt(summary["n_trials"])

    for col in METADATA_COLUMNS:
        summary.insert(METADATA_COLUMNS.index(col), col, events[col].iloc[0])

    return summary


def renumber_sessions(df: pd.DataFrame) -> pd.DataFrame:
    # ファイル名由来のsession番号は入力ミス等でずれることがあるため、
    # 個体ごとにdateの昇順で通し番号を振り直す
    df = df.copy()
    df["session"] = (
        df.groupby("subject")["date"].rank(method="dense").astype(int)
    )
    return df


def keep_recent_sessions(df: pd.DataFrame, n_recent: int) -> pd.DataFrame:
    rank_from_last = df.groupby("subject")["date"].rank(method="dense", ascending=False)
    return df[rank_from_last <= n_recent]


def read_csv_or_empty(path: Path) -> pd.DataFrame:
    if path.exists():
        # 読み書きの繰り返しで浮動小数点の値が変わらないようにround_tripで読む
        return pd.read_csv(path, dtype={"date": str}, float_precision="round_trip")
    return pd.DataFrame()


def drop_keys(df: pd.DataFrame, keys: set[tuple[str, str]]) -> pd.DataFrame:
    if df.empty or not keys:
        return df
    index = pd.MultiIndex.from_frame(df[KEY_COLUMNS].astype(str))
    return df[~index.isin(keys)]


def write_csv(df: pd.DataFrame, path: Path) -> None:
    # 書き込み途中で中断しても既存ファイルが壊れないよう、一時ファイル経由で置き換える
    tmp_path = path.with_name(path.name + ".tmp")
    df.to_csv(tmp_path, index=False)
    tmp_path.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update recent event data and lick summary for training progress plots."
    )
    parser.add_argument(
        "csv",
        type=Path,
        nargs="*",
        help="Input binary CSV file(s). Default: all *_binary.csv in --input-dir",
    )
    parser.add_argument(
        "--input-dir",
        "-i",
        type=Path,
        default=Path("data/behavior"),
        help="Directory containing binary CSV files. Default: data/behavior",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("data/monitor"),
        help="Directory for recent.csv and summary.csv. Default: data/monitor",
    )
    parser.add_argument(
        "--n-recent",
        "-n",
        type=int,
        default=10,
        help="Number of recent sessions per subject kept in recent.csv. Default: 10",
    )
    parser.add_argument(
        "--group-config",
        "-g",
        type=Path,
        default=Path("group.toml"),
        help="Path to group TOML file. Default: group.toml",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing subject/date data. By default, they are skipped.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    csv_paths = args.csv or sorted(args.input_dir.glob("*_binary.csv"))
    input_paths = [path.resolve() for path in csv_paths]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    recent_path = output_dir / "recent.csv"
    summary_path = output_dir / "summary.csv"

    group_config_path = args.group_config.resolve()
    group_config = load_group_config(group_config_path)

    recent = read_csv_or_empty(recent_path)
    summary = read_csv_or_empty(summary_path)

    existing_keys = (
        set(map(tuple, summary[KEY_COLUMNS].astype(str).drop_duplicates().to_numpy()))
        if not summary.empty
        else set()
    )

    new_events: list[pd.DataFrame] = []
    new_summaries: list[pd.DataFrame] = []
    processed_paths: list[Path] = []
    n_skipped = 0
    seen_keys: set[tuple[str, str]] = set()

    for path in input_paths:
        metadata = parse_identifier(path)
        key = (metadata["subject"], metadata["date"])

        if key in seen_keys:
            print(f"[WARN] Duplicated subject/date in inputs, skipped: {path.name}")
            continue

        if key in existing_keys and not args.overwrite:
            n_skipped += 1
            continue

        condition = resolve_condition(metadata["subject"], group_config, group_config_path)
        events = load_binary_csv(path, condition, metadata)
        session_summary = summarize_session(events)

        if session_summary.empty:
            print(f"[WARN] No trials detected, skipped: {path.name}")
            continue

        seen_keys.add(key)
        new_events.append(events)
        new_summaries.append(session_summary)
        processed_paths.append(path)
        print(f"[OK] subject={key[0]}, date={key[1]}: {path.name}")

    if n_skipped > 0:
        print(f"[INFO] Skipped {n_skipped} existing session(s). Use --overwrite to reprocess.")

    if not processed_paths:
        print("[INFO] Nothing to merge.")
        return

    summary = pd.concat(
        [drop_keys(summary, seen_keys), *new_summaries], ignore_index=True
    )
    summary = renumber_sessions(summary).sort_values(
        ["subject", "session", "stimulus_type", "major_freq", "visual_freq", "audio_freq", "time_window"]
    )
    write_csv(summary, summary_path)
    print(f"[OK] Wrote summary: {summary_path}")

    recent = pd.concat([drop_keys(recent, seen_keys), *new_events], ignore_index=True)
    recent = keep_recent_sessions(recent, args.n_recent)

    # recentのsession番号はsummary(全セッション)に揃える
    session_map = summary[KEY_COLUMNS + ["session"]].drop_duplicates()
    recent = (
        recent
        .drop(columns="session")
        .astype({"date": str})
        .merge(session_map.astype({"date": str}), on=KEY_COLUMNS, how="left")
        [METADATA_COLUMNS + ["time", "event"]]
        .sort_values(["subject", "session", "time"], kind="stable")
    )
    write_csv(recent, recent_path)
    print(f"[OK] Wrote recent data ({args.n_recent} sessions/subject): {recent_path}")


if __name__ == "__main__":
    main()
