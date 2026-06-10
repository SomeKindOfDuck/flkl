import argparse
import shutil
from pathlib import Path

import pandas as pd


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

    single = list(dict.fromkeys(group_config.get("single", [])))
    multi = list(dict.fromkeys(group_config.get("multi", [])))

    def format_list(values: list[str]) -> str:
        items = ", ".join(f'"{value}"' for value in values)
        return f"[{items}]"

    text = "\n".join(
        [
            f"single = {format_list(single)}",
            f"multi = {format_list(multi)}",
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


def parse_identifier(
    path: Path,
    group_config: dict[str, list[str]],
    group_config_path: Path,
) -> dict:
    identifier = path.stem.split("_")

    if len(identifier) < 4:
        raise ValueError(
            f"Invalid filename format: {path.name}. "
            "Expected at least subject_phase_session_date..."
        )

    subject = identifier[0]
    phase = identifier[1]
    session = int(identifier[2])
    date = identifier[3].split("-")[0]

    condition = resolve_condition(
        subject=subject,
        group_config=group_config,
        group_config_path=group_config_path,
    )

    return {
        "subject": subject,
        "date": date,
        "condition": condition,
        "phase": phase,
        "session": session,
    }


def load_binary_csv(
    path: Path,
    group_config: dict[str, list[str]],
    group_config_path: Path,
) -> pd.DataFrame:
    metadata = parse_identifier(path, group_config, group_config_path)

    df = pd.read_csv(path)

    required_cols = {"time", "event"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"{path} does not contain required column(s): "
            + ", ".join(sorted(missing_cols))
        )

    df["time"] = df["time"] - df["time"].min(skipna=True)

    for key, value in metadata.items():
        df[key] = value

    return df[
        [
            "subject",
            "date",
            "condition",
            "phase",
            "session",
            "time",
            "event",
        ]
    ]


def make_subject_date_index(df: pd.DataFrame) -> pd.MultiIndex:
    return pd.MultiIndex.from_arrays(
        [
            df["subject"].astype(str),
            df["date"].astype(str),
        ],
        names=["subject", "date"],
    )


def find_duplicate_subject_dates(
    merged_data: pd.DataFrame,
    new_merged_data: pd.DataFrame,
) -> set[tuple[str, str]]:
    if merged_data.empty or new_merged_data.empty:
        return set()

    required_cols = {"subject", "date"}

    if not required_cols.issubset(merged_data.columns):
        return set()

    if not required_cols.issubset(new_merged_data.columns):
        return set()

    existing_keys = set(make_subject_date_index(merged_data).tolist())
    new_keys = set(make_subject_date_index(new_merged_data).tolist())

    return existing_keys & new_keys


def filter_by_subject_dates(
    df: pd.DataFrame,
    subject_date_keys: set[tuple[str, str]],
    keep_matches: bool,
) -> pd.DataFrame:
    if df.empty or not subject_date_keys:
        return df

    keys = make_subject_date_index(df)
    duplicated = keys.isin(subject_date_keys)

    if keep_matches:
        return df.loc[duplicated].copy()
    else:
        return df.loc[~duplicated].copy()


def ask_duplicate_action(duplicate_keys: set[tuple[str, str]]) -> str:
    print("[WARN] The following subject/date pairs already exist in merged data:")

    for subject, date in sorted(duplicate_keys):
        print(f"  - subject={subject}, date={date}")

    while True:
        answer = input(
            "Choose action: [s]kip new data / [o]verwrite existing data: "
        ).strip().lower()

        if answer in {"s", "skip"}:
            return "skip"

        if answer in {"o", "overwrite"}:
            return "overwrite"

        print("Please enter 's' or 'o'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge binary CSV files and archive source files."
    )
    parser.add_argument(
        "csv",
        type=Path,
        nargs="+",
        help="Input binary CSV file(s) to merge",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("data/behavior/merged.csv"),
        help="Output merged CSV file. Default: merged.csv",
    )
    parser.add_argument(
        "--archive-dir",
        "-a",
        type=Path,
        default=Path("archives"),
        help="Directory to move merged source files into. Default: archives",
    )
    parser.add_argument(
        "--group-config",
        "-g",
        type=Path,
        default=Path("group.toml"),
        help="Path to group TOML file. Default: group.toml",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_paths = [path.resolve() for path in args.csv]
    output_path = args.output.resolve()
    group_config_path = args.group_config.resolve()

    group_config = load_group_config(group_config_path)

    if output_path in input_paths:
        raise ValueError("Output file must not be included in input CSV files.")

    archive_dir = args.archive_dir
    if not archive_dir.is_absolute():
        archive_dir = output_path.parent / archive_dir
    archive_dir = archive_dir.resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        merged_data = pd.read_csv(output_path)
    else:
        merged_data = pd.DataFrame()

    new_merged_data = pd.concat(
        [
            load_binary_csv(
                path,
                group_config=group_config,
                group_config_path=group_config_path,
            )
            for path in input_paths
        ],
        ignore_index=True,
    )

    duplicate_keys = find_duplicate_subject_dates(
        merged_data=merged_data,
        new_merged_data=new_merged_data,
    )

    if duplicate_keys:
        action = ask_duplicate_action(duplicate_keys)

        if action == "skip":
            new_merged_data = filter_by_subject_dates(
                new_merged_data,
                duplicate_keys,
                keep_matches=False,
            )
            print("[OK] Skipped duplicated subject/date data.")

        elif action == "overwrite":
            merged_data = filter_by_subject_dates(
                merged_data,
                duplicate_keys,
                keep_matches=False,
            )
            print("[OK] Removed existing duplicated subject/date data.")

    merged_data = pd.concat(
        [merged_data, new_merged_data],
        ignore_index=True,
    )

    merged_data.to_csv(output_path, index=False)
    print(f"[OK] Wrote merged data: {output_path}")

    failed_moves: list[Path] = []

    for src in input_paths:
        dst = archive_dir / src.name

        if dst.exists():
            failed_moves.append(src)
            continue

        try:
            shutil.move(str(src), str(dst))
        except OSError:
            failed_moves.append(src)

    if failed_moves:
        print(
            "[WARN] Some files could not be moved to archives: "
            + ", ".join(path.name for path in failed_moves)
        )

    print(f"[OK] Archived source files into: {archive_dir}")


if __name__ == "__main__":
    main()
