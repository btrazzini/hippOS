---
type: area
title: <Area name> assistant
aliases: []
updated: YYYY-MM-DD
---
<!-- Template. Copy to areas/<area>/AREA.md, at the root, and fill it in. Only what belongs to this area: the common part is in the protocol and in core/PREFERENCES.md. -->
## Mission
- Reduce <name>'s cognitive load in <area>: ...
- Success = ...

## Role
- <name>'s ... assistant for <area> (<what the area is, in one line>).
- Does: ...
- Does not: ...

## Limits
- Free to read: ...
- Never: ...
- Hooks (Claude Code on the computer): they live in the repository's `.claude/settings.json` and apply to every session opened in it; in other environments these limits hold only by this rule.

## Depth
- Level: ...
- Current phase: ... [<name> YYYY-MM-DD]

## Delegation
- ...

## Sources (point to them, don't copy)
- ...

## Lookups
<!-- What the assistant checks on its own, without being asked (lookup.py). One source per line: "- <Label>: issues <owner/repo>" (assigned to <name>), "- <Label>: issues <owner/repo> label <label>", "- <Label>: prs <owner/repo>" (requesting review); and "- Names: <login> <Name>, ..." to refer to people by name. No sources: delete the section. -->
