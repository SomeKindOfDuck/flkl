# flkl

視覚・聴覚刺激(フリッカー)を用いた弁別課題の実験制御と解析。

```
src/flkl/
├── bhv/        # 実験制御(uv run train / test / blink)
├── monitor/    # 訓練経過の前処理・作図と、その日次自動化
└── analysis/   # 2pデータの本解析
config/         # 設定ファイル(*-sample.* をコピーして使う)
data/           # データ(git管理外)
fig/            # 図(git管理外)
log/            # ログ(git管理外)
```

コマンドはすべてプロジェクトのルートで実行する(スクリプト内で相対パスを使っているため)。

## 依存関係

### Python

- [uv](https://docs.astral.sh/uv/)。Pythonの依存パッケージは `uv sync` で入る(`pyproject.toml` 参照)
- `detect` コマンド: tdms を binary csv に変換する。
  [TDMSViewer](https://github.com/7cm-diameter/TDMSViewer) を clone して `uv tool install <clone先>` でインストールする
  (`~/.local/bin` に入る)

### R

- R と以下のパッケージ
  - 訓練経過(`monitor/`): `tidyverse`, `data.table`, `ggh4x`
  - 本解析(`analysis/`): 上記に加えて `arrow`, `glmnet`, `viridis`, `future.apply`, `progressr`,
    `utexr`(GitHub の `7cm-diameter/utexr` から `remotes::install_github("7cm-diameter/utexr")` などで入れる)

### 日次自動化(`monitor/daily.sh`)で使うシステムのコマンド

Ubuntu(GNOME)を想定。

| コマンド | 用途 | Ubuntu のパッケージ |
|---|---|---|
| `gio` | NAS(SMB)のマウント | `gvfs-backends`(GNOMEなら通常入っている) |
| `systemd-run`, `systemctl --user` | 定期実行と通知の常駐 | systemd |
| `flock` | 多重起動の防止 | `util-linux` |
| `/usr/bin/python3` + libnotify | クリックでフォルダを開ける通知 | `python3-gi`, `gir1.2-notify-0.7` |
| `notify-send` | 上記が使えないときの予備の通知 | `libnotify-bin` |

## 設定ファイル

以下は環境ごとに異なるため git 管理外。clone したら作成する。

| ファイル | 内容 | 作り方 |
|---|---|---|
| `config/monitor.env` | NAS の場所など、`daily.sh` の環境設定 | `config/monitor-sample.env` をコピーして書き換える |
| `default.yaml` | `detect` のパラメータ設定(サンプリング周波数、検出するチャンネルなど) | 既存の環境からコピーする |
| `group.toml` | 個体の群分け | 下記の形式で作成する(`uv run merge` 時に未登録の個体がいると対話で追記される) |
| `config/train.yaml`, `config/test.yaml` | 実験制御のパラメータ | `config/*-sample.yaml` をコピーする |

`config/monitor.env` の項目(bash から `source` される):

| 変数 | 内容 |
|---|---|
| `NAS_URI` | tdms が保存されている SMB 共有(例: `smb://fnas.local/fnas_local/`) |
| `NAS_DIR` | マウント後の tdms のあるディレクトリ(GVFS のマウント先) |
| `DETECT_CONFIG` | `detect` の設定ファイル。相対パスはプロジェクトのルートから |

`group.toml` の形式:

```toml
single = ["G12M0", "G13M3"]
multi = ["G12F1", "G12F2"]
```

## 訓練経過の処理(`monitor/`)

tdms(NAS上)→ binary csv → 前処理 → 作図 の順に処理する。

### データの置き場所

| パス | 内容 |
|---|---|
| `data/behavior/*_binary.csv` | tdms から変換した binary csv(1セッション1ファイル) |
| `data/monitor/recent.csv` | 個体ごとに直近10セッションの生イベント(raster 用) |
| `data/monitor/summary.csv` | 全セッションの、刺激×時間窓ごとの平均 lick rate |
| `fig/monitor/{実験日}/` | raster / progress / psychometric の図と、その日の全個体の `progress-all.jpg` |
| `log/monitor/{日付}.log` | `daily.sh` のログ |

### 手動で実行する場合

```bash
# 1. tdms を binary csv に変換し、data/behavior/ に移す(RotaryA/RotaryB は常に除外)
detect <tdmsファイル...> default.yaml --exclude-events RotaryA RotaryB
mv <NAS上の>*_binary.csv data/behavior/

# 2. 前処理(未処理のセッションだけ追加する。再処理は --overwrite)
uv run merge

# 3. 作図(既存の図はスキップする。描き直しは --force)
Rscript src/flkl/monitor/draw_progress.R [subject ...] [--force]
```

### 日次自動化

`src/flkl/monitor/daily.sh` が、NAS のマウント → 未処理 tdms の検出 → `detect` → `data/behavior/` への移動 →
`merge` → 作図 を行う。新しいデータがなければ何もせず終了する。
完了・失敗時にはデスクトップ通知が出て、クリックすると図(失敗時はログ)のフォルダが開く。
17時以降の実行で当日のデータが1つもなければ、NAS への移行忘れの可能性として通知する。

systemd user timer で毎時起動する。以下の2ファイルを `~/.config/systemd/user/` に作成する
(`ExecStart` のパスは clone 先に合わせる)。

`flkl-monitor.service`:

```ini
[Unit]
Description=flkl: detect, merge and draw new behavior data on NAS

[Service]
Type=oneshot
ExecStart=/usr/bin/bash /path/to/flkl/src/flkl/monitor/daily.sh
TimeoutStartSec=2h
```

`flkl-monitor.timer`:

```ini
[Unit]
Description=Run flkl-monitor hourly from 9:00 to 17:00

[Timer]
OnCalendar=*-*-* 09..17:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now flkl-monitor.timer

systemctl --user start flkl-monitor.service   # 今すぐ1回実行する
systemctl --user list-timers flkl-monitor.timer  # 次回の実行予定
```

## 本解析(`analysis/`)

2pデータは `data/2p/{subject}-{date}/` に置く。各スクリプトはディレクトリ名から個体名と日付を取得し、
対応する行動データを `data/behavior/` から読み込む(`src/flkl/analysis/behavior_io.R`)。
実行方法は各スクリプトの先頭のコメントを参照。
