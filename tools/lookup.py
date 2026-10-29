#!/usr/bin/env python3
"""hippOS lookups in an area's sources (GitHub, via gh). Python 3.8+, no dependencies.

The assistant runs this on its own, without waiting to be asked. Sources live in the
"## Lookups" section of the area's AREA.md, one per line:

  - <Label>: issues <owner/repo>              issues assigned to the owner
  - <Label>: issues <owner/repo> label <x>    issues with the label (all wait on the owner)
  - <Label>: prs <owner/repo>                 PRs requesting the owner's review
  - Names: <login> <Name>, <login> <Name>     to refer to people by name

  opening <root> <area>    memory.py's opening with the "Looked up now" and review blocks
  owe     <root> <area>    what the owner owes: people, each source of the area and the rest
"""
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memory as m  # noqa: E402

DAYS_RECENT = 3
DAYS_STALLED = 30
OWE_ITEMS = 5
REF = re.compile(r"(?<![\w/])(?:#|PR #?)(\d{2,})\b(?! \()")  # "#123", "PR 123"
SOURCE = re.compile(r"^- ([^:]+): (issues|prs) (\S+/\S+)(?: label (.+))?$")


class NoGitHub(Exception):
    pass


def gh(*args):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise NoGitHub("gh not installed")
    except subprocess.TimeoutExpired:
        raise NoGitHub("gh took too long")
    if r.returncode != 0:
        raise NoGitHub((r.stderr.strip().splitlines() or ["gh error"])[-1][:80])
    return json.loads(r.stdout or "null")


def sources(area):
    """(label, kind, repo, label filter) of each source and the login -> name map, from AREA.md."""
    _, body = area.file("AREA.md") or ({}, "")
    found, names = [], {}
    for line in m.section(body, "Lookups"):
        if line.startswith("- Names:"):
            for pair in line[len("- Names:"):].split(","):
                login, _, name = pair.strip().partition(" ")
                if login and name:
                    names[login] = name.strip()
            continue
        s = SOURCE.match(line.strip())
        if s:
            found.append(s.groups())
    return found, names


def title(text, limit=60):
    """A short title that keeps the parenthesized ending (often who the issue is about)."""
    end = re.match(r"^(.*?)\s*(\([^()]*\))$", text)
    head, tail = (end.group(1), " " + end.group(2)) if end else (text, "")
    if len(head) + len(tail) > limit:
        head = head[:max(20, limit - len(tail))].rsplit(" ", 1)[0].rstrip(" -:,(") + "..."
    return head + tail


def date(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(m.TZ).date()


def look_up(source, me):
    """The source's items, each with who spoke last, when, and whether it waits on the owner."""
    label, kind, repo, label_filter = source
    if kind == "prs":
        prs = gh("pr", "list", "-R", repo, "--state", "open", "--search", "review-requested:@me",
                 "--limit", "100", "--json", "number,title,author,createdAt")
        return [{"n": p["number"], "title": p["title"], "who": p["author"]["login"], "action": "requested",
                 "when": date(p["createdAt"]), "waiting": True} for p in prs]
    filter_ = ["--label", label_filter] if label_filter else ["--assignee", "@me"]
    issues = gh("issue", "list", "-R", repo, "--state", "open", "--limit", "200", *filter_,
                "--json", "number,title,author,createdAt,comments")
    items = []
    for i in issues:
        last = i["comments"][-1] if i["comments"] else None
        who = (last or i)["author"]["login"]
        items.append({"n": i["number"], "title": i["title"], "who": who, "action": "replied" if last else "opened",
                      "when": date((last or i)["createdAt"]), "waiting": bool(label_filter) or who != me})
    return items


def describer(area):
    """Gives each "#123" in a text its title and state. The repository: the source named just before it
    ("Support #12"), the PR sources after "PR", or else the sources in AREA.md order."""
    found = sources(area)[0]
    order = lambda repos: list(dict.fromkeys(repos))
    cache = {}

    def resolve(ref):
        before = m.fold(ref.string[max(0, ref.start() - 30):ref.start()])
        named = [repo for label, _, repo, _ in found if m.fold(label) in before]
        prs = [repo for _, kind, repo, _ in found if kind == "prs"] if ref.group(0).startswith("PR") else []
        n = ref.group(1)
        for repo in order(named + prs + [repo for _, _, repo, _ in found]):
            if (repo, n) not in cache:
                try:
                    it = gh("api", f"repos/{repo}/issues/{n}")
                except NoGitHub:
                    cache[repo, n] = None
                    continue
                merged = (it.get("pull_request") or {}).get("merged_at")
                state = "merged" if merged else "open" if it["state"] == "open" else "closed"
                cache[repo, n] = f"{title(it['title'], 45)} · {state}"
            if cache[repo, n]:
                return f"{ref.group(0)} ({cache[repo, n]})"
        return ref.group(0)

    return lambda text: REF.sub(resolve, text)


def everything(area):
    """[(source, items)] for every source, and the names map. Raises NoGitHub if gh fails."""
    found, names = sources(area)
    if not found:
        return [], names
    me = gh("api", "user")["login"]
    return [(s, look_up(s, me)) for s in found], names


def line(it, label, names, today):
    who = names.get(it["who"], it["who"])
    source = f"{label} " if label else ""
    return f"{m.short_date(it['when'], today)} · {source}#{it['n']} · {title(it['title'])} · {who} {it['action']}"


def looked_up_blocks(area, today):
    """What waits on the owner in the last days and every PR requesting their review, each with its title."""
    try:
        result, names = everything(area)
    except NoGitHub as e:
        return [f"🔎 **Looked up now:** couldn't check GitHub ({e})."]
    if not result:
        return []
    new, reviews = [], []
    for (label, kind, _, _), items in result:
        if kind == "prs":
            reviews += items
            continue
        new += [(it, label) for it in items if it["waiting"] and (today - it["when"]).days <= DAYS_RECENT]
    new.sort(key=lambda x: x[0]["when"], reverse=True)
    reviews.sort(key=lambda it: it["when"])
    tag = lambda it: f"#{it['n']} {title(it['title'], m.TAG_MAX)}"
    blocks = [m.block("🔎 **Looked up now**", [line(it, label, names, today) for it, label in new],
                      [tag(it) for it, _ in new]) if new
              else f"🔎 **Looked up now:** nothing new waiting on you on GitHub in the last {DAYS_RECENT} days."]
    if reviews:
        blocks.append(m.block(f"👀 **Requesting your review** ({len(reviews)})",
                              [line(it, "", names, today) for it in reviews], [tag(it) for it in reviews]))
    return blocks


def owe(root, area):
    today = m.local_today()
    try:
        result, names = everything(area)
        error = None
    except NoGitHub as e:
        result, names, error = [], sources(area)[1], e
    people, todos, waiting = m.owed(area, names.values())
    due_of = lambda it: m.short_date(it["due"], today, it["approx"]) + " · " if it["due"] else ""
    blocks = [f"**What you owe · {m.area_title(area.name)}**"]
    if people:
        blocks.append(m.block(f"**People** ({len(people)})",
                              [f"{due_of(it)}**{it['for']}** · {m.short(it['text'])}" for it in people],
                              [m.tag(it["text"]) for it in people], OWE_ITEMS))
    else:
        blocks.append("**People:** nobody waiting on you, as far as the records go.")
    for (label, kind, _, _), items in result:
        if kind == "prs":
            lines = [line(it, "", names, today) for it in items]
            tags = [f"#{it['n']} {title(it['title'], m.TAG_MAX)}" for it in items]
            blocks.append(m.block(f"**{label}** ({len(items)})", lines, tags, OWE_ITEMS) if items
                          else f"**{label}:** no PR requesting your review.")
            continue
        waiting = sorted((it for it in items if it["waiting"]), key=lambda it: it["when"], reverse=True)
        stalled = sum(1 for it in items if (today - it["when"]).days > DAYS_STALLED)
        heading = f"**{label}** ({len(items)}) · " + (f"{len(waiting)} waiting on you" if waiting else "none waiting on you")
        if stalled:
            heading += f" · {stalled} stalled for over {DAYS_STALLED} days"
        blocks.append(m.block(heading, [line(it, "", names, today) for it in waiting],
                              [f"#{it['n']} {title(it['title'], m.TAG_MAX)}" for it in waiting], OWE_ITEMS))
    if error:
        blocks.append(f"**GitHub:** couldn't check ({error}).")
    if todos:
        blocks.append(m.block(f"**Your other to-dos** ({len(todos)})", [f"{due_of(it)}{m.gist(it['text'])}" for it in todos],
                              [m.tag(it["text"]) for it in todos], OWE_ITEMS))
    if waiting:
        blocks.append(f"**Waiting on you:** {waiting}")
    return "\n\n".join(blocks)


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    if len(argv) < 4 or argv[1] not in ("opening", "owe"):
        print(__doc__)
        return 2
    root = Path(argv[2]).expanduser()
    if not root.exists():
        print(f"root does not exist: {root}")
        return 2
    m.configure(root)
    area = m.Area(root, m.area_from_argument(root, argv[3]))
    if argv[1] == "owe":
        print(owe(root, area))
        return 0
    print(m.opening(root, area, looked_up_blocks(area, m.local_today()), describer(area)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
