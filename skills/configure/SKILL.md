---
name: configure
description: Sets up hippOS step by step, asking one question at a time - the hippOS folder in Google Drive, the person's profile, the first areas and, on a computer, the skills and the private copy of the repository. Use with /configure (or $configure in Codex), on first use, to add an area or to check the setup.
---
# hippOS configure (v0.3.0)

Memory rules: `protocol.md` in this folder (read "Layers", "Root in Drive" and "Drive access"). Tools: `memory.py` in this folder (`new` and `area` build from the repository's `templates/`).

- Talk in the language the person writes in. Ask one question at a time, with suggested answers when there are obvious ones (use the question tool if the environment has one). Before each step, say in one line what it does.
- Never fill in a field the person didn't give or confirm. Never overwrite or delete a memory file: creating a memory or an area, and the profile's `name`, `timezone` and `language`, are the only writing outside sleep.
- Only in Claude Code or Codex, with a shell. In chat: say that `/configure` runs in Claude Code (on the computer or at claude.ai/code) and stop. If `SLEEP-IN-PROGRESS.md` exists in the root, a sleep is running: say so and stop.

## 1. Where things stand
Check without changing anything, then tell the person in a few lines:
- Drive: `python3 memory.py root`. A path: local mode, the root exists. Nothing: look for Google Drive for desktop ("My Drive" under `~/Library/CloudStorage/GoogleDrive-*/` on a Mac; a drive letter or `~/My Drive` on Windows); with it, local mode, the root still to be created there (several Google accounts: ask which); without it, connector mode (search `title = 'hippOS'`, as in "Root").
- Memory: a root with `core/PROFILE.md` is an existing memory: go to step 5. Otherwise, steps 2 to 4; a root without it is an unfinished setup, and they complete what is missing.
- Computer (local mode): are `~/.claude/skills/assistant`, `sleep` and `configure` links to this repository? And `git remote -v`: an `origin` pointing to the public `btrazzini/hippOS` means there is no private copy yet.

## 2. Profile
Ask, one at a time:
1. Language of replies and memory content (suggest the one they are writing in; e.g. `en`, `pt-BR`).
2. What to call them (`name`).
3. Timezone, IANA (suggest the computer's: `readlink /etc/localtime` on a Mac, the part after `zoneinfo/`; in the cloud the machine is usually UTC, so ask).
4. Optional: a few lines about who they are that will hold for months (role, what they do, what matters to them).
5. Optional: two or three preferences on how to be served (length of answers, tone, what to avoid).

Create: `python3 memory.py new "<root>" "<name>" <timezone> <language>`, where `<root>` is `hippOS` directly in My Drive. Then write the answers to 4 in the body of `core/PROFILE.md` (with `[<name> date]`) and to 5 in `core/PREFERENCES.md`, under the template's sections. Connector mode: build it in `~/.cache/hippos-configure/hippOS/` and, at the end of step 4, create the same folders and files in Drive: the `hippOS` folder directly in My Drive, folders before their files (`mimeType: application/vnd.google-apps.folder`), files as in "Drive access". Before creating each one, search for it by title and parent: if it exists, keep it and don't create another (the connector can't overwrite, and two files with the same title break the memory).

## 3. Areas
Ask which areas of life to start with (suggest common ones, such as work, personal, health, finances; one is enough). For each area, one question at a time:
- Folder name: short, lowercase, hyphens (`side-project`); optional aliases.
- Mission in one line, and what success looks like.
- The assistant's role: what it does and what it doesn't.
- Limits (what it must never do) and sources it should know (tools, repositories, documents).
- GitHub lookups, only if they use GitHub for this area and `gh auth status` is logged in: which repositories, and whether to watch issues assigned to them, issues with a label, or PRs requesting their review (format in the `## Lookups` comment of `templates/area/AREA.md`), plus the people's logins and names.

Create: `python3 memory.py area "<root>" <area> [alias ...]`, then fill `AREA.md` with the answers, in their words; a section they skipped keeps the template's `...`.

## 4. Finish
1. `python3 memory.py validate "<root>"` with zero errors (fix what it flags), then `python3 memory.py state "<root>" <area> --write` for each area and `python3 memory.py core "<root>" --write`. Connector mode: run them on the local copy, upload everything, then run `core` again with `--ids` (a JSON of the created folders' ids by path, `"hippOS/areas/<area>": "<id>"`, as sleep does) and upload `MAP.md`.
2. Computer: skills not linked: offer to run `./install.sh` from the repository.
3. Private copy, needed for Claude Code in the cloud: if `origin` is the public hippOS, offer to create it; on a yes, with `gh` logged in, `git remote rename origin upstream` and `gh repo create <name they choose> --private --source . --push`. Never push to the public repository.
4. Cloud and chat: the Google Drive connector turned on in Claude, with the Google account that holds `hippOS`; for chat, the zip from `tools/package.sh`.
5. Nightly sleep, so each morning's opening starts consolidated: if the environment schedules tasks (a scheduled task in the Claude desktop app, or a cloud routine with `/schedule`), offer a `/sleep` every night at an hour they choose (suggest 03:00, their timezone). On a yes, create it with the prompt `/sleep`: on the computer, with the skills linked (4.2), and say the app runs it only while open (if closed, at the next launch); in the cloud, on the private copy (4.3), with the Drive connector (4.4). Elsewhere, they run `/sleep` themselves.
6. Morning brief, so the assistant speaks first: where nightly sleep can be scheduled, offer `/assistant` with no area every morning at an hour they choose (suggest 07:30, after the sleep), created the same way. With an email connector, offer to also send it to their own address; that yes is the authorization.
7. Close in up to 6 lines: what was created and the next step, `/assistant <area>`; conversations leave captures in the inbox, and `/sleep` consolidates them.

## 5. Existing memory
Say what is there (areas, profile fields) and ask what they want:
- Add an area: step 3, then step 4.1.
- Change `name`, `timezone` or `language` in `core/PROFILE.md`: only those fields, then `python3 memory.py validate "<root>" core`.
- Check the setup: steps 4.2 to 4.6.
Anything else in the memory (board, records, preferences) is a conversation with `/assistant`, which `/sleep` consolidates.
