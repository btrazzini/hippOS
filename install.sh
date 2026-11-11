#!/bin/bash
# Claude Code: the skills load through .claude/skills, in sessions opened in this repository, the only ones where
# the Drive folder is allowed (memory.py allow) and the guard applies; so no link in ~/.claude/skills.
# Codex: links the skills into ~/.agents/skills and ~/.codex/skills.
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$REPO/tools/memory.py" "$REPO/tools/lookup.py" "$REPO/tools/guard.py"
for skill in assistant sleep configure protect; do
  link="$HOME/.claude/skills/$skill"
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$REPO/skills/$skill" ]; then
    rm "$link"; echo "removed $link: Claude Code loads $skill from this repository"
  fi
done
for target in "$HOME/.agents/skills" "$HOME/.codex/skills"; do
  mkdir -p "$target"
  for skill in assistant sleep configure protect; do
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
python3 "$REPO/tools/memory.py" allow || echo "Drive folder not allowed yet: run python3 tools/memory.py allow after /configure creates it"
echo "Claude Code: open sessions in $REPO for /assistant, /sleep, /configure and /protect."
echo "Done. Update with: git -C \"$REPO\" pull upstream main"
