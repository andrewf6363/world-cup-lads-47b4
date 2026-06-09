#!/usr/bin/env python3
"""Post the daily recap to the lads' iMessage chat (runs on Andrew's Mac only —
Apple allows no cloud path into iMessage).

Reads the LIVE dashboard (so it posts exactly what friends see), composes a short
recap, dedupes against the last post, and sends via Messages.app.

Setup once:  python3 scripts/setup_imessage.py     (pick the chat -> ~/.wc26-imessage.json)
Test:        python3 scripts/post_imessage.py --test       (sends a fixed hello message)
Preview:     python3 scripts/post_imessage.py --dry-run    (prints, sends nothing)
Run:         python3 scripts/post_imessage.py [--force]
Schedule:    launchd plist com.wc26.recap fires this nightly at 10:45 PM (see README).
"""
import json, os, re, subprocess, sys, hashlib, urllib.request

URL = "https://andrewf6363.github.io/world-cup-lads-47b4/"
CFG = os.path.expanduser("~/.wc26-imessage.json")
STATE = os.path.expanduser("~/.wc26-imessage-state")

SEND_SCRIPT = '''on run argv
tell application "Messages" to send (item 1 of argv) to chat id (item 2 of argv)
end run'''


def fetch_data():
    html = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8")
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    if not m:
        sys.exit("could not find the DATA blob on the live page — is the site up?")
    return json.loads(m.group(1))


def compose(d):
    """Recap message + dedupe key. Returns (None, None) until the tournament starts."""
    daily, players, meta = d.get("daily"), d.get("players", []), d.get("meta", {})
    if not daily or not meta.get("started"):
        return None, None
    lines = [f"WORLD CUP LADS — {daily.get('headline','')}", daily.get("line", "")]
    lines += [f"- {i}" for i in daily.get("items", [])]
    if players:
        lines += ["", "Top of the table:"]
        lines += [f"{p['rank']}. {p['name']} — {p['total']:,} pts" for p in players[:3]]
    lines += ["", f"Full table: {URL}"]
    key = hashlib.sha256((daily.get("headline", "") + daily.get("line", "")
                          + "|".join(daily.get("items", []))).encode()).hexdigest()[:16]
    return "\n".join(lines), key


def send(msg, chat_id):
    r = subprocess.run(["osascript", "-e", SEND_SCRIPT, msg, chat_id],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("send failed: " + r.stderr.strip()
                 + "\nFix: System Settings -> Privacy & Security -> Automation -> allow Messages,"
                 + "\nor re-run setup_imessage.py if the chat id changed.")


def main():
    args = set(sys.argv[1:])
    dry, force, test = "--dry-run" in args, "--force" in args, "--test" in args
    if test:
        msg, key = ("World Cup Lads — recap bot is wired up. Daily recaps land here "
                    "once the matches kick off June 11. " + URL), None
    else:
        msg, key = compose(fetch_data())
        if not msg:
            print("no recap to post yet (tournament hasn't started)"); return
        last = open(STATE).read().strip() if os.path.exists(STATE) else ""
        if key == last and not force:
            print("recap unchanged since last post — nothing to send"); return
    print(msg); print("-" * 44)
    if dry:
        print("(dry run — nothing sent)"); return
    if not os.path.exists(CFG):
        sys.exit("no chat configured — run: python3 scripts/setup_imessage.py")
    send(msg, json.load(open(CFG))["chat_id"])
    if key:
        open(STATE, "w").write(key)
    print("posted to iMessage")


if __name__ == "__main__":
    main()
