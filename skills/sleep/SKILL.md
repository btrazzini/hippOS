---
name: sleep
description: Consolidates and audits the hippOS memory in Google Drive, the way sleep processes the day's memories. Use with /sleep [area] or $sleep [area], in a scheduled consolidation task, or when asked to organize, consolidate or check an area's memory.
model: opus
effort: medium
---
# hippOS sleep (v0.1.3)

Memory rules: `protocol.md` in this folder (read it in full). Validator: `memory.py` in this folder.
Argument: none, the normal case (sleep finds on its own what to process, step 0), or an area or `core`, to limit itself to it.
`inbox/core/` is part of every sleep, with or without an argument, in a pass of its own, the last.

Sleep is the only one that writes to the curated memory. It works in two phases and never skips the second.

## 0. Prepare
- Only in Claude Code or Codex, with a shell. In chat or without a shell: tell <name> and stop.
- Lock (one sleep at a time): if `SLEEP-IN-PROGRESS.md` exists at the root with `started` less than 60 minutes ago, another sleep is running: tell <name> and stop without touching anything. Older than that: a previous sleep got stuck; warn and continue. No lock: create the file before any other step, with the frontmatter `type: lock`, `started: YYYY-MM-DDTHH:MM`, `origin` and `areas`.
- Local mode (preferred): if `python3 memory.py root` prints a path, work directly in it (it is the Drive folder itself, synced) and use the Drive connector in no step.
- Connector mode (cloud, no local folder): build a local copy of the whole root ("Root" in the protocol; it is small, and `core/STATE.md` reads the board of every area) in `<work>/hippOS/`, listing every folder until the pages run out and reading with `download_file_content` (raw text). Save in `<work>/ids.json` the id of every folder and file, by path (`"hippOS/areas/<area>": "<id>"`).
- In the commands below, `<root>` is the local path or `<work>/hippOS`. `<work>` is `~/.cache/hippos-sleep/`, outside the repository and the skill (memory never stays in them); empty it at the start of each sleep. In both modes, before changing anything, copy to `<work>/before/` the files the run will touch (diff base and for undoing).
- No argument: `python3 memory.py pending <root>` says which areas to process and why. Process one at a time, core last; nothing pending: delete the lock, tell <name> and stop.
- `python3 memory.py validate <root> <area>`: note the errors that already existed before changing anything.
- Fix now the list of captures for this pass (the area's, or those in `inbox/core/` in the core pass). A capture arriving during sleep waits for the next one; only those on the list go to the trash at the end.
- Size of the run, decided by the list:
  - **Light:** up to 3 captures, no decision, no `mode: forget`, no change of initiative state (e.g., only preferences or simple facts), no format error to fix (step 2.1) and no topic over the limit to split. Skips the independent reviewer (step 2.4) and regenerates only the `STATE.md` of the touched areas and `core/STATE.md`. Say in the reply that it was a light run.
  - **Full:** everything else. Follows every step.

## 1. Consolidate (autonomous phase)
Destination of each capture line:

| Content | Destination |
|---|---|
| State, risk, next step of an initiative | `initiatives/<slug>.md` (`## State`, `## Risks`, `next`) |
| Decision | new `decisions/<YYYY-MM[-DD]>-<slug>.md`, or `## Addenda` of the existing one |
| Domain fact, question about the topic | `topics/<slug>.md` |
| Person who shows up in more than one area | `core/people/<slug>.md` |
| To-do, waiting on <name>, question for <name>, priority, phase | the area's `BOARD.md` ("Board items" in the protocol) |
| Dated event (delivery, release, conversation) | the area's `LOG.md`, on top |
| Mission, role, limits, sources or lookups of the area, at <name>'s request | the area's `AREA.md` |
| How <name> wants to be served | `core/PREFERENCES.md` |
| Who <name> is | `core/PROFILE.md` |
| Outcome revealing a decision criterion | `core/PRINCIPLES.md`, with the origin `[[area:slug]]` |
| `## Thread` | `## Thread` of `BOARD.md` |

For each capture on the list, in date order:
1. Read the capture and the context it touches (`memory.py context`).
2. Apply it to the curated memory per the protocol's "Lifecycle": rewrite state in the present, update `verified`/`next`, create a record only for a new topic (search first; if it exists, update it), new decision with `supersedes` when it fully contradicts or `amends` when it changes only a part, `## Outcome` when it brings a result, to-dos and questions in `BOARD.md` with `| since` and `| due`, dated line in `LOG.md`.
3. `mode: forget`: remove from the curated memory what was asked and what depended only on it.
4. Service preference or decision criterion: `core/PREFERENCES.md` or `core/PRINCIPLES.md`, with `[<name> date]`. What the protocol or the assistant skill already say is not repeated there; what contradicts them goes in anyway, being <name>'s latest word, and is reported in the reply as an adjustment to make in the system.
5. A doubt only <name> can settle (where it fits, whether something was approved, contradiction between captures): don't decide; it becomes an item in the board's `## Questions for <name>`, citing the capture.
6. Thread of the most recent capture: goes into `## Thread` of `BOARD.md` (replaces the previous one).
Extra consolidation: `LOG.md` pruned beyond 30 days; duplicates merged; finished initiatives closed; aged item (validator warning) moved to its record per the protocol's "Lifecycle"; topic over the limit (validator warning) split: the original keeps the essentials and `links` to the new ones, without losing a line; an item whose text says who <name> owes gets `| for <who>`. An overdue to-do is not touched without a capture: the opening asks <name>.

## 2. Audit (checking phase)
1. `python3 memory.py validate <root> <area>`: zero new errors. Fix and repeat. A pre-existing error is also fixed in this run, without asking <name>, without losing an item or changing the meaning of any.
2. Content check, capture by capture. First `python3 memory.py fidelity <root> <area> <captures on the list> <copy in before/ of each split topic>`: each literal or line it flags (date, amount, PR, issue, code, link) is a loss to fix, unless it left on purpose (`mode: forget`, resolved item). Then: is everything the capture said in the curated memory, in the right place, with the right marker? Did no `[hypothesis]` become `[fact]`? Was no approved decision rewritten? Was nothing invented beyond what the captures said?
3. Coherence, which the validator can't see, in the records this run touched: frontmatter against body and board (e.g., an initiative's `owner` against a "Waiting on <name>" item asking who the owner will be); a decision whose body says it supersedes or amends another without the `supersedes`/`amends` field; a `next` that already happened according to another capture. Incoherence: fix it if the captures settle it; otherwise, a question for <name> on the board.
4. Independent reviewer (full run only): if another agent is available (Codex when sleep runs in Claude, Claude when it runs in Codex), hand it the captures and the diff (before and after) with the request "point out only divergences between captures and curated memory, with file and line". No other agent: a subagent with `model: sonnet` (mechanical comparison; faster and cheaper) and without this session's context. Confirmed divergence: fix it.

## 3. Write
1. The area's `CHANGELOG.md`, and `core/CHANGELOG.md` when the run touched core (create from the template if missing): dated entry on top with the processed captures and, per file, what changed in one line.
2. Send to Drive only the changed files (local: already in place; connector mode: create the new one with the same title in the same folder and trash the old one only after the new one exists). Order, so that an interrupted sleep never loses data: curated first (with `BOARD.md` and `LOG.md`), then `CHANGELOG.md`.
3. Only after that: trash the captures on the list fixed in step 0. A capture that produced a question for <name> also goes (the question is on the board).
4. `python3 memory.py state <root> <area> --write` generates `areas/<area>/STATE.md`, and `python3 memory.py core <root> --write` generates `core/STATE.md` and `MAP.md` (in connector mode, with `--ids <work>/ids.json`; locally, the ids come from Drive itself). In connector mode, send them to Drive. Check at the end that no folder has two files with the same title.
5. Last, delete `SLEEP-IN-PROGRESS.md` (connector mode: trash it). If sleep stops midway on an error, also delete the lock before replying.

## 4. Reply to <name> (up to 6 lines)
How many captures went in, what relevant changed, divergences the audit found and fixed, new questions. Errors that existed before sleep: list them without hiding.
