# hippOS

Reader: agent (Claude Code or Codex). English.

This repository is the hippOS **system** (protocol, skills, validator, templates). Each person's memory lives in a folder in their Google Drive, never here.

## If asked for an assistant, sleep or setup
- `/assistant <area>` or `$assistant <area>`: follow `skills/assistant/SKILL.md`.
- `/sleep [area]` or `$sleep [area]`: follow `skills/sleep/SKILL.md`.
- `/configure` or `$configure`: follow `skills/configure/SKILL.md` (setup, new areas).
- Memory rules: `system/protocol.md`.
- Outside agent without the skills (e.g., OpenAI's Dot): `EXTERNAL-AGENTS.md` too.

## If asked to change the system
- Never write anyone's data (names of people and clients, amounts, decisions, contacts, real areas) into a file in this repo. Examples use generic placeholders (`work`, `hobby`, `Diego`). What belongs to one person (hooks in `.claude/settings.json`, their own skills) stays only in their private copy.
- Nothing in the system depends on a fixed name, account, folder or timezone: name, timezone and language come from `core/PROFILE.md`, the root is the `hippOS` folder in My Drive (`memory.py root` locally, a search by name through the connector). In the rules, the person is `<name>`.
- Single source: `system/protocol.md`, `tools/memory.py` and `tools/lookup.py`. In the skills they are symlinks; don't copy them.
- Rule change: protocol, skills and validator in the same change; `python3 -m py_compile tools/memory.py tools/lookup.py`; bump the version with `tools/version.sh <new>` (protocol, skill titles, `VERSION` in `memory.py`).
- Budget: the protocol and skills, which the assistant and sleep read every session, have a word ceiling (`tools/version.sh` checks it and refuses to bump the version above it). A new rule only comes in with the case that failed, and for one to come in, another leaves or merges. Test for each line: would removing it make the assistant err? What is mechanical goes into code, not text.
- Outside inspirations: `system/inspirations.md`. A curious look; nothing comes in without passing the question "does this help an executive?".
- Commit messages in English; push only on request.
