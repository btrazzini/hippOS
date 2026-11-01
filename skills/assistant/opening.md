# hippOS startup and opening, connector mode

Only without a shell, or where `python3 memory.py root` prints nothing; otherwise, `lookup.py opening` and `overview` do all of this. About 10 Drive calls before replying ("Drive access" in the protocol):
1. Find `MAP.md` ("Root" in the protocol) and read it with `download_file_content`: it gives the folder ids.
2. In a single search, find and read `core/PREFERENCES.md` and `core/PROFILE.md` (they override any default of yours), `core/PRINCIPLES.md` (<name>'s decision criteria: check them before recommending), `areas/<area>/AREA.md` (mission, role, limits, sources, lookups: you become this assistant), `areas/<area>/STATE.md` (opening, review, board, initiatives) and `core/STATE.md` (every area's due dates and waiting items).
3. List `inbox/<area>/` and `inbox/core/` in one search (`parentId = 'A' or parentId = 'B'`, `pageSize: 100`, follow `nextPageToken` until empty): not yet consolidated. Before replying, read every capture in `inbox/core/` (it may carry a new preference) and the area's, newest first, up to 10; past that, the ones touching the topic when it comes up.
- Warnings: suggest `/sleep`, with no area, when the area's `STATE.md` was generated over 3 days ago, the area inbox has more than 15 captures, or the `system_version` of `STATE.md` is older than this skill in its first two numbers. If newer, this environment's skill is outdated: say it needs reinstalling.

First reply: a message you write, nothing before or after, in <name>'s `language`: someone who works with <name> and has already looked at everything, talking to them. Plain sentences, about 60 words: no emojis, headings, lists, numbers or counts of what stays out, and never internal notation. First sentence: where you would start and why. Last sentence: one question, offering to start there (on Mondays, also the weekly review).
- Up to 4 items, in this order, from the area's `STATE.md` (`## Opening`) with the pending captures applied: overdue (due before today) with `for`, then the other overdue, oldest first; due dates in the next 7 days, or with none the first within 14; those beyond, inside their own `prep`; items with `for` and no due date, who waits the longest first; follow-ups (waiting on others overdue or quiet for 7 days; theirs to deliver, a nudge at most).
- Also say, in a clause each: its pinned list, always; the first line of the board's `## Attention`; today's next event; other areas with something overdue (`core/STATE.md`); warnings. With `gh`: what `## Lookups` of `AREA.md` shows waiting on <name> in the last 3 days, and PRs requesting review. Nothing presses and nothing is pinned: only the item marked "this turn" under without a date (do, date or drop?).
- Never a `#n` without its title. "Check" what the thread or a capture suggests already happened, when nothing recorded closes the item.

"What else?", "everything" or "what do I have open?": this list, nothing before or after (omit any block without content), labels in <name>'s `language`:
```
**<Area>** · <Thu, Oct 29> · thread: <thread in progress, or "none in progress"> · also in progress: <topic>; <topic>

**Today**
- <14:00> · <event> · you owe: <gist>; <person> owes: <gist>

**Attention** (sleep of <date>)
- <each line of the board's `## Attention`, as written>

**You asked not to forget** (<total>)

1. <date, or "since Oct 15"> · <the gist>

**Overdue** (done, postpone or drop?)

2. <date> · <the gist of the item>

**Next due dates** (<total>)

3. <today, tomorrow, "Fri Oct 30" or date> · **<Person>:** <the gist> (noted today)

**Coming up, as you asked** (<total>)

4. <date> · <the gist>

**Follow up** (<total>; nudge?)

5. <date, or "since Oct 15"> · **<Person>:** <the gist>

**Looked up now**
- <date> · <source> #<n> · <title> · <person> replied

**Requesting your review** (<total>)
- <date> · #<n> · <title> · <person> requested

**Waiting on you** (<total>)

6. <due date, if any> · <the gist> · since <date>

**Without a date** (<total>; do, date or drop?)

7. since <date> · <the gist>

**From other areas:** <Area, N overdue and 1 due tomorrow>

**Also:** <1 question for you; 2 parked; 1 decision to review>.

**Heads-up:** <protection hooks off, sleep pending or skill outdated, in one line>

Which topic?
```
- Up to 5 items per block, then "- and N more: <a>; <b>", numbered across blocks. Due dates: the next 7 days; with none, the first within 14. Coming up: those beyond, inside their own `prep`. Never a `#n` without its title. Gist: what comes before the first detail, within 100 characters. "(noted ...)": from a pending capture.
- Build it from the area's `STATE.md` (`## Opening`; overdue = due before today; follow up = waiting on others overdue or quiet for 7 days; pinned = its pinned list, unless already shown by date; `## Review` gives "Also"), with the pending captures applied, other areas from `core/STATE.md` (overdue or within 3 days; without a date for over 14 days: how many, since when) and, with `gh`, "Looked up now" from `## Lookups` of `AREA.md` (what waits on <name> in the last 3 days) and each PR requesting review; no hooks warning.
- Cloud session, where `gh` has no GraphQL or search (`gh pr list` and `gh issue list` fail): attach each repository of `## Lookups` with `add_repo`, access read, one at a time, never asking for write unless <name> asked for it; a denied one is said in "Looked up now" and the others go on. Then REST on each repository, `gh api`: `repos/<repo>/pulls?state=open&per_page=100` (those with their login in `requested_reviewers`, or any `requested_teams`, naming the team: its members can't be checked) and `repos/<repo>/issues?state=open&per_page=100&assignee=<login>`, or `&labels=<label>` (skip those with `pull_request`; who spoke last: `issues/<n>/comments`). Their login: `gh api user`, or their name in `Names`.
