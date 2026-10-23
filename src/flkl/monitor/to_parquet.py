"""tdms から変換した binary csv(列: event, time)を parquet にする

    uv run python -m flkl.monitor.to_parquet <binary csv ...> --outdir <出力先> [--remove]

- 出力は <出力先>/{csv と同じ stem}.parquet(例: G12F2_Phase-01_40_20260924-091721_binary.parquet)、zstd 圧縮
- 列と値は csv と同じ(event: 文字列、time: float64)。書き出した後に読み直して csv と一致することを確かめる
- --remove: 一致を確かめたら csv を消す
"""

import argparse
from pathlib import Path

import pandas as pd


def convert(csv_path: Path, outdir: Path) -> Path:
    df = pd.read_csv(csv_path, dtype={"event": str}, float_precision="round_trip")
    missing = {"event", "time"} - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} does not contain required column(s): {', '.join(sorted(missing))}")
    df = df[["event", "time"]].astype({"event": str, "time": "float64"})
    out_path = outdir / f"{csv_path.stem}.parquet"
    tmp_path = out_path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp_path, index=False, compression="zstd")
    back = pd.read_parquet(tmp_path)
    if not back.equals(df):
        tmp_path.unlink()
        raise ValueError(f"Round-trip check failed: {csv_path}")
    tmp_path.replace(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert binary CSV (event, time) to parquet.")
    parser.add_argument("csv", type=Path, nargs="+", help="Input binary CSV file(s)")
    parser.add_argument("--outdir", "-o", type=Path, required=True, help="Output directory")
    parser.add_argument("--remove", action="store_true", help="Remove the CSV after a successful conversion")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    for csv_path in args.csv:
        out_path = convert(csv_path, args.outdir)
        if args.remove:
            csv_path.unlink()
        print(f"[OK] {csv_path.name} -> {out_path}")


if __name__ == "__main__":
    main()
