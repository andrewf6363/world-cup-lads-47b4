#!/usr/bin/env python3
"""One-time iMessage setup for the recap bot.

Lists your Messages chats, lets you pick the lads' group (or a chat with yourself,
for testing), and saves the chat id to ~/.wc26-imessage.json. Re-run anytime to repoint.
The first run will ask permission for Terminal to control Messages — click Allow.
"""
import json, os, subprocess, sys

CFG = os.path.expanduser("~/.wc26-imessage.json")

LIST_SCRIPT = '''set out to ""
tell application "Messages"
  repeat with c in chats
    set nm to ""
    try
      set nm to name of c
      if nm is missing value then set nm to ""
    end try
    set out to out & (id of c) & "|||" & nm & "@@@"
  end repeat
end tell
return out'''


def main():
    print("Reading your Messages chats (grant permission if macOS asks)...")
    r = subprocess.run(["osascript", "-e", LIST_SCRIPT], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Couldn't read Messages chats: " + r.stderr.strip()
                 + "\nFix: System Settings -> Privacy & Security -> Automation ->"
                 + " allow Terminal to control Messages, then re-run.")
    chats = [c.split("|||") for c in r.stdout.strip().split("@@@") if c.strip() and "|||" in c]
    if not chats:
        sys.exit("No chats found — open Messages.app, make sure you're signed in, and re-run.")
    chats.sort(key=lambda c: c[1] == "")          # named (group) chats first
    print(f"\nFound {len(chats)} chats — group chats (named) listed first:\n")
    for i, (cid, nm) in enumerate(chats, 1):
        print(f"  {i:>3}. {(nm or '(no name — 1:1 chat)'): <38} {cid[:48]}")
    n = input("\nNumber of the chat to post recaps to (the lads' group — or yourself, to test): ").strip()
    try:
        cid = chats[int(n) - 1][0]
    except (ValueError, IndexError):
        sys.exit("Not a valid number — re-run and pick from the list.")
    json.dump({"chat_id": cid}, open(CFG, "w"), indent=2)
    print(f"\nSaved -> {CFG}")
    print("Test it:    python3 scripts/post_imessage.py --test")
    print("Preview:    python3 scripts/post_imessage.py --dry-run")


if __name__ == "__main__":
    main()
