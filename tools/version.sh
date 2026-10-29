#!/bin/bash
# Bumps the hippOS version everywhere (tools/version.sh 0.2.1); with no argument, only checks.
# Also checks the rules budget: what the assistant and sleep read every session has a ceiling, and
# for a rule to come in another one leaves or merges (AGENTS.md, "Budget").
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
WORD_LIMIT=5000
RULES="system/protocol.md skills/assistant/SKILL.md skills/sleep/SKILL.md"
words=$(cat $RULES | wc -w | tr -d ' ')
if [ "$words" -gt "$WORD_LIMIT" ]; then
  echo "budget exceeded: $words words in the rules (limit $WORD_LIMIT); drop or merge a rule before bumping the version"
  exit 1
fi
if [ $# -eq 1 ]; then
  new="$1"
  [[ "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "invalid version: $new"; exit 2; }
  echo "$new" > system/VERSION
  perl -pi -e "s/^version: .*/version: $new/" system/protocol.md
  perl -pi -e "s/\(v[0-9]+\.[0-9]+\.[0-9]+\)/(v$new)/" skills/assistant/SKILL.md skills/sleep/SKILL.md skills/configure/SKILL.md
  perl -pi -e "s/^VERSION = \".*\"/VERSION = \"$new\"/" tools/memory.py
fi
v="$(cat system/VERSION)"
err=0
check() { grep -q -- "$2" "$1" || { echo "out of version $v: $1"; err=1; }; }
check system/protocol.md "^version: $v$"
check skills/assistant/SKILL.md "(v$v)"
check skills/sleep/SKILL.md "(v$v)"
check skills/configure/SKILL.md "(v$v)"
check tools/memory.py "^VERSION = \"$v\"$"
[ $err -eq 0 ] && echo "version $v everywhere; rules at $words of $WORD_LIMIT words"
exit $err
