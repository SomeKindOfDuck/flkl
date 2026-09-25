#!/usr/bin/env bash
# NAS上の未処理tdmsを binary csv に変換し、merge と作図まで行う
#
# 新しいデータがなければ何もせず終了する。systemd user timer から毎時起動する想定。
# 環境に依存する設定(NASの場所など)は config/monitor.env から読み込む
# (config/monitor-sample.env をコピーして作成する。詳細は README 参照)。
# Usage: bash src/flkl/monitor/daily.sh

set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

PROJECT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
CONFIG_FILE="$PROJECT_DIR/config/monitor.env"
BEHAVIOR_DIR="$PROJECT_DIR/data/behavior"
LOG_DIR="$PROJECT_DIR/log/monitor"
# 記録・転送中のファイルを避けるため、最終更新からこの分数が経つまで処理しない
MIN_AGE_MIN=10
# この時刻以降の実行で当日のデータが1つもなければ、移行忘れの可能性として通知する
DEADLINE_HOUR=17

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d).log"
exec >>"$LOG_FILE" 2>&1

# 前の実行がまだ終わっていなければ終了する
exec 9>"$LOG_DIR/.lock"
if ! flock -n 9; then
    echo "[$(date '+%F %T')] [INFO] Previous run is still in progress."
    exit 0
fi

log() { echo "[$(date '+%F %T')] $*"; }
# 通知をクリックすると --open で指定したフォルダが開く(notify.py 参照)
# サービス終了後もクリックを受け付けられるよう、systemd-run で別ユニットとして起動する
# Usage: notify [-u critical] [--open PATH] MESSAGE
notify() {
    systemd-run --user --quiet --collect \
        /usr/bin/python3 "$PROJECT_DIR/src/flkl/monitor/notify.py" "$@" ||
        notify-send "flkl monitor" "${@: -1}" || true
}

check_today() {
    local today
    today="$(date +%Y%m%d)"
    (( 10#$(date +%H) < DEADLINE_HOUR )) && return 0
    compgen -G "$BEHAVIOR_DIR/*_${today}-*_binary.csv" >/dev/null && return 0
    log "[WARN] No data for $today by ${DEADLINE_HOUR}:00."
    notify -u critical --open "$NAS_DIR" "${DEADLINE_HOUR}時の時点で本日($today)のデータがありません。NASへの移行を確認してください。"
}

on_error() {
    log "[ERROR] Failed at line $1."
    notify --open "$LOG_DIR" "処理に失敗しました。ログを確認してください: $LOG_FILE"
}
trap 'on_error $LINENO' ERR

cd "$PROJECT_DIR"
log "[INFO] Start."

fail() {
    trap - ERR
    log "[ERROR] $1"
    notify --open "${2:-$LOG_DIR}" "処理を開始できませんでした: $1"
    exit 1
}

if [[ ! -f "$CONFIG_FILE" ]]; then
    fail "$CONFIG_FILE がありません。config/monitor-sample.env をコピーして作成してください。" "$PROJECT_DIR/config"
fi

# shellcheck source=/dev/null
source "$CONFIG_FILE"

for var in NAS_URI NAS_DIR DETECT_CONFIG; do
    [[ -n "${!var:-}" ]] || fail "$CONFIG_FILE に $var が設定されていません。" "$PROJECT_DIR/config"
done

[[ "$DETECT_CONFIG" = /* ]] || DETECT_CONFIG="$PROJECT_DIR/$DETECT_CONFIG"
[[ -f "$DETECT_CONFIG" ]] || fail "detect の設定ファイル $DETECT_CONFIG がありません。" "$PROJECT_DIR"

for cmd in detect uv Rscript gio systemd-run; do
    command -v "$cmd" >/dev/null || fail "コマンド $cmd が見つかりません。README の依存関係を確認してください。"
done

mkdir -p "$BEHAVIOR_DIR"

if [[ ! -d "$NAS_DIR" ]]; then
    log "[INFO] Mounting $NAS_URI"
    timeout 60 gio mount "$NAS_URI" </dev/null
fi

# binary csv が未作成で、十分古い tdms を列挙する
# 同一 subject/日付/セッション番号 が複数ある場合はサイズの大きい方を採用する
mapfile -t targets < <(
    find "$NAS_DIR" -maxdepth 1 -name '*.tdms' -mmin +"$MIN_AGE_MIN" -printf '%s\t%f\n' |
        while IFS=$'\t' read -r size name; do
            stem="${name%.tdms}"
            [[ -e "$BEHAVIOR_DIR/${stem}_binary.csv" ]] && continue
            # G12F2_Phase-01_40_20260924-091721 -> G12F2_Phase-01_40_20260924
            printf '%s\t%s\t%s\n' "${stem%-*}" "$size" "$name"
        done |
        sort -t $'\t' -k1,1 -k2,2nr |
        awk -F '\t' '!seen[$1]++ { print $3 }'
)

if [[ ${#targets[@]} -eq 0 ]]; then
    log "[INFO] No new data."
    check_today
    exit 0
fi

log "[INFO] New data: ${targets[*]}"

(cd "$NAS_DIR" && detect "${targets[@]}" "$DETECT_CONFIG" --exclude-events RotaryA RotaryB)

for name in "${targets[@]}"; do
    mv "$NAS_DIR/${name%.tdms}_binary.csv" "$BEHAVIOR_DIR/"
done

# 未登録 subject の対話プロンプトで止まらないよう stdin を閉じる(その場合はエラーになる)
uv run merge </dev/null

# 後から届いた個体を反映させるため、全体図だけ描き直す
latest_date=""
for name in "${targets[@]}"; do
    date_str="$(sed -E 's/.*_([0-9]{8})-[0-9]{6}\.tdms$/\1/' <<<"$name")"
    rm -f "fig/monitor/$date_str/progress-all.jpg"
    if [[ "$date_str" > "$latest_date" ]]; then
        latest_date="$date_str"
    fi
done

Rscript src/flkl/monitor/draw_progress.R

subjects="$(printf '%s\n' "${targets[@]}" | cut -d_ -f1 | sort -u | paste -sd ' ')"
log "[INFO] Done: $subjects"
notify --open "$PROJECT_DIR/fig/monitor/$latest_date" "処理が完了しました: $subjects"
check_today
