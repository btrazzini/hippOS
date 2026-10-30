# hippOS startup and opening, connector mode

Only without a shell, or where `python3 memory.py root` prints nothing; otherwise, `lookup.py opening` does all of this. About 10 Drive calls before replying ("Drive access" in the protocol):
1. Find `MAP.md` ("Root" in the protocol) and read it with `download_file_content`: it gives the folder ids.
2. In a single search, find and read `core/PREFERENCES.md` and `core/PROFILE.md` (they override any default of yours), `core/PRINCIPLES.md` (<name>'s decision criteria: check them before recommending), `areas/<area>/AREA.md` (mission, role, limits, sources, lookups: you become this assistant), `areas/<area>/STATE.md` (opening, review, board, initiatives) and `core/STATE.md` (every area's due dates and waiting items).
3. List `inbox/<area>/` and `inbox/core/` in one search (`parentId = 'A' or parentId = 'B'`, `pageSize: 100`, follow `nextPageToken` until empty): not yet consolidated. Before replying, read every capture in `inbox/core/` (it may carry a new preference) and the area's, newest first, up to 10; past that, the ones touching the topic when it comes up.
- Warnings: suggest `/sleep`, with no area, when the area's `STATE.md` was generated over 3 days ago, the area inbox has more than 15 captures, or the `system_version` of `STATE.md` is older than this skill in its first two numbers. If newer, this environment's skill is outdated: say it needs reinstalling.

First reply: exactly this template, nothing before or after (omit any block without content), labels in <name>'s `language`:
```
**<Area>** · <Thu, Oct 29> · 🧵 <thread in progress, or "no thread in progress"> · also in progress: <topic>; <topic>

🗓️ **Today**
- <14:00> · <event> · you owe: <gist>; <person> owes: <gist>

🎯 **Attention** (sleep of <date>)
- <each line of the board's `## Attention`, as written>

📌 **You asked not to forget** (<total>)

1. <date, or "since Oct 15"> · <the gist>

> ⚠️ **Check:** <an item the thread or a capture suggests already happened>

🔴 **Overdue** (done, postpone or drop?)

2. <date> · <the gist of the item>

📅 **Next due dates** (<total>)

3. <today, tomorrow, "Fri Oct 30" or date> · **<Person>:** <the gist> (noted today)

🔭 **Coming up, as you asked** (<total>)

4. <date> · <the gist>

🔁 **Follow up** (<total>; nudge?)

5. <date, or "since Oct 15"> · **<Person>:** <the gist>

🔎 **Looked up now**
- <date> · <source> #<n> · <title> · <person> replied

👀 **Requesting your review** (<total>)
- <date> · #<n> · <title> · <person> requested

⏳ **Waiting on you** (<total>)

6. <due date, if any> · <the gist> · since <date>

🕸️ **Without a date** (<total>; do, date or drop?)

7. since <date> · <the gist>

🗂️ **From other areas:** <Area, N overdue and 1 due tomorrow>

➕ **Also:** <1 question for you; 2 parked; 1 decision to review>.

⚠️ **Heads-up:** <protection hooks off, sleep pending or skill outdated, in one line>

Which topic?
```
- Up to 5 items per block, then "- and N more: <a>; <b>", numbered across blocks. Due dates: the next 7 days; with none, the first within 14. Coming up: those beyond, inside their own `prep`. Never a `#n` without its title. Gist: what comes before the first detail, within 100 characters. "(noted ...)": from a pending capture.
- Build it from the area's `STATE.md` (`## Opening`; overdue = due before today; follow up = waiting on others overdue or quiet for 7 days; without a date = those marked "this turn"; pinned = its pinned list, unless already shown by date; `## Review` gives "Also"), with the pending captures applied, other areas from `core/STATE.md` (overdue or within 3 days; without a date for over 14 days: how many, since when) and, with `gh`, "Looked up now" from `## Lookups` of `AREA.md` (what waits on <name> in the last 3 days) and each PR requesting review; no hooks warning. "Check" only when nothing recorded closes the item.
