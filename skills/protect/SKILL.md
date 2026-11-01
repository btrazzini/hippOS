---
name: protect
description: Sets up what each area's assistant must never do, asking one question at a time - commands it must never run, addresses it must never open, folders it may only read - writes them to the area's AREA.md and, on the computer, turns on the hippOS guard, a hook that blocks them. Use with /protect (or $protect in Codex), or "set up the protections".
---
# hippOS protect (v0.3.3)

Memory rules: `protocol.md` in this folder. Tools: `memory.py` and `guard.py` in this folder; `python3 guard.py` with no argument shows its help.

- Talk in the language the person writes in. Ask one question at a time, with suggested answers when there are obvious ones (use the question tool if the environment has one). Before each step, say in one line what it does.
- Write only the three lists below, in the `## Limits` of each `AREA.md`: the only writing outside sleep. Never remove an item or another `Limits` line without the person's yes.
- Be honest about the reach: on the computer, with the guard on, the lists are enforced; in chat, in the cloud and in sessions opened outside this repository, they are only rules the assistant follows.

## 1. Where things stand
Find the root as the assistant does (`python3 memory.py root`; without a shell, the connector, as in "Root" in the protocol). Show, per area, the current lists (`python3 guard.py show`) and whether the guard is on. Ask which areas to protect.

## 2. Each area, one question at a time
- What is production here: servers, deploy scripts, admin panels, live stores or accounts? Becomes `Never run` (deploy commands, `ssh` to those hosts) and `Never open` (their addresses).
- Which databases may only be read, and how they would be written to (an admin user, a remote host)? Becomes `Never run` (e.g. `mysql*-u root`, `psql*prod`).
- Which shared environments others depend on (containers, staging, queues)? Becomes `Never run` (e.g. `docker compose down`, `docker compose up --build`).
- Where secrets live (keys, certificates, `.env`)? Becomes `Never run` for commands that read them (e.g. `ssls/`, `cat*.env`).
- Which code folders the assistant may read but never change? Becomes `Read only` (absolute paths or `~/...`).

Propose concrete patterns from the answers. A pattern matches anywhere in a command or address, ignoring case and repeated spaces, and `*` stands for anything (including spaces). Test each proposal with `python3 guard.py test "<root>" "<example>"` and show the result; adjust until the person agrees.

Write, in the area's `## Limits`, replacing the line if it exists:
```
- Never run: `infra/deploy`, `docker compose down`
- Never open: `beta*.example.com`
- Read only: `~/code/app`
```
Then `python3 memory.py validate "<root>" <area>` (zero errors; a warning about items without backticks means the format is off). Connector mode: create the new `AREA.md` and trash the old one, as in "Drive access".

## 3. The guard (computer only)
Offer to turn it on: `python3 guard.py install` registers the hook in this repository's `.claude/settings.local.json` (not versioned, so nothing personal reaches the public repository), and it applies to sessions opened in this folder. Show it working: one `python3 guard.py test` that is blocked and one that is allowed. Say that sessions must be opened in this folder to be protected; the assistant's opening warns when they aren't. `python3 guard.py uninstall` turns it off.

## 4. Close (up to 6 lines)
What each area now forbids, where it is enforced (computer, with the guard) and where it is only a rule (chat, cloud), and that `/protect` again changes the lists.
