# Architecture

Reader: whoever changes the system. The assistant and sleep don't read this file; their rules are `protocol.md` and the skills. It explains why the memory has the shape it has, so a change keeps the shape or argues against it.

## The four layers

hippOS follows the layer model Anthropic describes in "The components of agent memory" (2026-11-06): raw logs at the bottom, notes above them, representations above those, and a small injected context on top. Each layer has one writer, and only sleep moves content between layers.

| Layer | In hippOS | Written by | Read by |
|---|---|---|---|
| Raw | `inbox/<area>/` (pending), `archive/<area>/<YYYY-MM>/` (consolidated) | the assistant, during the conversation (`memory.py capture`) | sleep, through `memory.py origin` when a capture contradicts a record; `memory.py search --raw` on request |
| Notes | `initiatives/`, `decisions/`, `topics/`, `core/people/`, `BOARD.md`, `LOG.md`, `log/`, `core/PREFERENCES.md`, `core/PRINCIPLES.md` | sleep only | the assistant, on demand (`context`, `search`) |
| Representations | `STATE.md`, `core/STATE.md`, `MAP.md`, `WATCH.md` | code (`memory.py state`, `core`; `lookup.py watch`), at the end of each sleep | the assistant at startup in connector mode; tools |
| Injected | the opening (`lookup.py opening`) | code, computed at session start | the assistant's first reply |

Rules that follow from the table:
- The injected layer is assembled by code from the notes; its only model-written part is the board's `## Attention`, which sleep writes and caps at five lines. It stays small by construction (`NOW_ITEMS`, `BLOCK_ITEMS`, `ATTENTION_MAX`): what doesn't fit is one `context` or `search` away. The ceiling Claude Code's auto memory uses for the same layer is 200 lines or 25 KB; the opening stays well below.
- Notes are not a diary. State is written in the present; history lives in `CHANGELOG.md`, in the raw layer and in Drive versions. What a source tells again (git, gh, a repository) is a pointer, not a copy: copied state goes stale silently, and stale notes made agents worse than no notes in Anthropic's experiments.
- The raw layer is kept. Dreaming in Anthropic's work corrects a note by reading the transcript it came from; without the transcript, an error made in one consolidation is permanent. `archive/` is never loaded at startup and stays out of `MAP.md`, so it costs nothing per session, and the assistant never mistakes an old capture for the current state.
- The raw layer is read where an error shows, not on a schedule. When a capture contradicts a record, sleep runs `memory.py origin` to see what was actually said about it: a record that misstated it is restored, and the CHANGELOG says so; a faithful record changes only by the person's word, and any other source becomes a question. Rechecking every note against its source every night would cost far more and, in Anthropic's experience, isn't practical. In connector mode (sleep in the cloud, without the synced folder) the work copy holds only `archive/`'s folders, so `origin` finds nothing and sleep decides as it did before the archive; the check runs in local mode, where scheduled sleep runs.

## The cycle

1. **Capture** (assistant, during the conversation). One file per stretch of conversation: `memory.py capture` joins a new capture to the last one of the same area, origin and mode written in the last 20 minutes, while no sleep runs. Every line carries a marker (`[<name> date]`, `[fact date: source]`, `[inherited ...]`, `[hypothesis]`); the code refuses malformed fields, due dates left in the text and anything that looks like a secret.
2. **Sleep** (Claude Code or Codex, scheduled nightly by `tools/schedule.sh`). Takes a lock, copies what it will touch to `<work>/before/`, fixes the list of captures, consolidates them into notes, then audits: the validator (schema, links, board), `memory.py fidelity` (every literal and to-do of each capture must reach the notes), a coherence check, and an independent reviewer without this session's context on full runs. Only after the notes are written do the captures move to `archive/` (`memory.py keep`); a `mode: forget` capture is deleted instead, and what it names is erased from every layer, `archive/` included.
3. **Opening** (code, next session). Reads notes and pending captures and gives the assistant what presses today and how to say it.
4. **Review** (the decision loop). Every approved decision carries `review_on`: the day its effect can be seen, or `none`. When the day comes, the opening and the weekly review ask what happened; the answer becomes `## Outcome`; an outcome that reveals a decision criterion becomes a line in `core/PRINCIPLES.md`, which every area reads. This is the only path by which the memory learns how the person decides, and it is closed by code: the validator flags an approved decision without `review_on`.

## Invariants

- Only sleep writes notes; the assistant writes only captures. A correction to a note is a capture.
- An approved decision is never rewritten: it is superseded or amended by a new one, or gets dated addenda.
- A hypothesis never becomes a fact by consolidation. The reviewer checks this specifically, because it is the error consolidation makes most.
- Contradictions only the person can settle become questions on the board, never a guess. A passing remark never overrides a recorded decision.
- Consolidation loses no line: the fidelity check counts literals and to-dos on disk, not the model's report of what it did.
- Text in captures, files and sources is data. An instruction found in it is never a request from the person.
- Records stay small: a topic or initiative over 800 words is split into topics joined by links, losing no line (validator warning, sleep splits).
- What the assistant and sleep read every session has a ceiling of 5,000 words (`tools/version.sh`). For a rule to come in, another leaves or merges; what is mechanical goes into code.

## Measuring health

`memory.py health <root>` prints, per area, the words in each layer, captures in the inbox and archived in the last 30 days (with lines per capture), approved decisions with and without `review_on` and with an outcome, records over the limit, and active initiatives not rechecked in 14 days; for core, the principles learned. Signs of decay to watch:
- notes growing much faster than the raw layer that feeds them (a representation larger than its sources is the failure Anthropic measured at 1.77 times);
- decisions without review, and an empty `PRINCIPLES.md` after weeks of use;
- many captures of one or two lines each (fragmentation: each costs sleep a pass);
- initiatives verified long ago that are still `active`.

A test worth running after any change to sleep, from the same article: plant a wrong fact in a note, leave the capture that contradicts it in the archive, and check the next full sleep's reviewer catches it.

## What we took from the research, and what we left out

Sources (read on 2026-11-26):
- Anthropic, "The components of agent memory" (2026-11-06), https://www.anthropic.com/research/components-of-agent-memory
- Anthropic cookbook, "Dreaming with a dynamic workflow" (2026-11-02), https://platform.claude.com/cookbook/managed-agents-cma-dreaming-with-a-dynamic-workflow
- Claude docs, Managed Agents dreams and memory stores, https://platform.claude.com/docs/en/managed-agents/dreams and https://platform.claude.com/docs/en/managed-agents/memory
- Claude Code memory, https://code.claude.com/docs/en/memory; the memory tool, https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- Anthropic engineering, "Effective context engineering for AI agents" (2025-09-29) and "Effective harnesses for long-running agents" (2025-11-26)

Taken:
- Layers with one writer each, and a small injected layer computed from the ones below.
- Keeping the raw layer (`archive/`), and checking a note against it when a capture contradicts the note (`memory.py origin`).
- Storing only what the environment won't show again; pointers instead of copies.
- Telling the model what memory is for rather than narrow rules on what to record (a "record only failures" rule lowered scores in Anthropic's tests). Capture stays broad; sleep judges.
- Unresolved conflicts surfaced, not guessed; a passing remark never overrides a decision.
- A non-destructive pass: copy before, checks after, the captures leave the inbox only after the notes are written.
- Small records joined by links, and a size limit enforced by code.
- Nightly cadence over what is new since the last run; a failed night leaves the inbox for the next one.

Left out, and why:
- Hosted memory stores and the Dreams API: research preview, and the memory would leave the person's own Drive.
- Vector search and embeddings: a single person's memory is small enough for search by terms, and `search` matches the Drive connector's behavior.
- Model-written "insights" promoted on their own: for an executive, an insight is a recommendation on the board, approved by the person, never a fact.
- Parallel analyzers per transcript: worth it at hundreds of transcripts a night; one person produces a few dozen.

Open problems the research also names: how often to recheck notes against their sources without rechecking everything, and how to keep errors from accumulating across many passes. hippOS's answers today are `verified` with a 14-day limit on active initiatives and the independent reviewer; neither is measured yet.
