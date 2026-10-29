#!/bin/bash
# Builds dist/assistant.zip with the links resolved, to upload to Claude (Settings > Capabilities > Skills).
# Sleep does not go to chat: it runs only in Claude Code or Codex.
# Only versioned files go in: anything else in the skill folder (memory, for instance) stays out.
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
rm -rf "$REPO/dist" && mkdir -p "$REPO/dist/tmp"
for skill in assistant; do
  mkdir -p "$REPO/dist/tmp/$skill"
  git -C "$REPO" ls-files "skills/$skill" | while read -r f; do
    cp -L "$REPO/$f" "$REPO/dist/tmp/$skill/$(basename "$f")"
  done
  (cd "$REPO/dist/tmp" && zip -qr "../$skill.zip" "$skill")
  echo "dist/$skill.zip"
done
rm -rf "$REPO/dist/tmp"
