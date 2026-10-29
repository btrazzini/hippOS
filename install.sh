#!/bin/bash
# Links the hippOS skills into Claude Code (~/.claude/skills) and Codex (~/.agents/skills and ~/.codex/skills).
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$REPO/tools/memory.py" "$REPO/tools/lookup.py"
for target in "$HOME/.claude/skills" "$HOME/.agents/skills" "$HOME/.codex/skills"; do
  mkdir -p "$target"
  for skill in assistant sleep configure; do
    link="$target/$skill"
    if [ -e "$link" ] && [ ! -L "$link" ]; then
      echo "skipped $link: it exists and is not a link"; continue
    fi
    if [ -L "$link" ] && [ "$(readlink "$link")" != "$REPO/skills/$skill" ]; then
      echo "skipped $link: it links to $(readlink "$link"); remove it to install hippOS's $skill"; continue
    fi
    ln -sfn "$REPO/skills/$skill" "$link"
    echo "ok $link -> $REPO/skills/$skill"
  done
done
echo "Done. Update with: git -C \"$REPO\" pull upstream main"
