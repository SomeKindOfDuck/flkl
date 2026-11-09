# flkl

視覚・聴覚刺激(フリッカー)を用いた弁別課題の実験制御と解析。

```
src/flkl/
├── bhv/        # 実験制御(uv run train / test / blink)
├── monitor/    # 訓練経過の前処理・作図(手動実行)
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
- `detect` コマンド: tdms を binary csv に変換する(`daily.sh` がそのあと parquet に変換する)。
  [TDMSViewer](https://github.com/7cm-diameter/TDMSViewer) を clone して `uv tool install <clone先>` でインストールする
  (`~/.local/bin` に入る)

### R

- R と以下のパッケージ
  - 訓練経過(`monitor/`): `tidyverse`, `data.table`, `ggh4x`
  - 本解析(`analysis/`): 上記に加えて `arrow`, `glmnet`, `viridis`, `future.apply`, `progressr`,
    `utexr`(GitHub の `7cm-diameter/utexr` から `remotes::install_github("7cm-diameter/utexr")` などで入れる)

### 手動の一括処理(`monitor/daily.sh --manual`)で使うシステムのコマンド

Ubuntu(GNOME)を想定。

| コマンド | 用途 | Ubuntu のパッケージ |
|---|---|---|
| `gio` | NAS(SMB)のマウント | `gvfs-backends`(GNOMEなら通常入っている) |
| `systemd-run` | 通知の常駐 | systemd |
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
| `NAS_DIR` | マウント後の行動データのディレクトリ(GVFS のマウント先。`Yamada_data/bhv`)。この下の `tdms/` と `parquet/` を使う |
| `NAS_TDMS_DIR`, `NAS_PARQUET_DIR` | (省略可)tdms と binary parquet の置き場所。既定は `$NAS_DIR/tdms`、`$NAS_DIR/parquet` |
| `SYNC_2P_BEHAVIOR` | (省略可)`1` にすると、2p のデータがある日の binary parquet を `data/behavior/` にコピーする。既定は `0`(コピーしない) |
| `DETECT_CONFIG` | `detect` の設定ファイル。相対パスはプロジェクトのルートから |

`group.toml` の形式:

```toml
single = ["G12M0", "G13M3"]
multi = ["G12F1", "G12F2"]
```

## フリッカーのパルス幅 (`train` / `test`)

`Experimental.flickr-on-ratio` は、刺激提示時間に対する合計ON時間の割合。省略時は `0.28`。
`flickr-duration: 2.`、`flickr-on-ratio: 0.28` なら、どの周波数でも合計560 msだけONになる。
例えば4 Hzでは約70 ms、14 Hzでは20 ms、20 Hzでは14 ms／パルス。
`0.5` にすると2秒提示中の合計ON時間は1秒になる。値は0より大きく1より小さくする。

視覚・聴覚それぞれについて合計ON時間を揃える。非同期提示でも各チャンネルのHzから幅を決める。
周期が提示時間に収まりきらない場合は末尾のパルスを考慮し、ON時間の配分を調整する。
Arduino側はマイクロ秒単位でパルス幅の端数を分配し、刺激開始を基準に切り替え時刻を決める。
実際の出力精度はArduinoの時計分解能・実行時間に依存する。
使用した `flickr-on-ratio` は、省略時の既定値も含めて開始時の設定ログに保存する。

Pythonと `ino/` は同じ版を使うこと。`train` / `test` は起動時にスケッチをアップロードする。
装置を動かさない検証は `uv run python -m unittest discover -s tests -v` (g++が必要)。

## training の刺激と報酬

`Experimental` に視覚・聴覚それぞれの「報酬あり」「報酬なし」のHzを直接列挙する。
例えば以下は、視覚14 Hzが報酬あり・4 Hzが報酬なし、聴覚12 Hzと15 Hzは両方とも報酬あり。

```yaml
Experimental:
  visual-rewarded: [14]
  visual-non-rewarded: [4]
  audio-rewarded: [12, 15]
  audio-non-rewarded: []
```

報酬はlickの有無によらず、刺激提示終了直後に `reward-pin` へ `reward-duration` 秒間出す。
空の `[]` または省略した分類からは試行を生成しない。
上の例では聴覚単独の無報酬試行はゼロ。視覚の2リストを空にすれば、聴覚単独だけの訓練になる。
同じモダリティの報酬あり・なしに同じHzを重複指定するとエラーにする。
視聴覚同期試行は `visual-*` の周波数と報酬区分に従い、同じHzを視覚・聴覚に提示する。

各周波数の基本試行数は `trials-per-stimulus`。視覚単独・同期では報酬ありに `reward-ratio`、
報酬なしに `extinction-ratio` を掛け、さらに `visual-ratio` / `sync-ratio` を掛ける。
聴覚単独では各周波数に `audio-ratio` を掛ける。
使用した4分類は、省略した項目の `[]` も含めて設定ログに保存する。

旧形式の `rewarded-frequency` / `extinction-frequency` / `audio-frequency` /
`audio-rewarded-frequency` も読み込める。旧 `audio-frequency` は全聴覚刺激の一覧として扱い、
報酬の有無で2リストへ変換する。新旧の刺激設定を同じYAML内に混在させるとエラーにする。

## 訓練経過の処理(`monitor/`)

tdms(NAS上)→ binary parquet(NAS上)→ 前処理 → 作図 の順に処理する。

### データの置き場所

| パス | 内容 |
|---|---|
| NAS `bhv/tdms/*.tdms` | 行動実験の tdms。`bhv/` 直下に置いたものは `daily.sh` がここに移す |
| NAS `bhv/parquet/*_binary.parquet` | tdms から変換した binary parquet(1セッション1ファイル、列は `event`, `time`)。行動データの正本 |
| `data/behavior/*_binary.parquet` | 本解析用のコピー。`SYNC_2P_BEHAVIOR=1` のとき、2p のデータがある日(`data/2p/{subject}-{date}/`)の分だけ `daily.sh` が NAS からコピーする |
| `data/monitor/recent.csv` | 個体ごとに直近10セッションの生イベント(raster 用) |
| `data/monitor/summary.csv` | 全セッションの、刺激×時間窓ごとの平均 lick rate |
| `fig/monitor/{実験日}/` | raster / progress / psychometric の図と、その日の全個体の `progress-all.jpg` |
| `log/monitor/{日付}.log` | `daily.sh` のログ |

### 手動で実行する場合

```bash
# 1. tdms を binary csv に変換し(NAS の bhv/tdms/ で実行。RotaryA/RotaryB は常に除外)、parquet にして bhv/parquet/ に置く
detect <tdmsファイル...> default.yaml --exclude-events RotaryA RotaryB
uv run python -m flkl.monitor.to_parquet <*_binary.csv...> --outdir <NAS の bhv/parquet> --remove

# 2. 前処理(未処理のセッションだけ追加する。再処理は --overwrite)
uv run merge --input-dir <NAS の bhv/parquet>

# 3. 作図(既存の図はスキップする。描き直しは --force)
Rscript src/flkl/monitor/draw_progress.R [subject ...] [--force]
```

### 手動で一括実行する場合

`pj-yoneyama` では monitor の定期的な自動処理を無効にしている。
既存の systemd timer が `daily.sh` を引数なしで呼んでも、設定の読み込み・ログ作成・NAS へのアクセス前に正常終了する。
タイマー自体の設定はPC側に残るため、別ブランチに切り替えた場合の動作は、そのブランチの `daily.sh` に従う。
変換・集計・作図のコードと、上記の個別コマンドはそのまま使用できる。

一連の処理を1回実行するには、明示的に `--manual` を付ける。

```bash
bash src/flkl/monitor/daily.sh --manual
```

このコマンドが、NAS のマウント → `bhv/` 直下の tdms を `bhv/tdms/` へ移動 → 未処理 tdms の検出 → `detect` →
parquet への変換(`bhv/parquet/` に置く)→ `merge`(出力はローカルの `data/monitor/`)→ 作図 を行う。
新しいデータがなければ変換・merge・作図はしない。`SYNC_2P_BEHAVIOR=1` のときは、2p のデータがある日の binary parquet の `data/behavior/` へのコピーを毎回確かめる。
完了・失敗時にはデスクトップ通知が出て、クリックすると図(失敗時はログ)のフォルダが開く。
17時以降の実行で当日のデータが1つもなければ、NAS への移行忘れの可能性として通知する。

## 本解析(`analysis/`)

2pデータは `data/2p/{subject}-{date}/` に置く。各スクリプトはディレクトリ名から個体名と日付を取得し、
対応する行動データを `data/behavior/` から読み込む(`src/flkl/analysis/behavior_io.R`。`*_binary.parquet` を優先し、なければ `*_binary.csv`)。
`data/behavior/` のファイルは手動で用意する。`SYNC_2P_BEHAVIOR=1` に設定して
`daily.sh --manual` を実行すると、`data/2p/` にディレクトリがある日の分を NAS からコピーできる。
実行方法は各スクリプトの先頭のコメントを参照。
