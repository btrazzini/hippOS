#!/usr/bin/env python3
"""hippOS lookups in an area's sources (GitHub, via gh). Python 3.8+, no dependencies.

The assistant runs this on its own, without waiting to be asked. Sources live in the
"## Lookups" section of the area's AREA.md, one per line:

  - <Label>: issues <owner/repo>              issues assigned to the owner
  - <Label>: issues <owner/repo> label <x>    issues with the label (all wait on the owner)
  - <Label>: prs <owner/repo>                 PRs requesting the owner's review
  - Names: <login> <Name>, <login> <Name>     to refer to people by name

Where gh's GraphQL is refused (a cloud session), the sources go through REST on each repository.

  opening <root> <area>    memory.py's opening with what GitHub adds to it
  overview <root> <area>   memory.py's overview with the "Looked up now" and review blocks
  owe     <root> <area>    what the owner owes: people, each source of the area and the rest
"""
import datetime as dt
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memory as m  # noqa: E402

DAYS_RECENT = 3
DAYS_STALLED = 30
OWE_ITEMS = 5
REF = re.compile(r"(?<![\w/])(?:#|PR #?)(\d{2,})\b(?! \()")  # "#123", "PR 123"
SOURCE = re.compile(r"^- ([^:]+): (issues|prs) (\S+/\S+)(?: label (.+))?$")


class NoGitHub(Exception):
    pass


class Refused(NoGitHub):
    """gh ran and was refused. A cloud session blocks GraphQL and search; REST on the repository may still answer."""


def gh(*args):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise NoGitHub("gh not installed")
    except subprocess.TimeoutExpired:
        raise NoGitHub("gh took too long")
    if r.returncode != 0:
        raise Refused((r.stderr.strip().splitlines() or ["gh error"])[-1][:80])
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


def rest(path, pages):
    """A REST list, page after page, up to `pages` of 100."""
    found = []
    for page in range(1, pages + 1):
        got = gh("api", f"{path}&per_page=100&page={page}")
        found += got
        if len(got) < 100:
            break
    return found


def rest_item(it):
    """A REST PR, issue or comment in the shape of gh's --json."""
    return {**it, "author": it["user"], "createdAt": it["created_at"]}


def prs_rest(repo, me):
    """Requests to the owner and to any team, named: a team's members are out of a cloud session's reach, and
    hiding one of the owner's reviews is worse than showing someone else's."""
    prs = []
    for p in rest(f"repos/{repo}/pulls?state=open", 5):
        teams = ", ".join(t["slug"] for t in p["requested_teams"])
        if me in [r["login"] for r in p["requested_reviewers"]]:
            prs.append(rest_item(p))
        elif teams:
            prs.append({**rest_item(p), "action": f"requested team {teams}"})
    return prs


def issues_rest(repo, me, label_filter):
    query = f"labels={quote(label_filter)}" if label_filter else f"assignee={quote(me)}"

    def with_comments(i):
        last_page = (i["comments"] - 1) // 100 + 1  # oldest first, so the last comment is on the last page
        comments = gh("api", f"repos/{repo}/issues/{i['number']}/comments?per_page=100&page={last_page}") if i["comments"] else []
        return {**rest_item(i), "comments": [rest_item(c) for c in comments]}

    issues = [i for i in rest(f"repos/{repo}/issues?state=open&{query}", 2) if "pull_request" not in i]
    with ThreadPoolExecutor(8) as pool:
        return list(pool.map(with_comments, issues))


def look_up(source, me):
    """The source's items, each with who spoke last, when, and whether it waits on the owner."""
    label, kind, repo, label_filter = source
    if kind == "prs":
        try:
            prs = gh("pr", "list", "-R", repo, "--state", "open", "--search", "review-requested:@me",
                     "--limit", "100", "--json", "number,title,author,createdAt")
        except Refused:
            prs = prs_rest(repo, me)
        return [{"n": p["number"], "title": p["title"], "who": p["author"]["login"], "action": p.get("action", "requested"),
                 "when": date(p["createdAt"]), "waiting": True} for p in prs]
    filter_ = ["--label", label_filter] if label_filter else ["--assignee", "@me"]
    try:
        issues = gh("issue", "list", "-R", repo, "--state", "open", "--limit", "200", *filter_,
                    "--json", "number,title,author,createdAt,comments")
    except Refused:
        issues = issues_rest(repo, me, label_filter)
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


def whoami(names):
    """The owner's login. A cloud session refuses `gh api user`; then, their own name in "Names" answers."""
    try:
        return gh("api", "user")["login"]
    except Refused:
        for login, name in names.items():
            if m.fold(name) == m.fold(m.NAME):
                return login
        raise NoGitHub("no login for you: add it to Names in AREA.md")


def everything(area):
    """[(source, items)] for every source, and the names map. Raises NoGitHub if gh fails."""
    found, names = sources(area)
    if not found:
        return [], names
    me = whoami(names)
    return [(s, look_up(s, me)) for s in found], names


def line(it, label, names, today):
    who = names.get(it["who"], it["who"])
    source = f"{label} " if label else ""
    return f"{m.short_date(it['when'], today)} · {source}#{it['n']} · {title(it['title'])} · {who} {it['action']}"


def waiting_now(area, today):
    """(items waiting on the owner in the last days with their source, PRs requesting their review, names); None
    with no source. Raises NoGitHub if gh fails."""
    result, names = everything(area)
    if not result:
        return None
    new, reviews = [], []
    for (label, kind, _, _), items in result:
        if kind == "prs":
            reviews += items
            continue
        new += [(it, label) for it in items if it["waiting"] and (today - it["when"]).days <= DAYS_RECENT]
    new.sort(key=lambda x: x[0]["when"], reverse=True)
    reviews.sort(key=lambda it: it["when"])
    return new, reviews, names


def looked_up_facts(area, today):
    """What GitHub adds to the opening: what is new for the owner, and who waits for a review, in a clause each."""
    try:
        found = waiting_now(area, today)
    except NoGitHub as e:
        return [f"GitHub: couldn't check ({e}); say so in a few words."]
    if not found:
        return []
    new, reviews, names = found
    facts = [f"New on GitHub, waiting on {m.NAME}: {line(it, label, names, today)}" for it, label in new[:OWE_ITEMS]]
    if reviews:
        facts.append(f"Review requested on GitHub ({len(reviews)}; only if the message is short of 60 words), oldest: {line(reviews[0], '', names, today)}")
    return facts


def looked_up_blocks(area, today):
    """What waits on the owner in the last days and every PR requesting their review, each with its title."""
    try:
        found = waiting_now(area, today)
    except NoGitHub as e:
        return [f"**Looked up now:** couldn't check GitHub ({e})."]
    if not found:
        return []
    new, reviews, names = found
    tag = lambda it: f"#{it['n']} {title(it['title'], m.TAG_MAX)}"
    blocks = [m.block("**Looked up now**", [line(it, label, names, today) for it, label in new],
                      [tag(it) for it, _ in new]) if new
              else f"**Looked up now:** nothing new waiting on you on GitHub in the last {DAYS_RECENT} days."]
    if reviews:
        blocks.append(m.block(f"**Requesting your review** ({len(reviews)})",
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
        theirs = sorted((it for it in items if it["waiting"]), key=lambda it: it["when"], reverse=True)
        stalled = sum(1 for it in items if (today - it["when"]).days > DAYS_STALLED)
        heading = f"**{label}** ({len(items)}) · " + (f"{len(theirs)} waiting on you" if theirs else "none waiting on you")
        if stalled:
            heading += f" · {stalled} stalled for over {DAYS_STALLED} days"
        blocks.append(m.block(heading, [line(it, "", names, today) for it in theirs],
                              [f"#{it['n']} {title(it['title'], m.TAG_MAX)}" for it in theirs], OWE_ITEMS))
    if error:
        blocks.append(f"**GitHub:** couldn't check ({error}).")
    if todos:
        blocks.append(m.block(f"**Your other to-dos** ({len(todos)})", [f"{due_of(it)}{m.gist(it['text'])}" for it in todos],
                              [m.tag(it["text"]) for it in todos], OWE_ITEMS))
    if waiting:
        blocks.append(f"**Waiting on you:** {waiting}")
    return "\n\n".join(blocks) + "\n\n" + m.for_agent()


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    if len(argv) < 4 or argv[1] not in ("opening", "overview", "owe"):
        print(__doc__)
        return 2
    root = Path(argv[2]).expanduser().resolve()
    if not root.exists():
        print(f"root does not exist: {root}")
        return 2
    m.configure(root)
    area = m.Area(root, m.area_from_argument(root, argv[3]))
    if argv[1] == "owe":
        print(owe(root, area))
        return 0
    if argv[1] == "overview":
        print(m.overview(root, area, looked_up_blocks(area, m.local_today()), describer(area)))
        return 0
    print(m.opening(root, area, looked_up_facts(area, m.local_today()), describer(area)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
