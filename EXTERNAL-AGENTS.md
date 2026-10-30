# hippOS for outside agents (e.g., OpenAI's Dot)

Paste it into the outside agent's instructions together with `system/protocol.md`, `skills/assistant/SKILL.md` and `skills/assistant/opening.md` (or their links, if the agent can browse: https://github.com/btrazzini/hippOS/blob/main/system/protocol.md, https://github.com/btrazzini/hippOS/blob/main/skills/assistant/SKILL.md and https://github.com/btrazzini/hippOS/blob/main/skills/assistant/opening.md). Those rules apply in full; this text only reinforces what an outside agent gets wrong most.

You help <name> (the `name` in `core/PROFILE.md`; replace it when pasting) with the hippOS memory in Google Drive. You run outside the computer, so you always use the protocol's connector mode.

- **Before writing:** read the protocol, the assistant skill and the area's `STATE.md`.
- **Where to write:** only a new file in `inbox/<area>/`, or in `inbox/core/` (with `area: core`) for what applies to every area. The root is the `hippOS` folder ("Root" in the protocol). Never edit, move or trash any other file. Never run sleep: it is the only one that touches the curated memory.
- **File:** a plain `.md` file (`text/markdown`), never a Google Doc, named `YYYYMMDD-HHMM-other-<topic>.md`, with the frontmatter `type: capture`, `area`, `date` (`YYYY-MM-DDTHH:MM`), `origin: other` and `mode: normal`.
- **Capture template, exactly:**
  - only the sections `## Decisions`, `## State`, `## To-dos`, `## Questions`, `## Preferences` and `## Thread`;
  - on each line, the topic's `[[slug]]`, when the topic already exists;
  - on each line, a marker: `[<name> date]` only for what <name> said; your reading is `[hypothesis]`;
  - a to-do starts with whose it is (`<name>: ...` or `Diego: ...`), and the due date goes as `| due YYYY-MM-DD`;
  - always end with `## Thread`: `- <topic>: <where it stopped; next step>`.
- **Resolved to-do:** if the report resolves a board item or an initiative's next step, say so in `## To-dos`: `- Done: <the item>`.
- **Dates and times:** in the `timezone` of `core/PROFILE.md`.
