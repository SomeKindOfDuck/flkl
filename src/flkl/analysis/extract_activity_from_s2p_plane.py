import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export Suite2p cell fluorescence traces to parquet."
    )
    parser.add_argument(
        "plane_dir",
        type=str,
        help="Path to suite2p plane directory, e.g. suite2p/plane0",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        type=str,
        default=None,
        help="Output directory. Default: <plane_dir>/exported",
    )
    parser.add_argument(
        "--neuropil-coef",
        type=float,
        default=0.7,
        help="Neuropil correction coefficient. Default: 0.7",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=5000,
        help="Number of frames per parquet row group. Default: 5000",
    )
    parser.add_argument(
        "--all-rois",
        action="store_true",
        help="Export all ROIs instead of only manually accepted cells.",
    )
    return parser.parse_args()


def load_suite2p_files(plane_dir: Path):
    required = {
        "F": plane_dir / "F.npy",
        "Fneu": plane_dir / "Fneu.npy",
        "iscell": plane_dir / "iscell.npy",
        "stat": plane_dir / "stat.npy",
    }

    missing = [str(p) for p in required.values() if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing files:\n" + "\n".join(missing))

    F = np.load(required["F"], mmap_mode="r")
    Fneu = np.load(required["Fneu"], mmap_mode="r")
    iscell = np.load(required["iscell"], allow_pickle=True)
    stat = np.load(required["stat"], allow_pickle=True)

    return F, Fneu, iscell, stat


def get_centroid(stat_entry):
    if isinstance(stat_entry, np.ndarray):
        stat_entry = stat_entry.item()

    if "med" in stat_entry:
        y, x = stat_entry["med"]
        return float(y), float(x)

    y = float(np.mean(stat_entry["ypix"])) if "ypix" in stat_entry else np.nan
    x = float(np.mean(stat_entry["xpix"])) if "xpix" in stat_entry else np.nan
    return y, x


def build_cell_metadata(iscell, stat, roi_indices: np.ndarray) -> pd.DataFrame:
    records = []

    for cell_id, roi_idx in enumerate(roi_indices):
        y, x = get_centroid(stat[int(roi_idx)])

        records.append(
            {
                "cell_id": f"cell_{cell_id:06d}",
                "cell_index": cell_id,
                "original_roi": int(roi_idx),
                "iscell": int(iscell[int(roi_idx), 0]),
                "iscell_prob": float(iscell[int(roi_idx), 1]),
                "y": y,
                "x": x,
            }
        )

    return pd.DataFrame(records)


def compute_f0_lower_percentile_mean(
    F,
    Fneu,
    roi_indices: np.ndarray,
    neuropil_coef: float,
    percentile: float = 5.0,
    roi_batch_size: int = 256,
) -> np.ndarray:
    """
    F0 = mean of values below the lower percentile for each cell.
    Returns shape: (n_cells,)
    """
    f0_list = []

    for start in range(0, len(roi_indices), roi_batch_size):
        end = min(start + roi_batch_size, len(roi_indices))
        batch_rois = roi_indices[start:end]

        corrected = (
            F[batch_rois, :].astype(np.float32)
            - neuropil_coef * Fneu[batch_rois, :].astype(np.float32)
        )

        q = np.nanpercentile(corrected, percentile, axis=1, keepdims=True)

        f0_batch = np.array(
            [
                np.nanmean(corrected[i, corrected[i, :] <= q[i]])
                for i in range(corrected.shape[0])
            ],
            dtype=np.float32,
        )

        f0_list.append(f0_batch)

        print(f"[OK] computed F0 for cells {start}–{end - 1}")

    f0 = np.concatenate(f0_list)

    # 0割り・異常値対策
    f0[~np.isfinite(f0)] = np.nan
    f0[f0 == 0] = np.nan

    return f0


def write_dff_parquet(
    F,
    Fneu,
    roi_indices: np.ndarray,
    f0: np.ndarray,
    outpath: Path,
    neuropil_coef: float,
    chunksize: int,
):
    n_rois, n_frames = F.shape
    n_cells = len(roi_indices)

    cell_cols = [f"cell_{i:06d}" for i in range(n_cells)]

    writer = None

    try:
        for start in range(0, n_frames, chunksize):
            end = min(start + chunksize, n_frames)

            corrected = (
                F[roi_indices, start:end].astype(np.float32)
                - neuropil_coef * Fneu[roi_indices, start:end].astype(np.float32)
            )

            dff = (corrected - f0[:, None]) / f0[:, None]

            dff = dff.T.astype(np.float32)

            df = pd.DataFrame(dff, columns=cell_cols)
            df.insert(0, "frame_idx", np.arange(start, end, dtype=np.int64))

            table = pa.Table.from_pandas(df, preserve_index=False)

            if writer is None:
                writer = pq.ParquetWriter(
                    outpath,
                    table.schema,
                    compression="zstd",
                )

            writer.write_table(table)

            print(f"[OK] wrote dF/F frames {start}–{end - 1}")

    finally:
        if writer is not None:
            writer.close()


def main():
    args = parse_args()

    plane_dir = Path(args.plane_dir)
    outdir = Path(args.outdir) if args.outdir is not None else plane_dir / "exported"
    outdir.mkdir(parents=True, exist_ok=True)

    F, Fneu, iscell, stat = load_suite2p_files(plane_dir)

    if F.shape != Fneu.shape:
        raise ValueError(f"F and Fneu shapes differ: F={F.shape}, Fneu={Fneu.shape}")

    if args.all_rois:
        roi_indices = np.arange(F.shape[0])
    else:
        roi_indices = np.where(iscell[:, 0].astype(bool))[0]

    print(f"F shape       : {F.shape}")
    print(f"Fneu shape    : {Fneu.shape}")
    print(f"Exported ROIs : {len(roi_indices)}")

    dff_path = outdir / "suite2p_dff_lower5.parquet"
    f0_path = outdir / "suite2p_f0_lower5.csv"

    f0 = compute_f0_lower_percentile_mean(
        F=F,
        Fneu=Fneu,
        roi_indices=roi_indices,
        neuropil_coef=args.neuropil_coef,
        percentile=5.0,
        roi_batch_size=256,
    )

    pd.DataFrame(
        {
            "cell_id": [f"cell_{i:06d}" for i in range(len(f0))],
            "cell_index": np.arange(len(f0)),
            "original_roi": roi_indices,
            "f0": f0,
        }
    ).to_csv(f0_path, index=False)

    write_dff_parquet(
        F=F,
        Fneu=Fneu,
        roi_indices=roi_indices,
        f0=f0,
        outpath=dff_path,
        neuropil_coef=args.neuropil_coef,
        chunksize=args.chunksize,
    )

    print(f"[DONE] dF/F parquet: {dff_path}")
    print(f"[DONE] F0 csv       : {f0_path}")


if __name__ == "__main__":
    main()
