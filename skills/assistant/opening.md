# hippOS opening, connector mode

Only where `lookup.py opening` can't run; it delivers this same opening ready. First reply: exactly this template, nothing before or after (omit any block without content), labels in <name>'s `language`:
```
**<Area>** · <Thu, Oct 29> · 🧵 <thread in progress, or "no thread in progress"> · also in progress: <topic>; <topic>

🗓️ **Today**
- <14:00> · <event> · you owe: <gist>; <person> owes: <gist>

🎯 **Attention** (sleep of <date>)
- <each line of the board's `## Attention`, as written>

> ⚠️ **Check:** <an item the thread or a capture suggests already happened>

🔴 **Overdue** (done, postpone or drop?)

1. <date> · <the gist of the item>

📅 **Next due dates** (<total>)

2. <today, tomorrow, "Fri Oct 30" or date> · **<Person>:** <the gist> (noted today)

🔁 **Follow up** (<total>; nudge?)

3. <date, or "since Oct 15"> · **<Person>:** <the gist>

🔎 **Looked up now**
- <date> · <source> #<n> · <title> · <person> replied

👀 **Requesting your review** (<total>)
- <date> · #<n> · <title> · <person> requested

⏳ **Waiting on you** (<total>)

4. <due date, if any> · <the gist> · since <date>

🕸️ **Without a date** (<total>; do, date or drop?)

5. since <date> · <the gist>

🗂️ **From other areas:** <Area, N overdue and 1 due tomorrow>

➕ **Also:** <1 question for you; 2 parked; 1 decision to review>.

⚠️ **Heads-up:** <protection hooks off, sleep pending or skill outdated, in one line>

Which topic?
```
- Up to 5 items per block, then "- and N more: <a>; <b>", numbered across blocks. Due dates: the next 7 days; with none, the first within 14. Never a `#n` without its title. Gist: what comes before the first detail, within 100 characters. "(noted ...)": from a pending capture.
- Build it from the area's `STATE.md` (`## Opening`; overdue = due before today; follow up = waiting on others overdue or quiet for 7 days; without a date = those marked "this turn"; `## Review` gives "Also"), with the pending captures applied, other areas from `core/STATE.md` (overdue or within 3 days; without a date for over 14 days: how many, since when) and, with `gh`, "Looked up now" from `## Lookups` of `AREA.md` (what waits on <name> in the last 3 days) and each PR requesting review; no hooks warning. "Check" only when nothing recorded closes the item.
