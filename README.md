# flkl

視覚・聴覚刺激(フリッカー)を用いた弁別課題の実験制御と解析。

`pj-yoneyama` は別の利用者・Windowsの解析環境を前提とする。
行動データの処理は `uv run monitor <TDMSファイル...>` で手動実行し、保存先は引数で指定する。

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

以下のコマンド例はプロジェクトのルートで実行する。コマンドに渡す相対パスは実行時のディレクトリを基準にする。

## 依存関係

### Python

- [uv](https://docs.astral.sh/uv/)。Pythonの依存パッケージは `uv sync` で入る(`pyproject.toml` 参照)
- `detect` コマンド: tdms を binary csv に変換する(`monitor` がそのあと parquet に変換する)。
  [TDMSViewer](https://github.com/7cm-diameter/TDMSViewer) を clone して `uv tool install <clone先>` でインストールする
  (`detect --help` が実行できるようPATHを設定する。実行ファイルは `monitor --detect-command` でも指定できる)

### R

- R と以下のパッケージ
  - 訓練経過(`monitor/`): `tidyverse`, `data.table`, `ggh4x`
  - 本解析(`analysis/`): 上記に加えて `arrow`, `glmnet`, `viridis`, `future.apply`, `progressr`,
    `utexr`(GitHub の `7cm-diameter/utexr` から `remotes::install_github("7cm-diameter/utexr")` などで入れる)

WindowsでRのインストール先がPATHにない場合は、`monitor --rscript "C:/Program Files/R/<version>/bin/Rscript.exe"` のように指定する。
`monitor --no-plot` ならRを使わず変換・集計まで実行する。

### 旧Linux向け一括処理(`monitor/daily.sh --manual`)で使うシステムのコマンド

以下は旧 `daily.sh` 専用。Windows向けの `uv run monitor` では使用しない。

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
| `default.yaml` または `--config` で指定したYAML | TDMSの検出設定(サンプリング周波数、閾値など) | `config/detect-sample.yaml` をコピーし、記録装置に合わせる |
| `<出力先>/group.toml` | 個体の群分け | 下記の形式で作成する。未登録の個体は対話で指定できる。既存ファイルを使う場合は `--group-config` で指定する |
| `config/train.yaml`, `config/test.yaml` | 実験制御のパラメータ | `config/*-sample.yaml` をコピーする |
| `config/monitor.env` | 旧Linux向け `daily.sh` のNAS設定 | 旧処理を使う場合だけ `config/monitor-sample.env` をコピーする |

`monitor` のTDMS検出設定は、明示した `--config PATH` を最優先する。
省略時は **flkl直下の `default.yaml`** を使い、それもなければ処理開始前にエラーにして `--config` の指定を求める。
実行時のディレクトリにたまたまある別の `default.yaml` は使用しない。
選択した設定ファイルの絶対パスを開始時に表示する。`train.yaml` とは別の設定なので、実験制御用YAMLを渡さないこと。

`fs` は記録のサンプリング周波数(Hz)、`threshold` はチャンネル別の `[ON閾値, OFF閾値]`、
`invert_y` は信号の反転、`debounce` は安定状態の判定に使うサンプル数。
例えば `fs: 2000` で `debounce.Lick: 20` は10 msに相当する。サンプルの値は記録装置に合わせて変更する。
TDMS内のチャンネル名と設定のキーを一致させ、検出対象の全チャンネルの設定を用意する。
RotaryA / RotaryB は従来どおり検出結果から除外する。

旧 `config/monitor.env` の項目(bashから `source` される。新しい `monitor` コマンドでは読まない):

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

### TDMSファイルを指定して実行する(Windows / Linux)

TDMSファイルを1つ以上引数で渡す。別々のフォルダのファイルもまとめて渡せる。
WindowsのPowerShellでの例(`flkl/default.yaml` があれば `--config` は省略できる):

```powershell
uv sync
uv run monitor "D:/recordings/M01_Phase-01_1_20261109-100000.tdms" "D:/recordings/M02_Phase-01_1_20261109-110000.tdms" --config "D:/settings/detect.yaml" --output-dir "D:/analysis/yoneyama"
```

ワイルドカードも使える。スペース・日本語を含むパスは引用符で囲む。

```powershell
uv run monitor "D:/実験データ/*.tdms" --output-dir "D:/解析結果/yoneyama"
```

入力TDMSはその場所から読み込み、生成物は `--output-dir` の下へ保存する(省略時は `./monitor-output/`)。
`detect` → parquet変換 → 集計 → Rで作図、の順に処理する。NASのマウント・Bash・定期実行の設定は不要。
指定したセッションを再計算して集計へ反映し、他のセッションの集計を保持する。図は集計結果から更新する。
既存の群設定を利用する場合は `--group-config "D:/settings/group.toml"` を追加する。

出力先の構成:

```text
<出力先>/
├── binary/*_binary.parquet  # TDMSごとのイベント(event, time)
├── recent.csv              # 個体ごとの直近10セッション
├── summary.csv             # 刺激×時間窓ごとの平均lick rate
├── group.toml              # --group-config を省略した場合の群設定
└── fig/{実験日}/           # raster / progress / psychometric / progress-all
```

ファイル名の形式は従来の `{subject}_{phase}_{session}_{YYYYMMDD}-{HHMMSS}.tdms` を使う。
現在の集計は同じ個体・同じ日を1セッションとして扱う。同一個体・同一日の別ファイルを同時に指定した場合や、
別フォルダにある同名のファイルを指定した場合は、処理前にエラーにする。
解析窓(刺激2秒、試行境界の間隔5秒)や達成基準は従来のままなので、実験条件を変える場合は別途調整が必要。

### 個別に実行する場合

```powershell
detect <TDMSファイル...> <検出設定.yaml> --output <CSV出力先> --exclude-events RotaryA RotaryB
uv run python -m flkl.monitor.to_parquet <binary.csvファイル...> --outdir <parquet出力先>
uv run merge --input-dir <parquet出力先> --output-dir <集計出力先> --group-config <群設定.toml>
Rscript src/flkl/monitor/draw_progress.R --data-dir <集計出力先> --figure-dir <図の出力先>
```

### 旧Linux向け一括処理

`pj-yoneyama` では monitor の定期的な自動処理を無効にしている。
既存の systemd timer が `daily.sh` を引数なしで呼んでも、設定の読み込み・ログ作成・NAS へのアクセス前に正常終了する。
タイマー自体の設定はPC側に残るため、別ブランチに切り替えた場合の動作は、そのブランチの `daily.sh` に従う。
旧環境で一連の処理を1回実行するには、明示的に `--manual` を付ける。

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
新しい `monitor` のイベント出力は `<出力先>/binary/` にある。これを `data/behavior/` に配置するか、
`read_behavior_data()` の `behavior_dir` と `group_config` に利用環境のパスを渡す。
2p解析の各スクリプトは従来の配置を前提とする箇所があるため、新しい利用者の構成に合わせて呼び出し元も調整する。
実行方法は各スクリプトの先頭のコメントを参照。
