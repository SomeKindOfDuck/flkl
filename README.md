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

## Windowsで最初からセットアップする

Windows 10 / 11 (x64) のPowerShellで、以下を順番に実行する。
`powershell` と書かれたコードはPowerShellへ、`r` と書かれたコードはRのコンソールへ入力する。
初回はパッケージをダウンロードするためインターネット接続が必要。
例の `D:/recordings`、`D:/analysis` などは、利用者のデータ・保存先に置き換える。

### 1. uvとGitをインストールする

スタートメニューからPowerShellを開く。uvはPythonの準備とパッケージ管理に使う。
[uv公式のWindowsインストール手順](https://docs.astral.sh/uv/getting-started/installation/)に従い、次を実行する。

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Gitが入っていなければ、[Git公式のWindows案内](https://git-scm.com/install/windows)にあるインストーラー、
または次のコマンドでインストールする。`winget` が見つからない場合はインストーラーを使う。

```powershell
winget install --id Git.Git -e --source winget
```

**PowerShellを閉じて開き直し**、両方のバージョンが表示されることを確認する。

```powershell
uv --version
git --version
```

### 2. pj-yoneyamaを取得する

配布元に `pj-yoneyama` ブランチが共有されていることが前提。
以下はユーザーフォルダ内の `Projects/flkl` に取得する例。保存場所は変えてよい。

```powershell
$flklWorkspace = Join-Path $env:USERPROFILE "Projects"
New-Item -ItemType Directory -Force -Path $flklWorkspace | Out-Null
Set-Location $flklWorkspace
git clone --branch pj-yoneyama https://github.com/SomeKindOfDuck/flkl.git flkl
Set-Location .\flkl
git branch --show-current
```

最後に `pj-yoneyama` と表示されることを確認する。
GitHubの認証やアクセス権を求められる場合、配布元から利用者のアカウントへ権限を付与してもらう。
すでにこのブランチのフォルダを受け取っている場合は、そのフォルダへ `Set-Location` して次へ進む。

**以降のPowerShellコマンドは、特記がなければflkl直下で実行する。**
相対パスは実行時のディレクトリを基準にする。

### 3. Pythonとflklの依存パッケージを準備する

flklは [.python-version](.python-version) でPython 3.10を指定している。
TDMSViewerにはPython 3.12以降が必要なので、ここでは両方をuvで用意する。
uvは[複数のPythonを管理できる](https://docs.astral.sh/uv/guides/install-python/)。

```powershell
uv python install 3.10 3.12
uv sync --locked
uv run --locked monitor --help
```

`uv sync --locked` は [uv.lock](uv.lock) のバージョンでflklの依存パッケージを入れる。
`utex` とその依存関係もこの段階で取得される。Gitが必要なのはそのためでもある。
`uv run` がflkl内の `.venv` を使うため、手動で仮想環境を有効化する操作は不要。
`monitor --help` にTDMSファイルや `--config` の説明が表示されれば、この段階は完了。

### 4. TDMSViewerをインストールする

TDMSをイベント列へ変換する `detect` は、[TDMSViewer](https://github.com/7cm-diameter/TDMSViewer) が提供する。
flkl直下から実行して、隣の `TDMSViewer` フォルダに取得する。

```powershell
git clone https://github.com/7cm-diameter/TDMSViewer.git ../TDMSViewer
uv tool install --python 3.12 ../TDMSViewer
uv tool update-shell
```

[uv tool install](https://docs.astral.sh/uv/guides/tools/) はTDMSViewer専用のPython環境を作り、
`nptdms`、PyQtなどの依存関係と `detect` / `tdms-viewer` コマンドをまとめてインストールする。
flklの `.venv` とは別に管理される。

PowerShellを開き直してflklへ戻り、変換コマンドを確認する(保存場所を変えた場合はパスも変更する)。

```powershell
Set-Location (Join-Path $env:USERPROFILE "Projects/flkl")
detect --help
uv tool list
```

`detect --help` に `--output` と `--exclude-events` が表示されることを確認する。
GUIで波形や設定を確認するときは `tdms-viewer` で起動できる。

### 5. Rと作図用パッケージをインストールする

[CRANのWindows版R](https://cloud.r-project.org/bin/windows/base/)からR本体のインストーラーを取得してインストールする。
スタートメニューからRを起動し、**Rのコンソール**で次を実行する。

```r
install.packages(
  c("tidyverse", "data.table", "ggh4x"),
  repos = "https://cloud.r-project.org",
  type = "binary"
)
library(tidyverse)
library(data.table)
library(ggh4x)
file.path(R.home("bin"), "Rscript.exe")
```

[Windows用バイナリのパッケージ](https://stat.ethz.ch/R-manual/R-patched/library/utils/html/install.packages.html)を入れる手順。
個人用ライブラリの作成を尋ねられたら作成する。
3つの `library()` がエラーなく実行でき、最後に `Rscript.exe` の場所が表示されれば準備できている。

**PowerShellに戻り**、表示されたパスを次の変数に設定する。下の `R-4.x.y` は実際のフォルダ名へ置き換える。

```powershell
$flklRscript = "C:/Program Files/R/R-4.x.y/bin/Rscript.exe"
& $flklRscript --version
```

この変数を実行時の `--rscript` に渡す。PowerShellを開き直した場合は再度設定する。
すでに `Rscript --version` が通る環境では `--rscript` を省略できる。
変換・集計まで先に試す場合は `--no-plot` を指定するとRを使わず実行できる。

### 6. TDMSの検出設定を準備する

flkl直下の `default.yaml` がまだなければ、サンプルをコピーする。

```powershell
if (-not (Test-Path .\default.yaml)) {
    Copy-Item .\config\detect-sample.yaml .\default.yaml
}
notepad .\default.yaml
```

記録のサンプリング周波数 `fs`、チャンネル名、閾値、デバウンスを実際の装置に合わせ、保存する。
`default.yaml` はTDMSの検出用で、trainingの刺激・報酬設定とは別。
各項目と設定ファイルの選択順序は[設定ファイル](#設定ファイル)を参照。
別の場所に保存した場合は、実行コマンドに `--config "D:/settings/detect.yaml"` を追加する。

### 7. まず1ファイルを解析する

入力ファイル名と出力先を置き換えて実行する。

```powershell
uv run --locked monitor "D:/recordings/M01_Phase-01_1_20261109-100000.tdms" --output-dir "D:/analysis/yoneyama" --rscript $flklRscript
```

未登録の個体について `Choose group [single/multi]` と表示されたら、実験で決めた群を入力する。
結果は出力先の `group.toml` に保存され、次回から使われる。
完了後は `D:/analysis/yoneyama/summary.csv` と `D:/analysis/yoneyama/fig/` 以下の図を確認する。
複数ファイル・ワイルドカード・各種オプションは[訓練経過の処理](#訓練経過の処理monitor)を参照。

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

`group.toml` の形式(個体名は実際のTDMSファイル名に合わせる):

```toml
single = ["M01"]
multi = ["M02"]
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
WindowsのPowerShellでの例(`flkl/default.yaml` があれば `--config` は省略できる)。
`$flklRscript` はセットアップ手順5で設定した実行ファイルのパス。PATHにある場合は `--rscript` を省略できる。

```powershell
uv run --locked monitor "D:/recordings/M01_Phase-01_1_20261109-100000.tdms" "D:/recordings/M02_Phase-01_1_20261109-110000.tdms" --config "D:/settings/detect.yaml" --output-dir "D:/analysis/yoneyama" --rscript $flklRscript
```

ワイルドカードも使える。スペース・日本語を含むパスは引用符で囲む。

```powershell
uv run --locked monitor "D:/実験データ/*.tdms" --output-dir "D:/解析結果/yoneyama" --rscript $flklRscript
```

入力TDMSはその場所から読み込み、生成物は `--output-dir` の下へ保存する(省略時は `./monitor-output/`)。
`detect` → parquet変換 → 集計 → Rで作図、の順に処理する。NASのマウント・Bash・定期実行の設定は不要。
指定したセッションを再計算して集計へ反映し、他のセッションの集計を保持する。図は集計結果から更新する。
既存の群設定を利用する場合は `--group-config "D:/settings/group.toml"` を追加する。

| オプション | 用途・省略時の動作 |
|---|---|
| `--config PATH` | 検出設定YAML。省略時はflkl直下の `default.yaml`。両方なければ停止する |
| `--output-dir DIR` / `-o DIR` | 解析結果の保存先。省略時は実行ディレクトリ内の `monitor-output/` |
| `--group-config PATH` | 既存の群設定TOML。省略時は出力先の `group.toml` を使用・作成する |
| `--rscript PATH` | `Rscript.exe` の場所。省略時はPATHから探す |
| `--detect-command PATH` | `detect.exe` の場所。省略時はPATHから探す |
| `--no-plot` | Rによる作図を省き、変換・集計まで実行する |

Rを使わず変換・集計する場合:

```powershell
uv run --locked monitor "D:/recordings/*.tdms" --output-dir "D:/analysis/yoneyama" --no-plot
```

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

一括処理の各段階を別々に実行したい場合の例。通常は上記の `monitor` だけでよい。

```powershell
detect "D:/recordings/M01_Phase-01_1_20261109-100000.tdms" .\default.yaml --output "D:/analysis/csv" --exclude-events RotaryA RotaryB
uv run --locked python -m flkl.monitor.to_parquet "D:/analysis/csv/M01_Phase-01_1_20261109-100000_binary.csv" --outdir "D:/analysis/yoneyama/binary"
uv run --locked merge --input-dir "D:/analysis/yoneyama/binary" --output-dir "D:/analysis/yoneyama" --group-config "D:/analysis/yoneyama/group.toml"
& $flklRscript .\src\flkl\monitor\draw_progress.R --data-dir "D:/analysis/yoneyama" --figure-dir "D:/analysis/yoneyama/fig"
```

### コマンドが見つからない・処理が止まる場合

| 症状 | 確認すること |
|---|---|
| `uv` / `git` が見つからない | インストール後にPowerShellを開き直す。uvはインストーラーが表示した場所も確認する |
| `Remote branch pj-yoneyama not found` / GitHubへアクセスできない | 配布元にブランチが共有されているかと、利用者のアクセス権を確認する |
| `monitor` が見つからない | flkl直下で `git branch --show-current` を確認し、`uv sync --locked` を実行する |
| `Command not found: detect` | `uv tool list` に `tdms-viewer` があるか確認する。`uv tool update-shell` 後にPowerShellを開き直す |
| `Command not found: Rscript` | 手順5で調べた実在するパスを `--rscript` へ渡す。作図しない場合は `--no-plot` を使う |
| Rでパッケージがないと言われる | `--rscript` に指定したRと同じバージョンのコンソールで、手順5のパッケージをインストールする |
| `No default.yaml` / `Detection config does not exist` | flkl直下に `default.yaml` を作成するか、`--config` で実在するYAMLを指定する |
| `No TDMS file matched` | 入力の場所・拡張子を確認する。スペースや日本語を含むパスは引用符で囲む |
| `Invalid filename format` / `Multiple TDMS files for subject=...` | 上記の命名規則と、個体・日ごとに1セッションという制約を確認する |
| `detect` がチャンネルの設定で失敗する | TDMS内のチャンネル名とYAMLの `threshold` などが対応しているか確認する |

`detect` がPATHから見つからない場合は、uvが登録した実行ファイルを直接指定できる。

```powershell
$flklDetect = Join-Path (uv tool dir --bin) "detect.exe"
& $flklDetect --help
uv run --locked monitor "D:/recordings/*.tdms" --output-dir "D:/analysis/yoneyama" --detect-command $flklDetect --rscript $flklRscript
```

解析処理はLinuxで検証している。Windowsのインストールからの一連の操作は、実機ではまだ検証していない。

### 旧Linux向け一括処理

<details>
<summary>従来のUbuntu / GNOME環境でdaily.shを使う場合</summary>

`pj-yoneyama` では monitor の定期的な自動処理を無効にしている。
既存の systemd timer が `daily.sh` を引数なしで呼んでも、設定の読み込み・ログ作成・NAS へのアクセス前に正常終了する。
タイマー自体の設定はPC側に残るため、別ブランチに切り替えた場合の動作は、そのブランチの `daily.sh` に従う。
旧環境で一連の処理を1回実行するには、明示的に `--manual` を付ける。

この経路で必要なシステムコマンド:

| コマンド | 用途 | Ubuntu のパッケージ |
|---|---|---|
| `gio` | NAS(SMB)のマウント | `gvfs-backends` |
| `systemd-run` | 通知の常駐 | systemd |
| `flock` | 多重起動の防止 | `util-linux` |
| `/usr/bin/python3` + libnotify | クリックでフォルダを開ける通知 | `python3-gi`, `gir1.2-notify-0.7` |
| `notify-send` | 上記が使えないときの予備の通知 | `libnotify-bin` |

`config/monitor-sample.env` を `config/monitor.env` にコピーして環境に合わせる。
これはBashから `source` される設定で、新しい `monitor` コマンドでは読まない。

| 変数 | 内容 |
|---|---|
| `NAS_URI` | tdmsが保存されているSMB共有(例: `smb://fnas.local/fnas_local/`) |
| `NAS_DIR` | マウント後の行動データのディレクトリ。この下の `tdms/` と `parquet/` を使う |
| `NAS_TDMS_DIR`, `NAS_PARQUET_DIR` | (省略可)tdmsとbinary parquetの置き場所。既定は `$NAS_DIR/tdms`、`$NAS_DIR/parquet` |
| `SYNC_2P_BEHAVIOR` | (省略可)`1` なら2pデータのある日のbinary parquetを `data/behavior/` にコピーする。既定は `0` |
| `DETECT_CONFIG` | `detect` の設定ファイル。相対パスはプロジェクトのルートから |

```bash
bash src/flkl/monitor/daily.sh --manual
```

このコマンドが、NAS のマウント → `bhv/` 直下の tdms を `bhv/tdms/` へ移動 → 未処理 tdms の検出 → `detect` →
parquet への変換(`bhv/parquet/` に置く)→ `merge`(出力はローカルの `data/monitor/`)→ 作図 を行う。
新しいデータがなければ変換・merge・作図はしない。`SYNC_2P_BEHAVIOR=1` のときは、2p のデータがある日の binary parquet の `data/behavior/` へのコピーを毎回確かめる。
完了・失敗時にはデスクトップ通知が出て、クリックすると図(失敗時はログ)のフォルダが開く。
17時以降の実行で当日のデータが1つもなければ、NAS への移行忘れの可能性として通知する。

</details>

## 本解析(`analysis/`)

2pデータの解析も行う場合は、作図用パッケージに加えて以下をRのコンソールでインストールする。

```r
install.packages(
  c("arrow", "glmnet", "viridis", "future.apply", "progressr", "remotes"),
  repos = "https://cloud.r-project.org",
  type = "binary"
)
remotes::install_github("7cm-diameter/utexr", upgrade = "never")
```

上の `type = "binary"` はWindows用。Linuxでは省略してインストールする。

2pデータは `data/2p/{subject}-{date}/` に置く。各スクリプトはディレクトリ名から個体名と日付を取得し、
対応する行動データを `data/behavior/` から読み込む(`src/flkl/analysis/behavior_io.R`。`*_binary.parquet` を優先し、なければ `*_binary.csv`)。
新しい `monitor` のイベント出力は `<出力先>/binary/` にある。これを `data/behavior/` に配置するか、
`read_behavior_data()` の `behavior_dir` と `group_config` に利用環境のパスを渡す。
2p解析の各スクリプトは従来の配置を前提とする箇所があるため、新しい利用者の構成に合わせて呼び出し元も調整する。
実行方法は各スクリプトの先頭のコメントを参照。
