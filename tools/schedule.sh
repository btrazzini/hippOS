#!/bin/bash
# macOS: runs /sleep every day at a set hour through launchd, in a Claude Code session with no window,
# even with the Claude app closed. The Mac's clock sets the hour; if the Mac is asleep then, it runs on wake.
#   tools/schedule.sh install [HH:MM]   schedule it (default 03:00); run again to change the hour
#   tools/schedule.sh status            whether it is scheduled, and the last run
#   tools/schedule.sh now               run it now, through launchd
#   tools/schedule.sh check             test everything except the sleep itself (Claude, Drive, pending)
#   tools/schedule.sh remove            unschedule it
# Each run leaves a log in ~/Library/Logs/hippOS/ and a notification with the first line of sleep's reply.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="hippos.sleep"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/Library/Logs/hippOS"
DOMAIN="gui/$(id -u)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin"

notify() {
  osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' -e 'end run' \
    "$1" "$2" >/dev/null 2>&1 || true
}

# claude on the PATH, else the newest copy bundled with the Claude desktop app (its path changes with each update).
find_claude() {
  command -v claude && return
  ls -d "$HOME/Library/Application Support/Claude/claude-code"/*/*/claude.app/Contents/MacOS/claude 2>/dev/null | sort -V | tail -1
}

# Drive and the network may take a while to come back after the Mac wakes: wait up to 10 minutes.
find_root() {
  local root
  for _ in $(seq 20); do
    root=$(python3 "$REPO/tools/memory.py" root 2>/dev/null)
    if [ -n "$root" ] && [ -d "$root" ] && curl -s -o /dev/null -m 10 https://api.anthropic.com; then
      echo "$root"; return
    fi
    sleep 30
  done
}

run() {  # what launchd calls; "check" stops before the sleep
  mkdir -p "$LOGDIR"
  find "$LOGDIR" -name 'sleep-*' -mtime +30 -delete 2>/dev/null
  local stamp log json claude root code summary
  stamp=$(date +%Y-%m-%d-%H%M)
  log="$LOGDIR/sleep-$stamp.log"; json="$LOGDIR/sleep-$stamp.json"
  [ "${1:-}" = check ] || exec >>"$log" 2>&1
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ${1:-run}"
  claude=$(find_claude)
  [ -x "$claude" ] || { echo "Claude Code not found"; notify "hippOS sleep" "Claude Code not found"; exit 1; }
  echo "claude: $claude ($("$claude" --version))"
  root=$(find_root)
  [ -n "$root" ] || { echo "Drive or network unavailable"; notify "hippOS sleep" "Drive or network unavailable, sleep did not run"; exit 1; }
  echo "root: $root"
  python3 "$REPO/tools/memory.py" pending "$root"
  [ "${1:-}" = check ] && { echo "check ok"; exit 0; }

  # The model and effort in the sleep skill's frontmatter; auto: no one is there to answer a permission prompt.
  cd "$REPO" || exit 1
  caffeinate -i "$claude" -p "/sleep" --model opus --effort medium --permission-mode auto \
    --add-dir "$root" --add-dir "$HOME/.cache/hippos-sleep" \
    --name "hippOS sleep $(date +%Y-%m-%d)" --output-format json </dev/null >"$json"
  code=$?
  python3 - "$json" <<'EOF'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read()
try:
    d = json.loads(raw)
except ValueError as e:
    sys.exit(print(f"unreadable output ({e}):\n{raw[:2000]}"))
print(d.get("result", ""))
print(f"\nsession {d.get('session_id')} (claude --resume), models {list(d.get('modelUsage', {}))}, cost {d.get('total_cost_usd')}")
EOF
  summary=$(python3 -c 'import json, sys; print((json.load(open(sys.argv[1])).get("result") or "").strip().splitlines()[0][:200])' "$json" 2>/dev/null)
  if [ $code -eq 0 ]; then notify "hippOS sleep done" "${summary:-see $log}"; else notify "hippOS sleep failed" "exit $code, see $log"; fi
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') end (exit $code)"
  exit $code
}

install() {
  local at="${1:-03:00}" hour minute
  [[ "$at" =~ ^([01]?[0-9]|2[0-3]):([0-5][0-9])$ ]] || { echo "hour as HH:MM, e.g. 03:00"; exit 2; }
  hour=$((10#${BASH_REMATCH[1]})); minute=$((10#${BASH_REMATCH[2]}))
  [ -x "$(find_claude)" ] || { echo "Claude Code not found: install it or the Claude desktop app"; exit 1; }
  python3 "$REPO/tools/memory.py" root >/dev/null || { echo "hippOS folder not found in Google Drive: run /configure first"; exit 1; }
  mkdir -p "$(dirname "$PLIST")" "$LOGDIR"
  cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>$LABEL</string>
	<key>ProgramArguments</key>
	<array><string>/bin/bash</string><string>$REPO/tools/schedule.sh</string><string>run</string></array>
	<key>StartCalendarInterval</key>
	<dict><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$minute</integer></dict>
	<key>StandardOutPath</key><string>$LOGDIR/launchd.log</string>
	<key>StandardErrorPath</key><string>$LOGDIR/launchd.log</string>
	<key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null
  launchctl bootstrap "$DOMAIN" "$PLIST" || exit 1
  printf 'scheduled: /sleep every day at %02d:%02d (the Mac'"'"'s clock); logs in %s\n' "$hour" "$minute" "$LOGDIR"
}

status() {
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval' "$PLIST" | awk '/Hour/{h=$3} /Minute/{m=$3} END{printf "scheduled: every day at %02d:%02d\n", h, m}'
  else
    echo "not scheduled"
  fi
  local last; last=$(ls -t "$LOGDIR"/sleep-*.log 2>/dev/null | head -1)
  if [ -n "$last" ]; then echo "last run: $last"; tail -3 "$last"; fi
}

[ "$(uname)" = Darwin ] || { echo "macOS only; elsewhere, schedule /sleep with /configure"; exit 1; }
case "${1:-}" in
  install) install "${2:-}" ;;
  remove) launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null; rm -f "$PLIST"; echo "unscheduled" ;;
  status) status ;;
  now) launchctl kickstart "$DOMAIN/$LABEL" && echo "running; log in $LOGDIR" ;;
  check) run check ;;
  run) run ;;
  *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
