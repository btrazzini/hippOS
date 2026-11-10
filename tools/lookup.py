#!/usr/bin/env python3
"""hippOS lookups in an area's sources (GitHub, via gh). Python 3.8+, no dependencies.

The assistant runs this on its own, without waiting to be asked. Sources live in the
"## Lookups" section of the area's AREA.md, the area's watch points, one per line:

  - <Label>: issues <owner/repo>              issues assigned to the owner
  - <Label>: issues <owner/repo> label <x>    issues with the label (all wait on the owner)
  - <Label>: prs <owner/repo>                 PRs requesting the owner's review
  - Names: <login> <Name>, <login> <Name>     to refer to people by name
  - <Label>: <anything else, in words>        a watch point the agent looks at with a connector, in conversation
                                              ("Google Tasks, list Work: what is due by tomorrow")

Each GitHub item is triaged against the memory: placed (the memory names it: a board item, a record, a capture),
moved (someone spoke after that), new, or never placed. Only moved and new ones are brought up.

Where gh's GraphQL is refused (a cloud session), the sources go through REST on each repository.

  opening <root> <area>    memory.py's opening with what GitHub adds to it: what waits on the owner, what was
                           merged lately, their open issues and what the memory holds open that GitHub shows closed
  overview <root> <area>   memory.py's overview with the "Looked up now" and review blocks
  owe     <root> <area>    what the owner owes: people, each source of the area and the rest
  recheck <root> <area>    for sleep: what the memory holds open (board, `next`, ## Open) whose PR or issue is closed
  watch   <root> <area> [--write]   for sleep: what the watch points show now, as the area's WATCH.md
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
DAYS_PULSE = 7  # merged PRs the opening is told about
PULSE_PEOPLE = 4
PULSE_THEMES = 3
STALE_ITEMS = 5
WATCH_ITEMS = 30  # never-placed items WATCH.md names per source
DAY = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
OWE_ITEMS = 5
REF = re.compile(r"(?<![\w/])(?:#|PR #?)(\d{2,})\b(?! \()")  # "#123", "PR 123"
ANY_REF = re.compile(r"(?:\b([\w.-]+(?:/[\w.-]+)?)#|(?<![\w/])(?:#|PR #?))(\d{2,})\b")  # also "owner/repo#123", "repo#123"
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


def points(area):
    """The watch points no code reaches (a connector does): (label, what to look at, in the owner's words)."""
    _, body = area.file("AREA.md") or ({}, "")
    lines = [l.strip() for l in m.section(body, "Lookups")]
    plain = [re.match(r"^- ([^:]{1,40}):\s+(.+)$", l) for l in lines
             if not SOURCE.match(l) and not l.startswith("- Names:") and "..." not in l]
    return [p.groups() for p in plain if p]


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


def same_repo(hint, repo, label):
    """A reference's written repository ("owner/repo", "repo" or the source's label) names this one."""
    return m.fold(hint) in (m.fold(repo), m.fold(repo.split("/")[-1]), m.fold(label))


def homes(area):
    """{number: [(repository as written or None, day)]} for every PR or issue the memory names (board, log, records,
    pending captures): the latest day on the line, never ahead of today, else the file's. Naming it is placing it:
    the owner decided what happens to it, so it stops coming back until someone speaks after that day."""
    today = m.local_today()
    files = [area.folder / "BOARD.md", area.folder / "LOG.md", *sorted((area.folder / "log").glob("*.md")),
             *[path for path, _, _ in area.records.values()], *area.inbox]
    found = {}
    for path in files:
        if not path.exists():
            continue
        saved = dt.date.fromtimestamp(path.stat().st_mtime)
        for text in m.text_of(path).splitlines():
            for ref in ANY_REF.finditer(text):
                days = [d for d in map(m.iso_date, DAY.findall(text)) if d and d <= today]
                found.setdefault(int(ref.group(2)), []).append((ref.group(1), max(days) if days else saved))
    return found


def triage(source, items, home, today):
    """The source's items by what the memory did with them: moved (placed, and someone else spoke after), new (never
    placed, someone else spoke in the last days), unplaced (never placed otherwise) and placed (quiet since)."""
    label, _, repo, _ = source
    out = {"moved": [], "new": [], "unplaced": [], "placed": []}
    for it in items:
        days = [day for hint, day in home.get(it["n"], []) if not hint or same_repo(hint, repo, label)]
        if not days:
            out["new" if it["waiting"] and (today - it["when"]).days <= DAYS_RECENT else "unplaced"].append(it)
        else:
            out["moved" if it["waiting"] and it["when"] > max(days) else "placed"].append(it)
    for rows in out.values():
        rows.sort(key=lambda it: it["when"], reverse=True)
    return out


def resolver(area):
    """Looks a "#123" up: {title, state (open, merged, closed), when it closed} or None. The repository: the one
    written with it ("owner/repo#12"), the source named just before it ("Support #12"), the PR sources after "PR",
    or else the sources in AREA.md order."""
    found = sources(area)[0]
    cache = {}

    def fetch(repo, n):
        if (repo, n) not in cache:
            try:
                it = gh("api", f"repos/{repo}/issues/{n}")
            except NoGitHub:
                cache[repo, n] = None
            else:
                merged = (it.get("pull_request") or {}).get("merged_at")
                state = "merged" if merged else "open" if it["state"] == "open" else "closed"
                closed = merged or it.get("closed_at")
                cache[repo, n] = {"title": it["title"], "state": state, "when": date(closed) if closed else None}
        return cache[repo, n]

    def resolve(ref):
        if ref.re is ANY_REF and ref.group(1):
            hinted = [repo for label, _, repo, _ in found if same_repo(ref.group(1), repo, label)]
            repo = hinted[0] if hinted else ref.group(1) if "/" in ref.group(1) else None
            return fetch(repo, ref.group(2)) if repo else None
        n = ref.group(ref.re.groups)
        before = m.fold(ref.string[max(0, ref.start() - 30):ref.start()])
        named = [repo for label, _, repo, _ in found if m.fold(label) in before]
        prs = [repo for _, kind, repo, _ in found if kind == "prs"] if ref.group(0).startswith("PR") else []
        for repo in dict.fromkeys(named + prs + [repo for _, _, repo, _ in found]):
            got = fetch(repo, n)
            if got:
                return got
        return None

    return resolve


def describer(area):
    """Gives each "#123" in a text its title and state."""
    resolve = resolver(area)

    def described(ref):
        got = resolve(ref)
        return f"{ref.group(0)} ({title(got['title'], 45)} · {got['state']})" if got else ref.group(0)

    return lambda text: REF.sub(described, text)


def held_open(area, today):
    """[(where, text, ref, looked up)] for what the memory holds open (board items, the `next` of active initiatives,
    `## Open` lines) naming a PR or issue GitHub shows merged or closed. Work may remain after it, so this is a
    question to settle, not a verdict."""
    places = [(f"BOARD.md ({it['section']})", it["text"]) for it in m.open_items(area)]
    for slug, (path, meta, body) in sorted(area.records.items()):
        if meta.get("status") in ("done", "cancelled", "superseded", "discarded"):
            continue
        where = f"{path.parent.name}/{path.name}"
        if meta.get("type") == "initiative" and meta.get("status") == "active" and meta.get("next"):
            places.append((f"{where} next", meta["next"]))
        places += [(f"{where} ## Open", l[2:]) for l in m.section(body, "Open")]
    refs = [(where, text, ref) for where, text in places for ref in ANY_REF.finditer(text)]
    resolve = resolver(area)
    with ThreadPoolExecutor(8) as pool:
        looked = list(pool.map(lambda r: resolve(r[2]), refs))
    held = {(where, text, ref.group(0)): got for (where, text, ref), got in zip(refs, looked) if got and got["state"] != "open"}
    return [(*key, got) for key, got in held.items()]


def closed_line(text, ref, got, today):
    when = f" {m.short_date(got['when'], today)}" if got["when"] else ""
    return f"{m.short(text)} · {ref} ({title(got['title'], 45)}) {got['state']}{when}"


def merged_lately(repo, today):
    """PRs merged into the repository in the last DAYS_PULSE days: [(author login, title)]."""
    since = today - dt.timedelta(days=DAYS_PULSE)
    try:
        prs = gh("pr", "list", "-R", repo, "--state", "merged", "--search", f"merged:>={since.isoformat()}",
                 "--limit", "300", "--json", "title,author,mergedAt")
        return [(p["author"]["login"], p["title"]) for p in prs]
    except Refused:
        prs = rest(f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc", 3)
        return [(p["user"]["login"], p["title"]) for p in prs if p.get("merged_at") and date(p["merged_at"]) >= since]


def pulse(area, names, today):
    """What moved: per repository of the PR sources, how many PRs were merged lately, by whom and on what (the
    title's subject, before " - ")."""
    facts = []
    for repo in dict.fromkeys(repo for _, kind, repo, _ in sources(area)[0] if kind == "prs"):
        merged = merged_lately(repo, today)
        if not merged:
            facts.append(f"Merged into {repo} in the last {DAYS_PULSE} days: none.")
            continue
        by = {}
        for login, text in merged:
            by.setdefault(names.get(login, login), []).append(text.split(" - ")[0].strip()[:30])
        people = []
        for who, themes in sorted(by.items(), key=lambda x: -len(x[1]))[:PULSE_PEOPLE]:
            top = sorted(set(themes), key=lambda t: -themes.count(t))[:PULSE_THEMES]
            people.append(f"{who} {len(themes)} ({', '.join(f'{t} {themes.count(t)}' for t in top)})")
        rest_ = len(by) - PULSE_PEOPLE
        facts.append(f"Merged into {repo} in the last {DAYS_PULSE} days: {len(merged)} PRs. " + "; ".join(people)
                     + (f"; and {rest_} more people" if rest_ > 0 else "") + ". The memory may not have caught up with these.")
    return facts


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
    """What the watch points add to the opening: per GitHub source, what moved or is new against the memory; what
    was merged lately; what the memory holds open that GitHub shows closed; and the points a connector reaches."""
    asks = points(area)
    live = ([f"Watch points to look at now, with the connectors this environment has (load their tools if deferred); "
             f"one you can't reach, say so in a few words:"] + [f"- {label}: {what}" for label, what in asks]) if asks else []
    try:
        result, names = everything(area)
        if not result:
            return live
        home = homes(area)
        facts = [f"On GitHub, looked up now (only what is assigned to {m.NAME} or asks for their review; look no further "
                 "unless asked):"]
        unplaced = 0
        for source, items in result:
            t = triage(source, items, home, today)
            unplaced += len(t["unplaced"])
            counts = [f"{len(t[k])} {words}" for k, words in (("moved", "moved after being placed"), ("new", "new"),
                      ("unplaced", "never placed"), ("placed", "placed and quiet")) if t[k]]
            facts.append(f"- {source[0]}: {len(items)} open" + (f" · {', '.join(counts)}" if counts else ""))
            facts += [f"  - {kind}: {line(it, '', names, today)}" for kind in ("moved", "new") for it in t[kind][:OWE_ITEMS]]
        if unplaced:
            facts.append(f"- Never placed ({unplaced}): don't list them unasked. Offer once, in a clause, to go through them "
                         f"a few at a time, grouped by the work in motion each belongs to. What {m.NAME} decides about one "
                         "(later, not theirs, part of an initiative) is a capture naming its `<repo>#<n>`: that places it.")
        facts += [f"- {f}" for f in pulse(area, names, today)]
        held = held_open(area, today)
        if held:
            facts += ["", f"Recorded as open, but GitHub shows it closed (ask {m.NAME} whether it is done; don't assert it):"]
            facts += [f"- {closed_line(text, ref, got, today)}" for _, text, ref, got in held[:STALE_ITEMS]]
            facts += [f"- and {len(held) - STALE_ITEMS} more (lookup.py recheck)"] if len(held) > STALE_ITEMS else []
        return facts + ([""] + live if live else [])
    except NoGitHub as e:
        return [f"GitHub: couldn't check ({e}); say so in a few words."] + ([""] + live if live else [])


def watch(root, area, write=False):
    """The area's WATCH.md: what the watch points showed when sleep looked, for the sessions that can't reach
    GitHub (chat, voice). Generated, never edited; with no GitHub source or no gh, nothing is written."""
    today = m.local_today()
    try:
        result, names = everything(area)
        if not result:
            return "no GitHub source in ## Lookups: no WATCH.md"
        home = homes(area)
        out = ["---", "type: watch", f"area: {area.name}", f"generated: {m.now()}", f"system_version: {m.VERSION}", "---",
               f"# Watch of area {area.name} (generated by sleep; do not edit)", "",
               "What GitHub showed at `generated`, against the memory: say it as of then. Placed = the memory names it.", ""]
        for source, items in result:
            label, kind, repo, _ = source
            t = triage(source, items, home, today)
            out.append(f"## {label} ({kind} {repo}): {len(items)} open")
            for key, title_ in (("moved", "Moved after being placed"), ("new", "New"), ("unplaced", "Never placed")):
                rows = t[key][:WATCH_ITEMS]
                out += [f"- {title_} ({len(t[key])}):" + ("" if rows else " none")] + [f"  - {line(it, '', names, today)}" for it in rows]
                out += [f"  - and {len(t[key]) - len(rows)} more"] if len(t[key]) > len(rows) else []
            out += [f"- Placed and quiet: {len(t['placed'])}", ""]
        out += ["## Merged lately"] + [f"- {f}" for f in pulse(area, names, today)] + [""]
        held = held_open(area, today)
        out += ["## Held open in the memory, closed on GitHub"]
        out += [f"- {closed_line(text, ref, got, today)}" for _, text, ref, got in held] or ["- none"]
        text = "\n".join(out) + "\n"
    except NoGitHub as e:
        return f"couldn't check GitHub ({e}); WATCH.md left as it was"
    if write:
        (area.folder / "WATCH.md").write_text(text, encoding="utf-8")
        return f"areas/{area.name}/WATCH.md written"
    return text


def recheck(root, area):
    """For sleep: each open place in the memory naming a PR or issue that GitHub shows merged or closed."""
    today = m.local_today()
    try:
        held = held_open(area, today)
    except NoGitHub as e:
        return f"couldn't check GitHub ({e}); nothing rechecked"
    if not held:
        return "nothing held open in the memory is closed on GitHub"
    out = [f"Held open in the memory, closed on GitHub ({len(held)}). For each: close it (board item to LOG.md, `next` "
           f"rewritten) with [fact {today}: gh] if nothing else is left to do, or keep it and say what is left.", ""]
    out += [f"- {where} · {closed_line(text, ref, got, today)}" for where, text, ref, got in held]
    return "\n".join(out + ["", m.DATA_ONLY])


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
    if len(argv) < 4 or argv[1] not in ("opening", "overview", "owe", "recheck", "watch"):
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
    if argv[1] == "recheck":
        print(recheck(root, area))
        return 0
    if argv[1] == "watch":
        print(watch(root, area, "--write" in argv[4:]))
        return 0
    if argv[1] == "overview":
        print(m.overview(root, area, looked_up_blocks(area, m.local_today()), describer(area)))
        return 0
    print(m.opening(root, area, looked_up_facts(area, m.local_today()), describer(area)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
