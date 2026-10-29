# hippOS

*Leia em português: [README.pt-BR.md](README.pt-BR.md)*

Personal AI assistants with memory: one assistant per area of your life (work, health, finances, a hobby and whatever comes next), and a memory that is yours, in plain Markdown in your Google Drive, consolidated by `/sleep` the way the brain consolidates memory overnight. The name comes from the hippocampus, the part of the brain that consolidates memory during sleep, which is what `/sleep` does. It works in Claude (chat, phone, Claude Code) and in Codex.

This repository holds only the **system**: protocol, skills, validator and templates. Each person's **memory** lives in a `hippOS/` folder in their own Google Drive. Nothing personal goes in here.

## How it works

```
GitHub (your copy of hippOS)      Google Drive: hippOS/
  system/protocol.md                core/         who you are, preferences, principles, overview
  skills/assistant/  ──reads────▶   areas/<area>  curated memory of each area
                     ──writes───▶   inbox/<area>  raw captures from each conversation
  skills/sleep/      ──reads the inbox, writes areas/ and core/, empties the inbox
  tools/memory.py    validator, STATE, opening, fidelity (no network)
  tools/lookup.py    the area's GitHub, through gh, on the spot
```

Setup is guided: **`/configure`** asks one question at a time and builds the memory (see "Getting started").

1. **`/assistant <area>`** opens a conversation as that area's assistant. It reads the core, the area's rules and its `STATE.md`, looks up on its own what is waiting on you in the area's sources (GitHub, through `tools/lookup.py`), answers "what do I owe?", and during the conversation writes a small file to the `inbox/` per capture (decision, change of state, to-do, preference). It never changes the curated memory.
2. **`/sleep`**, with no area, finds on its own what needs sleep (`memory.py pending`: captures in the inbox, old state or state from an earlier version, errors or cleanup flagged by the validator) and processes area by area, core last. With an area (`/sleep <area>`), it stays there. In each area it consolidates into the curated memory (phase 1), audits with the validator, the fidelity check and an independent reviewer (phase 2), generates the `STATE.md` files and `MAP.md`, records what changed in `CHANGELOG.md` and empties the inbox.

Conversation modes: normal (captures), "just discussing" (records nothing), "forget that" (sleep removes it).

The assistant replies in the `language` set in your profile. The system is in English, and so is the memory's structure (headings, frontmatter, markers and board fields, as in `templates/`); only the content is in your language.

## Where to run what

| | Assistant (`/assistant`) | Sleep (`/sleep`) |
|---|---|---|
| Claude Code on your computer | Yes, the fastest (reads the Drive folder straight from disk) | **Yes, the main place** |
| Claude Code in the cloud (claude.ai/code, browser or phone app) | Yes | **Yes: it's how you run sleep away from your computer** |
| Codex on your computer | Yes | Yes, picking the model by hand (Codex ignores the skill's `model` and `effort`) |
| Claude chat (desktop or phone) | Yes | **No** |
| Codex in the cloud | No (no Drive access) | No |
| Outside agents (e.g., OpenAI's Dot) | Yes, through the Drive connector, with `EXTERNAL-AGENTS.md` pasted into their instructions | No |

**Why sleep doesn't run in chat:** it needs to read the whole memory, run the Python validator and rewrite files. In chat, every file goes through the conversation, one by one (there are dozens); the validator only runs if code execution is on and has to be copied in every time; and since the Drive connector can't edit a file, every change becomes "create a new one and trash the old one", losing Drive's version history. Claude Code (on your computer or in the cloud) has the repository, a terminal, and pins sleep's model and effort (`model: opus`, `effort: medium`).

**Rule of thumb:** chat and phone are for talking to the assistant and producing captures; sleep runs in Claude Code. Away from your computer, open a session at claude.ai/code on your copy of the repository and type `/sleep`. One sleep at a time: the `SLEEP-IN-PROGRESS.md` lock, at the root, prevents two at once.

**Recommended model:** the assistant day to day with Sonnet, medium effort; Opus, high effort, for hard decisions (you can switch mid-conversation). Sleep pins Opus on its own in Claude Code.

## Getting started

Tested on a Mac; not yet on Windows (see "Known limits").

1. **Clone and link the skills**, on your computer:
   ```
   git clone https://github.com/btrazzini/hippOS ~/hippOS
   cd ~/hippOS
   ./install.sh
   ```
   `install.sh` links the skills into Claude Code and Codex (`~/.claude/skills`, `~/.agents/skills` and `~/.codex/skills`).
2. **`/configure`**, in Claude Code opened in that folder. It asks one question at a time and sets everything up: the `hippOS/` folder directly in "My Drive" (the name is fixed: it is how the assistant finds it), your profile (name, language, timezone), your first areas, and the `STATE.md` and `MAP.md` files.
3. **Your private copy.** `/configure` also offers to create it: Claude Code in the cloud only opens repositories in your account, and a fork of a public repository can't be private. Your copy can have any name; hippOS stays as `upstream`, so you update with `git pull upstream main` and `git push`. Your own tweaks (hooks in `.claude/settings.json`, your own skills) stay only in your copy, in files hippOS doesn't have, so they never conflict.
4. **Protections** (optional): `/protect` asks what each area's assistant must never do (deploy, write to a database, take down a shared environment, edit a code folder) and writes it to the area's `AREA.md`. On your computer it also turns on the guard, a hook in `tools/guard.py` that blocks those commands, addresses and edits in sessions opened in this folder. Elsewhere they are rules the assistant follows.
5. **Cloud and chat:** turn on the Google Drive connector in your Claude account, with the Google account that holds `hippOS/`. In the cloud, sessions open your private copy; in chat, a project that syncs your copy, or the `assistant` skill installed in your account with the zip from `tools/package.sh` (reinstall it with every version). Codex in the cloud isn't supported: its environment has no Google Drive tools.

No computer? Import hippOS as a private repository in your GitHub account, open a session at claude.ai/code on it and run `/configure`: it builds the memory through the Drive connector.

## Adding an area

Run `/configure` again and choose to add an area. By hand: `python3 tools/memory.py area <root> <area>` creates it from `templates/area/`; fill in `AREA.md` (mission, role, limits, sources) and run `/sleep`, which generates its `STATE.md` and updates `MAP.md`.

## Versions

`system/VERSION`. If you change the protocol or a skill, `tools/version.sh <new>` bumps the version everywhere (`VERSION`, the protocol header, the skill titles and `memory.py`); with no argument, it only checks. Then reinstall in Claude (`tools/package.sh`). Each version is tagged `vX.Y.Z`, with notes under Releases. A change in the first two numbers calls for a `/sleep` (with no area, it goes through all of them) to convert the memory to the new format.

## Known limits

- **Windows is untested.** The skills rely on git symlinks (turn on Developer Mode or `git config core.symlinks true` before cloning), `install.sh` needs bash (Git Bash or WSL), the rules call `python3`, and correct timezones need the `tzdata` package (`pip install tzdata`).
- **Folder ids outside a Mac.** Only Google Drive for desktop on a Mac exposes folder ids, so a local `/sleep` on Windows or Linux leaves them out of `MAP.md`; the assistant in chat and in the cloud relies on them. A `/sleep` run in the cloud (claude.ai/code) fills them in.
- **Protections are enforced only on the computer.** The guard blocks what the lists name in sessions opened in the repository's folder; in chat, in the cloud and in other folders they are rules. Patterns are plain text, so a determined rewrite of a command can slip past; keep anything critical behind real permissions too.
- **Sleep is manual.** You run `/sleep` yourself (see below).

## Possible, not yet set up

- **Automatic sleep.** A scheduled task can run `/sleep` on its own (every night, for instance) in Claude Code on your computer, in local mode, so the memory wakes up consolidated. It would also work in the cloud, through the connector, only slower.

## Credits and inspiration

hippOS owes a clear debt to **[ai-memory](https://github.com/akitaonrails/ai-memory)**, by Fabio Akita (MIT License): long-term memory for coding agents, whose cycle (capture, consolidation, opening, handoff) mirrors hippOS's (capture, sleep, opening, thread). Two of its ideas are at the core of hippOS:

- **Checking the fidelity of consolidation without AI.** A model consolidating notes tends to lose the literals (dates, amounts, issue and PR numbers, code, links); plain code checks that they made it into the memory. Here: `memory.py fidelity`, in sleep's audit.
- **Rules with a budget.** What the agent reads every session has a word ceiling, and promoting a rule is subtractive: for one to come in, another leaves. Here: the ceiling in `tools/version.sh` and the rule in `AGENTS.md`.

hippOS took ideas from ai-memory, not code. Both trace back to Andrej Karpathy's "LLM wiki" pattern (ingest, query and lint, with an index and a log). What we brought in, what we kept for later and what doesn't fit is in `system/inspirations.md`.

## Contributing

Issues and pull requests are welcome; the maintainer decides what goes in. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE): use, copy, change and redistribute hippOS, commercially or not, as long as you keep the license notice, which credits the origin. If you build on it, a link back to this repository is appreciated.

Everything is meant to be auditable: the rules the agents follow are plain Markdown in `system/` and `skills/`, the tools are plain Python with no dependencies, and nothing reaches the network except `gh`, when an area lists GitHub sources. Your memory stays in your Google Drive; this repository never holds it.
