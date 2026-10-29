# Inspirations

Outside projects we looked at while thinking about hippOS. We look out of curiosity. hippOS is memory for an executive (people, commitments, decisions, due dates), not for coding agents. Before bringing in any idea, the question is: "does this help an executive carry less in their head?". Copying another project's solution is not the goal.

This file is not read by the assistant or by sleep; it is for whoever changes the system.

## ai-memory

- Source: https://github.com/akitaonrails/ai-memory (read on 2026-10-29, commit `f32a9c5`).
- What it is: long-term memory for coding agents (Claude Code, Codex and others), with a server, a database, search and work handoff between agents. Its cycle (capture, consolidation, opening, handoff) is the same as hippOS's (capture, sleep, opening, thread).

Ideas we brought in:
- Checking the fidelity of consolidation without AI. Consolidation by a model tends to lose the literals (dates, amounts, PR and issue numbers, code, links); code checks whether they made it into the memory. Here: `memory.py fidelity`, in sleep's checking step.
- Rules with a budget. What the agent reads every session has a ceiling, and promoting a rule is subtractive: for one to come in, another leaves. Test for each line: would removing it make the agent err? Here: the word ceiling in `version.sh` and the rule in `AGENTS.md`.

Ideas kept for when the memory grows:
- Periodic cleanup of contradictions across a whole area (a statement another one contradicts, outdated information, duplicates), pointing out only real conflicts.
- Compacting what went cold: an unused topic becomes the facts that last, and the text goes to history, without deleting.
- History that doesn't vanish: a local git, outside Drive, with one commit per sleep, to answer "what did it look like on that date".

What doesn't fit here:
- Server, database, semantic search and many users: they solve a scale hippOS doesn't have.
- Automatic capture of everything through hooks: it makes sense for code; in an executive's conversation it becomes noise.
- Rewriting groups of pages by a model: sleep already consolidates, and the project itself keeps this off until it passes a retrieval test.

Common origin: Andrej Karpathy's "LLM wiki" pattern (ingest, query and lint, with an index and a log), which ai-memory itself cites.
