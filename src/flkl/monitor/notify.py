"""デスクトップ通知を表示し、クリックで指定したフォルダを開けるようにする

notify-send(0.7.9)はアクションに対応していないため、libnotifyを直接使う。
アクションを受け取るため、通知が閉じられるか MAX_LIFETIME_SEC が経過するまで常駐する。
systemdのoneshotサービスから呼ぶ場合、サービス終了時に一緒に止められないよう
systemd-run --user で別ユニットとして起動すること。

Usage: /usr/bin/python3 notify.py [-u {low,normal,critical}] [--open PATH] MESSAGE
"""

import argparse
import subprocess

import gi

gi.require_version("Notify", "0.7")
from gi.repository import GLib, Notify  # noqa: E402

SUMMARY = "flkl monitor"
MAX_LIFETIME_SEC = 12 * 60 * 60

URGENCY = {
    "low": Notify.Urgency.LOW,
    "normal": Notify.Urgency.NORMAL,
    "critical": Notify.Urgency.CRITICAL,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Show a desktop notification.")
    parser.add_argument("message")
    parser.add_argument("-u", "--urgency", choices=URGENCY, default="normal")
    parser.add_argument("--open", dest="open_path", help="Folder opened by clicking the notification")
    args = parser.parse_args()

    Notify.init(SUMMARY)
    loop = GLib.MainLoop()

    notification = Notify.Notification.new(SUMMARY, args.message)
    notification.set_urgency(URGENCY[args.urgency])

    if args.open_path:
        def open_folder(_notification, action):
            print(f"Action '{action}': open {args.open_path}", flush=True)
            # 終了するとsystemdに子プロセスごと止められるため、xdg-openの終了を待つ
            subprocess.run(["xdg-open", args.open_path], timeout=30, check=False)
            loop.quit()

        # "default"は通知本体のクリックに対応する
        notification.add_action("default", "開く", open_folder)
        notification.add_action("open", "フォルダを開く", open_folder)

    def on_closed(*_):
        print(f"Closed (reason={notification.get_closed_reason()})", flush=True)
        loop.quit()

    notification.connect("closed", on_closed)
    notification.show()

    if not args.open_path:
        return

    GLib.timeout_add_seconds(MAX_LIFETIME_SEC, loop.quit)
    loop.run()


if __name__ == "__main__":
    main()
