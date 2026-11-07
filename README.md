# hippOS

*Leia em português: [README.pt-BR.md](README.pt-BR.md)*

**Talk about your day. hippOS keeps what matters, and any assistant picks up where you left off.**

hippOS is a memory for people who lead: the commitments you made, what others owe you, the decisions you took and why, the people involved. You talk to it the way you would to a trusted chief of staff, ideally by voice. It notes what lasts, sleep organizes it overnight, and the next morning your assistant already knows where you stopped and where to start.

## Why it exists

Anyone who leads carries too much in their head: the promise made in the hallway, the report Diego has owed since last week, why the team chose option B in March, the deadline that hangs on someone who has gone quiet. Lists don't hold it, because writing things down is one more task. Chat assistants don't hold it either: each conversation starts from zero, and the memory some of them keep belongs to the vendor, is hard to see and stays behind when you switch.

hippOS exists so you can stop carrying it. You talk, it remembers, and when you come back it tells you what needs you.

## The idea

The name comes from the hippocampus, the part of the brain that records the day and, during sleep, consolidates what deserves to stay. hippOS works the same way, in three moves:

1. **Talk.** By voice or text, you tell the assistant of an area (work, health, finances, a hobby) what happened, what you decided, what you promised, what worries you. On the spot, without interrupting, it notes what lasts: decisions and their reasons, commitments with an owner and a date, changes of state, risks, your preferences. Each note is a small file in an inbox in your Google Drive.
2. **Sleep.** `/sleep`, ideally scheduled every night, reads the inbox and consolidates it into the area's memory: it merges, corrects, closes what was done, checks with plain code that no date or amount was lost, and writes a fresh state of each area.
3. **Pick up.** The next conversation opens like someone who works with you talking: where it would start and why, what is overdue with someone waiting, what you asked it not to forget. Any assistant that reads the folder continues from there.

## What it believes

- **Talk, don't type.** Recording has to cost nothing, or it doesn't happen. That is why hippOS is at its best in a voice chat: you talk on the way to a meeting and the memory is up to date. *Why:* the moment to record is the moment it happened, and that is rarely in front of a keyboard.
- **Keep what matters, not everything.** You can talk about anything: plans, doubts, what you would rather not think about. The assistant keeps what will be needed later and lets the rest go. *Why:* a memory that records every word turns into noise and stops being read. "Just discussing" records nothing; "forget that" erases it.
- **It says where each thing came from.** Every line in the memory is marked: what you said, and when; what was checked, and against what; what is only a guess. *Why:* a memory that mixes your words with the AI's guesses can't be trusted when you decide, so a guess is never promoted to fact.
- **The memory is yours.** Plain Markdown in a folder in your own Google Drive: you can read it, edit it, back it up and take it elsewhere. No server, no database, no hippOS account.
- **No vendor lock.** The memory is files and the rules are open text, so the assistant can change: Claude (chat, voice, Claude Code), Codex, or an outside agent that reaches your Drive (`EXTERNAL-AGENTS.md`). Whoever comes next picks up where the last one stopped.
- **It takes the initiative.** You shouldn't have to remember to ask. The opening says where to start; what has no date comes back, one item a day; what others owe you comes up when it goes quiet.
- **A critical colleague, not a yes-man.** It recommends and you decide. It separates fact from hypothesis, says when two things collide and doesn't agree by default.
- **Made to decide and to lead.** Every idea that comes in passes one question: "does this help an executive carry less in their head?". Decisions with their reasons, commitments, people and due dates come first.
- **One area at a time.** Each area has its own assistant, mission and limits (including what it must never do), so work doesn't spill into health, and the other way around.
- **Auditable.** The rules are plain Markdown, the tools are plain Python with no dependencies, and sleep keeps a changelog of what it changed and why.

## What it is not

- **Not a task or notes app.** There is no screen to keep tidy: you talk, and the memory is tidied for you.
- **Not a transcript.** It doesn't keep every word, only the facts, decisions and commitments that come out of what you say.
- **Not an agent that acts for you.** It remembers, reminds and helps you think; sending, deciding and doing stay with you.
- **Not a service.** Nothing of yours reaches hippOS. This repository holds only the system.

## A morning with hippOS

By voice, in the Claude app on your phone, on the way to the office:

> **You:** Work.
>
> **Assistant:** I'd start with Diego's proposal: you promised him an answer by yesterday and he is waiting. After that, the budget review is on Friday and finance hasn't sent the numbers yet. And you asked me not to forget the call with the new client. Shall we start with Diego?
>
> **You:** Yes. I'm going with option B, the cheaper one, but delivered in two phases. I'll tell him at lunch. And remind me to chase finance tomorrow morning.
>
> **Assistant:** Two phases makes sense, but the second one lands in the same week as the budget review; worth giving Diego that date now. Noted: answer Diego at lunch, and chase finance tomorrow morning.

That night, sleep records the decision with its reason, keeps the answer to Diego open until you say it is done and adds the follow-up with finance. Tomorrow, whichever assistant you open starts from there.

## Getting started, in three steps

1. **Set it up once.** `/configure`, in Claude Code (on your computer, or at claude.ai/code if you have no computer at hand), asks one question at a time and creates the `hippOS/` folder in your Google Drive, your profile and your first areas.
2. **Talk by voice.** In Claude, create a project for hippOS, paste the block in your language from `CLAUDE-PROJECT-INSTRUCTIONS.md` into the project's instructions and turn on the Google Drive connector, with the Google account that holds `hippOS/`. The instructions now live in the project: every chat in it, voice included, already starts as your assistant, with no file to attach and no command to type. To check, open a voice chat in the project and say only the name of an area; if the reply asks for a typed command, the instructions didn't load.
3. **Let it sleep.** `/configure` offers to schedule `/sleep` every night. Sleep runs in Claude Code (on your computer or in the cloud), because it rewrites the memory and runs the validator; chat and voice are for talking.

The full steps are in "Getting started", below.

## How it works, in detail

From here on, the mechanics: what goes where, what runs where and the known limits.

This repository holds only the **system**: protocol, skills, validator and templates. Each person's **memory** lives in a `hippOS/` folder in their own Google Drive. Nothing personal goes in here.

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
   - **The opening** reads like someone who works with you talking, not a dashboard: a few plain sentences, no emojis or lists. It says where it would start and why (what is overdue with someone waiting comes first), then what else presses, what you asked it **not to forget** and the first point sleep concluded needs your **attention** (what dates alone don't show, such as two things colliding or a deadline hanging on someone quiet). What other sessions have just captured already counts (it is memory, even before sleep), and you answer in your own words. When nothing presses, one item **without a date** comes back, a different one each day, so nothing depends on you remembering to ask. With a calendar connector, it mentions today's next meeting and what each side owes. **"What else?"** opens the numbered list, so you can answer "1 done, 3 on Friday": what is overdue, the next due dates, what to **follow up** (what you wait on from others, overdue or quiet for a week), what waits on you, what has no date and one **Also** line counting the rest (questions, parked items, decisions to review, initiatives not checked).
   - **`/assistant`** with no area gives the brief of every area at once; on Mondays the opening offers the **weekly review** (`memory.py review`). Before you talk to someone, `memory.py person` brings everything open with them. An item can recur (`| every month`), show up earlier (`| prep 30`) and remember the last nudge (`| last`), so following up doesn't nag the next morning.
2. **`/sleep`**, with no area, finds on its own what needs sleep (`memory.py pending`: captures in the inbox, old state or state from an earlier version, errors or cleanup flagged by the validator) and processes area by area, core last. With an area (`/sleep <area>`), it stays there. In each area it consolidates into the curated memory (phase 1), audits with the validator, the fidelity check and an independent reviewer (phase 2), generates the `STATE.md` files and `MAP.md`, records what changed in `CHANGELOG.md` and empties the inbox. Closed to-dos stay in `LOG.md`, and older entries move to `log/<YYYY-MM>.md` instead of being deleted, so "did I already send that?" has an answer.

Conversation modes: normal (captures), "just discussing" (records nothing), "forget that" (sleep removes it).

The assistant replies in the `language` set in your profile. The system is in English, and so is the memory's structure (headings, frontmatter, markers and board fields, as in `templates/`); only the content is in your language.

## Where to run what

| | Assistant (`/assistant`) | Sleep (`/sleep`) |
|---|---|---|
| Claude Code on your computer | Yes, the fastest (reads the Drive folder straight from disk) | **Yes, the main place** |
| Claude Code in the cloud (claude.ai/code, browser or phone app) | Yes | **Yes: it's how you run sleep away from your computer** |
| Codex on your computer | Yes | Yes, picking the model by hand (Codex ignores the skill's `model` and `effort`) |
| Claude chat (desktop or phone) | Yes | **No** |
| Claude project (chat and voice) | Yes, with `CLAUDE-PROJECT-INSTRUCTIONS.md` pasted into the project's instructions (skills don't load in voice) | No |
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
2. **`/configure`**, in Claude Code opened in that folder. It asks one question at a time and sets everything up: the `hippOS/` folder directly in "My Drive" (the name is fixed: it is how the assistant finds it), your profile (name, language, timezone), your first areas, and the `STATE.md` and `MAP.md` files; it also offers to schedule `/sleep` every night and a morning brief.
3. **Your private copy.** `/configure` also offers to create it: Claude Code in the cloud only opens repositories in your account, and a fork of a public repository can't be private. Your copy can have any name; hippOS stays as `upstream`, so you update with `git pull upstream main` and `git push`. Your own tweaks (hooks in `.claude/settings.json`, your own skills) stay only in your copy, in files hippOS doesn't have, so they never conflict.
4. **Protections** (optional): `/protect` asks what each area's assistant must never do (deploy, write to a database, take down a shared environment, edit a code folder) and writes it to the area's `AREA.md`. On your computer it also turns on the guard, a hook in `tools/guard.py` that blocks those commands, addresses and edits in sessions opened in this folder. Elsewhere they are rules the assistant follows.
5. **Cloud and chat:** turn on the Google Drive connector in your Claude account, with the Google account that holds `hippOS/`. In the cloud, sessions open your private copy; in chat, a project with `CLAUDE-PROJECT-INSTRUCTIONS.md` in its instructions (the one that also works by voice), or the `assistant` skill installed in your account with the zip from `tools/package.sh` (reinstall it with every version). Codex in the cloud isn't supported: its environment has no Google Drive tools.

No computer? Import hippOS as a private repository in your GitHub account, open a session at claude.ai/code on it and run `/configure`: it builds the memory through the Drive connector.

## Adding an area

Run `/configure` again and choose to add an area. By hand: `python3 tools/memory.py area <root> <area>` creates it from `templates/area/`; fill in `AREA.md` (mission, role, limits, sources) and run `/sleep`, which generates its `STATE.md` and updates `MAP.md`.

## Versions

`system/VERSION`. If you change the protocol or a skill, `tools/version.sh <new>` bumps the version everywhere (`VERSION`, the protocol header, the skill titles and `memory.py`); with no argument, it only checks. Then reinstall in Claude (`tools/package.sh`). Each version is tagged `vX.Y.Z`, with notes under Releases. A change in the first two numbers calls for a `/sleep` (with no area, it goes through all of them) to convert the memory to the new format: in that pass it reads every record, not only those the captures touched.

Old notes need no separate tool: what the validator flags, the next `/sleep` fixes, even without a new version. A `.md` loose in an area or outside the protocol's folders is treated as a capture: its content goes where it belongs and the file to the Drive trash. To keep a text that isn't memory, leave it in `areas/<area>/drafts/`.

## Known limits

- **Windows is untested.** The skills rely on git symlinks (turn on Developer Mode or `git config core.symlinks true` before cloning), `install.sh` needs bash (Git Bash or WSL), the rules call `python3`, and correct timezones need the `tzdata` package (`pip install tzdata`).
- **Folder ids outside a Mac.** Only Google Drive for desktop on a Mac exposes folder ids, so a local `/sleep` on Windows or Linux leaves them out of `MAP.md`; the assistant in chat and in the cloud relies on them. A `/sleep` run in the cloud (claude.ai/code) fills them in.
- **Protections are enforced only on the computer.** The guard blocks what the lists name in sessions opened in the repository's folder; in chat, in the cloud and in other folders they are rules. Patterns are plain text, so a determined rewrite of a command can slip past; keep anything critical behind real permissions too.
- **Sleep runs by itself only on a schedule.** `/configure` offers to schedule `/sleep` every night: a scheduled task in the Claude desktop app (local mode; it runs only while the app is open, or at the next launch) or a cloud routine (`/schedule`, on your private copy, through the connector, slower). Without one, you run `/sleep` yourself.

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
