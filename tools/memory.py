#!/usr/bin/env python3
"""hippOS memory tool. Python 3.8+, no dependencies.

Works on a local copy of the memory root in Drive (or the synced folder itself).
Never touches the network. The owner's name and timezone come from the frontmatter
of core/PROFILE.md (`name`, `timezone`).

  root                                   the root in Google Drive for desktop (Mac or Windows); HIPPOS_ROOT sets another
  new      <root> <name> <timezone> <language>   creates a memory from templates/ (never over an existing one)
  area     <root> <area> [alias ...]     adds an area from templates/ (never over an existing one)
  validate <root> [area|core|all]        schema, links, captures, board, overdue, files outside the schema
  pending  <root>                        what sleep with no argument processes, and why
  state    <root> <area> [--write]       generates areas/<area>/STATE.md
  core     <root> [--write] [--ids f]    generates core/STATE.md and MAP.md
  opening  <root> <area>                 first reply, ready, computed now
  (GitHub and other area sources: tools/lookup.py)
  brief    <root> [YYYY-MM-DD]           every area at once: overdue, due dates (to a date), follow-ups
  review   <root> <area|all>             what waits without a date or went quiet (the weekly review)
  person   <root> <name>                 everything open with someone, in every area
  index    <root> <area>                 every record by type and status
  context  <root> <area> <slug>          the record and its neighbors
  fidelity <root> <area> [capture ...]   capture literals, to-dos and questions missing from the memory
  digest   <root> <area>                 the area on one screen, for sleep to write ## Attention
  archive  <root> <area>                 moves LOG.md entries over 30 days old to log/<YYYY-MM>.md
  capture  <root> <area> <origin> <topic> [--forget]   writes a capture from stdin; refuses malformed fields
"""
import calendar
import datetime as dt
import difflib
import json
import os
import re
import string
import subprocess
import sys
import unicodedata
from pathlib import Path

VERSION = "0.3.0"
TZ = dt.datetime.now().astimezone().tzinfo  # TZ, NAME, MARKER and NOTATION: configure(), from PROFILE.md
NAME = "owner"
SPEAKS = "en"  # the owner's `language`; what memory.py prints is in English and the agent translates it
DAYS_STALE = 14
DAYS_AGED = 14
DAYS_STATE = 3
DAYS_OTHER_AREAS = 3
DAYS_NEXT = 7  # due dates in the opening
DAYS_AHEAD = 14  # with none in DAYS_NEXT, the first one up to here; further out only weighs on the screen
DAYS_FOLLOW_UP = 7  # waiting on others with no due date and no news for longer: time to nudge
DAYS_WAITING = 7  # "Waiting on you" says since when, past this
DAYS_LOG = 30  # LOG.md keeps this many days; older entries go to log/<YYYY-MM>.md
ATTENTION_MAX = 5  # lines sleep writes for the top of the opening
BOARD_MAX_LINES = 80
BOARD_MAX_BYTES = 9000
INBOX_MAX = 15
THREADS = 3  # threads in progress kept on the board, one per topic
REVIEW_DAY = 0  # Monday: the opening offers the weekly review
OTHERS = "Waiting on others"
ITEM_SECTIONS = ("Waiting on", OTHERS, "Loose ends", "Questions for")  # "Waiting on <name>", "Questions for <name>"
BOARD_SECTIONS = ITEM_SECTIONS + ("Thread",)
AGING_SECTIONS = ("Waiting on", "Questions for")
DONE = re.compile(r"^- (?:done|dropped|resolved)\b:?\s*(.+)", re.I)
CAPTURE_SECTIONS = ("Decisions", "State", "To-dos", "Questions", "Preferences", "Thread")
EMPTY = {"none", "nothing"}
TEXT_MAX = 100
TAG_MAX = 30  # an item named in the "and N more" line
BLOCK_ITEMS = 5
UNDATED_ITEMS = 3  # open items without a due date shown per day, in rotation
AGENT_SEPARATOR = "----- agent only, do not show -----"
CALENDAR = ("Calendar: if this environment has a calendar connector (load its tools if deferred), read today's remaining "
            "events before replying; with any, add a 🗓️ block right after the first line, `HH:MM · title`, and for "
            "someone with open items what each side owes (memory.py person <root> <name>).")
PREFERENCES_MAX = 500  # words; read every session: for a rule to come in, another leaves or merges
TOPIC_MAX = 800  # words; above it, sleep splits the topic
CURRENCIES = ("R$", "US$", "$", "€", "£")
# Literals consolidation tends to lose: amounts, code, links, issues and PRs, dates, numbers
LITERAL = re.compile(r"(?:R\$|US\$|\$|€|£)\s?\d[\d.,]*|`[^`\n]{2,80}`|https?://[^\s)>\]]+|\b[\w.-]+/[\w.-]+#\d+|#\d{2,}"
                     r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}(?:/\d{2,4})?\b|\b\d{3,}\b")
LEFT_ON_PURPOSE = re.compile(r"^- (done|resolved|dropped|cancel|discard)", re.I)
FOLDERS = ("initiatives", "decisions", "topics")
BOARD_OPTIONAL = ("Phase", "Priorities", "Attention")  # the board's sections beyond the required ones
RECORD_DATED = ("Risks", "Consequences", "Open")  # where a record may hide a commitment, besides `next`
ATTENTION_MARKER = re.compile(r"\[recommendation (\d{4}-\d{2}-\d{2})\b")
FULL_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}(?:/\d{2,4})?")
AREA_FILES = ("AREA.md", "BOARD.md", "LOG.md", "STATE.md", "CHANGELOG.md")
CORE_FILES = ("PROFILE.md", "PREFERENCES.md", "PRINCIPLES.md", "STATE.md", "CHANGELOG.md")
ROOT_FILES = ("MAP.md", "SLEEP-IN-PROGRESS.md")
CONFLICT_COPY = re.compile(r" \(\d+\)$")  # how Google Drive names a conflict copy
LISTS = ("depends_on", "unblocks", "decisions", "affects", "amends", "links")
SIMPLE_REFS = ("supersedes", "superseded_by")
ORIGINS = {"claude-chat", "claude-code", "codex", "other"}
MODES = {"normal", "forget"}
STATUS = {
    "initiative": {"active", "paused", "done", "cancelled"},
    "decision": {"proposed", "approved", "superseded", "discarded"},
}
PRIORITIES = {"high", "medium", "low", "tbd"}
SECRETS = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\bghp_[A-Za-z0-9]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b|\bxox[bp]-[A-Za-z0-9-]{10,}|\b(?:password|senha)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
LINK = re.compile(r"\[\[([^\]]+)\]\]")
# A date in free text: ISO, dd/mm or mm/dd, or a day named in words (content is in the owner's language).
# Not "today": "até hoje" means "so far". Not "até segunda ordem": "until further notice".
TEXT_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|tomorrow|amanh[ãa]"
                       r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
                       r"|segunda(?!\s+ordem)|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo)\b", re.I)
# Words right before a date that make it look like a due date
DUE_WORDS = re.compile(r"\b(?:by|due(?: on| by)?|deadline:?|until|before|around|renews?(?: on)?"
                       r"|até|vence(?: em)?|prazo:?|por volta de|renova(?: em)?)\s*$")
ABBREVIATION = re.compile(r"\b[A-Z][a-z]{1,3}$")  # "Dr", "Sra", "Prof" right before a period
CAPTURE_NAME = re.compile(r"^\d{8}-\d{4}-[a-z-]+-[a-z0-9-]+\.md$")
FIELD = re.compile(r"^(since|due|last):?\s+(~?)(\S+)$")
FIELD_FOR = re.compile(r"^for:?\s+(.+)$")
FIELD_PREP = re.compile(r"^prep:?\s+(\S+)$")
FIELD_EVERY = re.compile(r"^every:?\s+(.+)$")
PREP = re.compile(r"^[0-9]{1,4}$")
EVERY = re.compile(r"^(?:([1-9][0-9]{0,2})\s+)?(day|week|month|year)s?$")  # n = 0 would never move on
NOT_DONE = re.compile(r"^- (?:feito|feita|conclu[ií]d[oa]|pront[oa]|finished|completed)\s*:", re.I)  # the marker is "Done:"
DROPPED = re.compile(r"^- dropped\b", re.I)
MARKERS = r"fact|{name}|inherited|hypothesis|recommendation"
WITH_AREA = ("validate", "state", "opening", "review", "index", "context", "fidelity", "digest", "archive", "capture")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ROOT_NAME = "hippOS"  # the memory folder, directly in My Drive
LIMIT_LISTS = {"Never run": "run", "Never open": "open", "Read only": "read_only"}  # AREA.md `## Limits`, read by guard.py
BACKTICKED = re.compile(r"`([^`]+)`")
DRIVES = ("My Drive", "Meu Drive", "Mi unidad", "Mon Drive", "Meine Ablage", "Il mio Drive")


# ---------- reading ----------

def text_of(path):
    """A file's text; a BOM is dropped and bytes that aren't UTF-8 become \ufffd (the validator flags them)."""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def unquote(value):
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value


def read(path):
    """Frontmatter (flat `key: value`, quotes dropped, block lists turned into `[a, b]`) and body."""
    text = text_of(path)
    meta, body = {}, text
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                block = None
                for line in lines[1:i]:
                    if block and line.strip().startswith("- "):
                        meta[block].append(unquote(line.strip()[2:].strip()))
                        continue
                    block = None
                    if ":" in line and not line.startswith((" ", "\t")):
                        key, value = line.split(":", 1)
                        meta[key.strip()] = unquote(value.strip())
                        if not meta[key.strip()]:
                            block, meta[key.strip()] = key.strip(), []
                meta = {k: (f"[{', '.join(v)}]" if v else "") if isinstance(v, list) else v for k, v in meta.items()}
                body = "\n".join(lines[i + 1:])
                break
    return meta, body


def timezone(name):
    """IANA timezone (e.g. America/New_York); without it, or without a tz database (Windows without tzdata), the machine's."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except (ImportError, TypeError, ValueError, KeyError):
        return dt.datetime.now().astimezone().tzinfo


def markers(name):
    """The statement marker and the whole notation (markers and links), with the owner's name."""
    m = MARKERS.format(name=re.escape(name))
    return re.compile(rf"\[(?:{m})\b[^\]]*\]"), re.compile(rf"\[(?:{m})[^\]]*\]|\[\[[^\]]+\]\]")


MARKER, NOTATION = markers(NAME)


def configure(root):
    """The owner's name and timezone, from the frontmatter of core/PROFILE.md, for texts, markers and dates."""
    global NAME, TZ, MARKER, NOTATION, SPEAKS
    profile = root / "core" / "PROFILE.md"
    meta = read(profile)[0] if profile.exists() else {}
    NAME = meta.get("name") or "owner"
    SPEAKS = meta.get("language") or "en"
    TZ = timezone(meta.get("timezone"))
    MARKER, NOTATION = markers(NAME)


def known_timezone(name):
    """False only when a timezone database is available and lacks the name (Windows may have none)."""
    try:
        from zoneinfo import available_timezones
    except ImportError:
        return True
    zones = available_timezones()
    return not zones or name in zones


def fold(text):
    """For comparing names: no case, accents or surrounding spaces."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().strip()


def find_roots():
    """Local-mode roots: HIPPOS_ROOT, if set; otherwise the hippOS folder at the top of each Google Drive for desktop.

    Mac: ~/Library/CloudStorage/GoogleDrive-<account>/My Drive/hippOS. Windows: <letter>:/My Drive/hippOS
    or, mirrored, ~/My Drive/hippOS. "My Drive" goes by another name with Drive in another language.
    Several (one per Google account): the one whose MAP.md sleep rewrote last comes first."""
    if os.environ.get("HIPPOS_ROOT"):
        fixed = Path(os.environ["HIPPOS_ROOT"]).expanduser()
        return [fixed] if fixed.is_dir() else []
    bases = list((Path.home() / "Library" / "CloudStorage").glob("GoogleDrive-*/*"))
    if os.name == "nt":
        bases += [Path(f"{letter}:/") / d for letter in string.ascii_uppercase[3:] for d in DRIVES]
        bases += [Path.home() / d for d in DRIVES]
    found = [b / ROOT_NAME for b in bases if (b / ROOT_NAME).is_dir()]
    last = lambda p: (p / "MAP.md").stat().st_mtime if (p / "MAP.md").exists() else 0
    return sorted(found, key=last, reverse=True)


def as_list(value):
    if not value:
        return []
    return [v.strip() for v in value.strip("[]").split(",") if v.strip()]


def iso_date(value):
    try:
        return dt.date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def word_count(body):
    return len(re.sub(r"<!--.*?-->", "", body, flags=re.S).split())


def heading(title):
    """A '## <title>' heading, where 'Waiting on' (<name>) never takes 'Waiting on others'."""
    return rf"^## {re.escape(title)}(?! others\b)"


def section(body, title, prefix=False):
    """First-level items ('- ') of a '## <title>' section (or of one starting with it, with `prefix`)."""
    rest = r"[^\n]*" if prefix else r"\s*"
    m = re.search(rf"{heading(title)}{rest}\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return [l for l in m.group(1).split("\n") if l.startswith("- ")] if m else []


# ---------- board ----------

def board_item(title, line):
    """A board item: '- text | since YYYY-MM-DD | due [~]YYYY-MM-DD | for <who> | last YYYY-MM-DD | prep <days> |
    every [n] day|week|month|year | pin'."""
    parts = line[2:].strip().split(" | ")
    fields, errors = {}, []
    while len(parts) > 1:
        tail = parts[-1].strip()
        if tail == "pin":
            parts.pop()
            fields["pin"] = True
            continue
        prep, every = FIELD_PREP.match(tail), FIELD_EVERY.match(tail)
        if prep or every:
            parts.pop()
            if prep and PREP.match(prep.group(1)):
                fields["prep"] = int(prep.group(1))
            elif every and EVERY.match(every.group(1).strip()):
                fields["every"] = every.group(1).strip()
            else:
                errors.append(f"'{tail}': use 'prep <days>' or 'every [n] day|week|month|year'")
            continue
        who = FIELD_FOR.match(tail)
        if who:
            parts.pop()
            if "for" in fields:
                errors.append("repeated for field")
            fields["for"] = who.group(1).strip()
            continue
        m = FIELD.match(tail)
        if not m:
            break
        key, approx, value = m.groups()
        parts.pop()
        if key in fields:
            errors.append(f"repeated {key} field")
        elif len(value) != 10 or not iso_date(value):
            errors.append(f"{key} with an invalid date ({value})")
        elif approx and key != "due":
            errors.append(f"{key} does not take ~")
        else:
            fields[key] = (iso_date(value), bool(approx))
    text = " | ".join(parts).strip()
    due, approx = fields.get("due", (None, False))
    return {"section": title, "text": text, "since": fields.get("since", (None,))[0], "due": due, "approx": approx,
            "for": fields.get("for"), "last": fields.get("last", (None,))[0], "prep": fields.get("prep"),
            "every": fields.get("every"), "pin": fields.get("pin", False),
            "empty": text.lower().rstrip(".") in EMPTY, "errors": errors}


def next_due(due, every, after):
    """The first occurrence of a recurring item after the day `after`, counted from `due`. A month too short for that
    day takes its last one, and the item stays there from then on: earlier than the 31st, never later."""
    m = EVERY.match(every)
    n, unit = int(m.group(1) or 1), m.group(2)
    try:
        if unit in ("day", "week"):
            span = n * (7 if unit == "week" else 1)
            return due + dt.timedelta(days=span * max(1, (after - due).days // span + 1))
        span = n * (12 if unit == "year" else 1)
        step = max(1, ((after.year - due.year) * 12 + after.month - due.month) // span)
        while True:
            months = due.month - 1 + step * span
            year, month = due.year + months // 12, months % 12 + 1
            d = dt.date(year, month, min(due.day, calendar.monthrange(year, month)[1]))
            if d > after:
                return d
            step += 1
    except (ValueError, OverflowError):  # past the calendar's last year
        return due


def board_items(body):
    return [board_item(t, l) for t in ITEM_SECTIONS for l in section(body, t, prefix=True)]


def words(text):
    return {w for w in re.findall(r"\w+", fold(clean(text))) if len(w) > 2}


def matches(item, line):
    """A capture line names a board item, compared by their gists (what comes before the first detail), since the
    capture often adds a comment ("Done: <the item> (dropped, not now)"): the same gist; or most of the line's gist
    in the item; or most of the item's gist in the line, when it is most of what the line says. A gist under 3
    words only matches the same gist (fewer would match unrelated items). In doubt, no match: an item left open
    until sleep files the capture is better than one hidden by mistake."""
    gi, gl = words(short(item, 10 ** 6)), words(short(line, 10 ** 6))
    shorter = len(gl) >= 3 and len(gl & words(item)) >= 0.8 * len(gl)
    longer = len(gi) >= 3 and len(gi & words(line)) >= 0.8 * len(gi) and len(gi & gl) > 0.5 * len(gl)
    return bool(gi) and (gi == gl or shorter or longer)


def owner(text):
    """Whose the item is: the label before ':' at the start ('Diego: send the proposal'), or None."""
    m = re.match(r"^([^:\[\]]{1,40}):\s", NOTATION.sub("", text).replace("**", "").strip())
    return m.group(1).strip() if m else None


def is_owner(who):
    """The label names the owner: the start of their name, or their name the start of it ('Diego', 'Diego Souza'
    and 'Diego Souza Lima' for one another)."""
    a, b = fold(who).split(), fold(NAME).split()
    return bool(a) and a[:len(b)] == b[:len(a)]


PARTICLES = {"da", "de", "do", "das", "dos", "di", "del", "van", "von", "e"}


def someone_else(who):
    """The label is another person: not the owner, and shaped like a name ('Diego', 'Diego (Acme)', 'João da
    Silva'), not like a phrase ('Follow up with Diego', 'Board deck'). In doubt, the item stays the owner's:
    hiding one of their to-dos is worse than showing someone else's."""
    parts = re.sub(r"\([^)]*\)", "", who or "").split()
    return (bool(who) and not is_owner(who) and 1 <= len(parts) <= 4 and parts[0][:1].isupper()
            and all(p[:1].isupper() or p.lower() in PARTICLES for p in parts))


def capture_section(item):
    """The board section of a pending to-do: someone else's waits on others; one owed to someone waits on <name>."""
    if someone_else(owner(item["text"])):
        return OTHERS
    return "Waiting on" if item["for"] else "Loose ends"


def unfiled(area):
    """What the pending captures say about the board, which sleep hasn't filed yet but is already memory:
    events in date order, ("todo", item) for each to-do (the item `noted` on the capture's day) and ("done",
    text) for each one closed; and their threads, newest first."""
    if not hasattr(area, "_unfiled"):
        events, threads = [], []
        named = lambda f: iso_date(f"{f.name[:4]}-{f.name[4:6]}-{f.name[6:8]}")  # YYYYMMDD-...
        captures = sorted(((read(f), f) for f in area.inbox), key=lambda c: (c[0][0].get("date", ""), c[1].name))
        for (meta, body), f in captures:
            if meta.get("mode") == "forget":
                continue
            day = iso_date(meta.get("date")) or named(f) or local_today()
            for l in section(body, "To-dos"):
                d = DONE.match(l)
                if d:
                    done = board_item("", f"- {d.group(1)}")  # a closing line may repeat the item's fields
                    events.append(("done", (done["text"], day, None if DROPPED.match(l) else done["every"], bool(DROPPED.match(l)))))
                    continue
                it = board_item("", l)
                if not it["empty"] and words(it["text"]):
                    it.update(section=capture_section(it), since=it["since"] or day, noted=day)
                    events.append(("todo", it))
            for l in section(body, "Questions"):
                it = board_item("", l)
                if not it["empty"] and words(it["text"]):
                    it.update(section="Questions for", since=it["since"] or day, noted=day)
                    events.append(("todo", it))
            threads = [l[2:] for l in section(body, "Thread")] + threads
        area._unfiled = events, threads
    return area._unfiled


def open_items(area):
    """The board's open items with the pending captures applied in date order: a to-do they close leaves, or, when it
    recurs and was done, not dropped, moves on to its next occurrence (unless sleep already moved it: `last` is that
    day or later); a to-do naming a board item updates its fields; any other comes in, `noted`."""
    _, board = area.file("BOARD.md") or ({}, "")
    items = [it for it in board_items(board) if not it["empty"]]
    for kind, x in unfiled(area)[0]:
        if kind == "done":
            text, day, every, dropped = x  # the text after "Done:", the capture's day, the recurrence it may state
            kept = []
            for it in items:
                every_ = it["every"] or every
                if not matches(it["text"], text):
                    kept.append(it)
                elif every_ and it["due"] and not dropped:
                    if not (it["last"] and it["last"] >= day):
                        it.update(due=next_due(it["due"], every_, day), every=every_, approx=False, last=day, noted=day)
                    kept.append(it)
            items = kept
            continue
        same = next((it for it in items if (it["section"] == OTHERS) == (x["section"] == OTHERS)
                     and matches(it["text"], x["text"])), None)
        if same:
            if x["due"]:
                same.update(due=x["due"], approx=x["approx"])
            same.update({"for": x["for"] or same["for"], "noted": x["noted"], "last": x["last"] or same["last"],
                         "prep": x["prep"] or same["prep"], "every": x["every"] or same["every"], "pin": x["pin"] or same["pin"]})
        else:
            items.append(dict(x))
    return items


def threads(area):
    """Threads in progress, newest first, one per topic (the label before ':'), up to THREADS: the pending
    captures' first, then the board's."""
    _, board = area.file("BOARD.md") or ({}, "")
    out, seen = [], set()
    for line in unfiled(area)[1] + [l[2:] for l in section(board, "Thread")]:
        t = clean(line)
        if not t or t.lower().rstrip(".") in EMPTY or t.lower().startswith("none"):
            continue
        key = fold(owner(t) or t)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out[:THREADS]


def dates_in_text(text):
    """Dates that look like due dates in free text, outside markers and links (the format asks for '| due')."""
    bare = NOTATION.sub("", text)
    found = []
    for m in TEXT_DATE.finditer(bare):
        before = bare[max(0, m.start() - 30):m.start()].lower()
        if DUE_WORDS.search(before):
            found.append(m.group(1))
    return found


def same_day(found, due):
    """A date found in an item's text is its due date: the same day, as dd/mm or mm/dd too. A day named in words
    ("Friday") can't contradict the field."""
    if "-" in found:
        return found == due.isoformat()
    if "/" in found:
        a, b = (int(n) for n in found.split("/")[:2])
        return (a, b) in ((due.day, due.month), (due.month, due.day))
    return True


def text_day(found, near):
    """The day a date in a text stands for: ISO, or dd/mm (mm/dd in English) in the year that brings it closest to `near`."""
    if "-" in found:
        return iso_date(found)
    parts = [int(n) for n in found.split("/")]
    day, month = (parts[1], parts[0]) if SPEAKS.lower() in ("en", "en-us") else (parts[0], parts[1])
    years = [parts[2] + (2000 if parts[2] < 100 else 0)] if len(parts) > 2 else [near.year - 1, near.year, near.year + 1]
    days = []
    for year in years:
        try:
            days.append(dt.date(year, month, day))
        except ValueError:
            pass
    return min(days, key=lambda d: abs((d - near).days), default=None)


def later_dates(text, since):
    """Full dates in an item's text after the day it entered the board, whatever the word before them ("em 05/11",
    "para 2026-12-01"): a deadline nothing reads. Earlier ones are history ("paid on 2026-10-28"); "3/4" is no date."""
    near = since or local_today()
    found = []
    for m in TEXT_DATE.finditer(NOTATION.sub("", text)):
        if FULL_DATE.fullmatch(m.group(1)):
            day = text_day(m.group(1), near)
            if day and day > near:
                found.append(m.group(1))
    return found


def outside_schema(root, area):
    """Markdown files nothing reads: loose in the area or in core, in a folder the protocol doesn't know, or a
    conflict copy of a record. drafts/ is the place for what isn't memory."""
    core = area.name == "core"
    files, folders = (CORE_FILES, ("people",)) if core else (AREA_FILES, FOLDERS + ("log",))
    found = []
    for f in sorted(area.folder.rglob("*.md")) if area.folder.is_dir() else []:
        parts = f.relative_to(area.folder).parts
        if parts[0] == "drafts" or any(p.startswith(".") for p in parts):
            continue
        loose = f.name not in files if len(parts) == 1 else parts[0] not in folders or len(parts) > 2
        if loose or CONFLICT_COPY.search(f.stem):
            found.append(f)
    if core:
        found += [f for f in sorted(root.glob("*.md")) if f.name not in ROOT_FILES]
        found += sorted((root / "areas").glob("*.md"))
    return found


def without_log(board):
    return re.sub(r"^## Log\b.*?(?=^## |\Z)", "", board, flags=re.M | re.S)


class Area:
    def __init__(self, root, name):
        self.root, self.name = root, name
        self.folder = root / "core" if name == "core" else root / "areas" / name
        self.records = {}  # slug -> (path, meta, body)
        self.duplicates = []
        folders = ("people",) if name == "core" else FOLDERS
        for sub in folders:
            for f in sorted((self.folder / sub).glob("*.md")):
                meta, body = read(f)
                if f.stem in self.records:
                    self.duplicates.append(f.stem)
                self.records[f.stem] = (f, meta, body)
        self.inbox = sorted((root / "inbox" / name).glob("*.md"))

    def file(self, name):
        f = self.folder / name
        return read(f) if f.exists() else None


def areas(root):
    folder = root / "areas"
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.exists() else []


def resolve_area(root, name):
    """The area folder by name, by an alias or by an obvious typo; None if not found."""
    key = fold
    names = {"core": "core"}
    for a in areas(root):
        f = root / "areas" / a / "AREA.md"
        for n in [a] + (as_list(read(f)[0].get("aliases")) if f.exists() else []):
            names[key(n)] = a
    if key(name) in names:
        return names[key(name)]
    close = {names[n] for n in difflib.get_close_matches(key(name), names, n=3, cutoff=0.75)}
    return close.pop() if len(close) == 1 else None


def area_from_argument(root, name):
    """For the commands: the resolved area, or stop with the list of areas to ask about."""
    found = resolve_area(root, name)
    if found is None:
        print(f"unknown area: {name}. Areas: {', '.join(areas(root))}. Ask {NAME} which one.")
        sys.exit(2)
    return found


def limits(root):
    """The protections of every area, {"run"|"open"|"read_only": [(area, item)]}: the items in backticks of the
    `- Never run:`, `- Never open:` and `- Read only:` lines of each AREA.md's `## Limits`."""
    found = {kind: [] for kind in LIMIT_LISTS.values()}
    for a in areas(root):
        f = root / "areas" / a / "AREA.md"
        for line in section(read(f)[1], "Limits", prefix=True) if f.exists() else []:
            label, _, rest = line[2:].partition(":")
            if label.strip() in LIMIT_LISTS:
                found[LIMIT_LISTS[label.strip()]] += [(a, i.strip()) for i in BACKTICKED.findall(rest) if i.strip()]
    return found


def exists(root, area, ref):
    """A link target: a record of the area, of another one (`area:slug`) or of core (`core:slug`), or a draft."""
    if ":" in ref:
        other, slug = ref.split(":", 1)
        folder = root / "core" if other == "core" else root / "areas" / other
        return folder.exists() and (slug in Area(root, other).records or (folder / "drafts" / f"{slug}.md").exists())
    return ref in area.records or (area.folder / "drafts" / f"{ref}.md").exists()


# ---------- validate ----------

class ForSleep(str):
    """A warning sleep itself resolves; `pending` calls sleep for it."""

    def __new__(cls, reason, text):
        warning = super().__new__(cls, text)
        warning.reason = reason
        return warning


def validate(root, area):
    errors, warnings = [], []
    today = local_today()

    if area.name != "core":
        for required in ("AREA.md", "BOARD.md"):
            if not (area.folder / required).exists():
                errors.append(f"missing {required}")
    for slug in area.duplicates:
        errors.append(f"{slug}: slug repeated in two folders")
    if area.name != "core" and (area.folder / "AREA.md").exists():
        mine = as_list(read(area.folder / "AREA.md")[0].get("aliases"))
        for other in areas(root):
            if other == area.name:
                continue
            f_other = root / "areas" / other / "AREA.md"
            theirs = [fold(t) for t in as_list(read(f_other)[0].get("aliases"))] if f_other.exists() else []
            for a in mine:
                if fold(a) == fold(other) or fold(a) in theirs:
                    errors.append(f"AREA.md: alias '{a}' conflicts with area {other}")

    if area.name != "core" and (area.folder / "AREA.md").exists():
        for line in section(read(area.folder / "AREA.md")[1], "Limits", prefix=True):
            label, _, rest = line[2:].partition(":")
            if label.strip() in LIMIT_LISTS and rest.strip() not in ("", "...", "none") and not BACKTICKED.search(rest):
                warnings.append(f"AREA.md: '{label.strip()}' without items in backticks; the guard reads only `item`, `item`")
    for slug, (f, meta, body) in area.records.items():
        kind, status = meta.get("type", ""), meta.get("status", "")
        folder = f.parent.name
        expected = {"initiatives": "initiative", "decisions": "decision", "topics": "topic", "people": "person"}[folder]
        if kind != expected:
            errors.append(f"{slug}: type '{kind}' outside folder {folder}")
            continue
        if not meta.get("title"):
            errors.append(f"{slug}: no title")
        if kind == "initiative":
            if status not in STATUS["initiative"]:
                errors.append(f"{slug}: invalid status ({status})")
            if meta.get("priority") not in PRIORITIES:
                errors.append(f"{slug}: invalid priority")
            verified = iso_date(meta.get("verified"))
            if not verified:
                errors.append(f"{slug}: no verified")
            elif status == "active":
                if not meta.get("next"):
                    errors.append(f"{slug}: active without next")
                days = (today - verified).days
                if days > DAYS_STALE:
                    warnings.append(f"{slug}: active, verified {days} days ago")
        elif kind == "decision":
            if status not in STATUS["decision"]:
                errors.append(f"{slug}: invalid status ({status})")
            if meta.get("confirmed") not in ("yes", "inherited"):
                errors.append(f"{slug}: confirmed must be yes or inherited")
            if status == "approved" and not meta.get("decided_by"):
                errors.append(f"{slug}: approved without decided_by")
            if status == "superseded" and not meta.get("superseded_by"):
                errors.append(f"{slug}: superseded without superseded_by")
            if not re.match(r"^\d{4}-\d{2}(-\d{2})?-", slug):
                errors.append(f"{slug}: name without a date at the start")
            review = iso_date(meta.get("review_on"))
            if review and review <= today and "## Outcome" not in body:
                warnings.append(f"{slug}: review overdue since {review}")
        elif kind in ("topic", "person"):
            if not iso_date(meta.get("updated")):
                errors.append(f"{slug}: no updated")
            n = word_count(body)
            if kind == "topic" and n > TOPIC_MAX:
                warnings.append(ForSleep("topic too large to split", f"{slug}: topic with {n} words (limit {TOPIC_MAX}); split into smaller topics joined by links"))
        for line in section(body, "Open"):
            if not PARKED.search(line) and clean(line[2:]).lower() not in EMPTY:
                warnings.append(ForSleep("open line without since", f"{slug}: '## Open' line without '| since', so the weekly review misses it: '{clean(line[2:])[:50]}'"))
        for field in LISTS:
            for ref in as_list(meta.get(field)):
                if not exists(root, area, ref):
                    errors.append(f"{slug}: {field} points to a missing slug ({ref})")
        for field in SIMPLE_REFS:
            ref = meta.get(field, "")
            if ref and not exists(root, area, ref):
                errors.append(f"{slug}: {field} points to a missing slug ({ref})")

    targets = [(slug, f) for slug, (f, _, _) in area.records.items()]
    for name in ("BOARD.md", "LOG.md", "AREA.md", "PREFERENCES.md", "PRINCIPLES.md", "PROFILE.md"):
        if (area.folder / name).exists():
            targets.append((name, area.folder / name))
    for label, f in targets:
        text = text_of(f)
        if "\ufffd" in text:
            errors.append(f"{label}: not valid UTF-8; save it as UTF-8")
        for ref in sorted(set(LINK.findall(text))):
            if not exists(root, area, ref):
                errors.append(f"{label}: broken link [[{ref}]]")
        if SECRETS.search(text):
            errors.append(f"{label}: looks like it holds a secret; remove it from memory")

    prefs = area.folder / "PREFERENCES.md"
    if area.name == "core" and prefs.exists():
        n = word_count(read(prefs)[1])
        if n > PREFERENCES_MAX:
            warnings.append(f"PREFERENCES.md with {n} words (limit {PREFERENCES_MAX}): drop what the protocol or the skill already say and merge similar ones; check with {NAME} before dropping anything")
    profile = area.folder / "PROFILE.md"
    if area.name == "core" and profile.exists():
        meta = read(profile)[0]
        if not meta.get("name"):
            errors.append("PROFILE.md without `name` in the frontmatter: what to call the person the memory belongs to")
        tz = meta.get("timezone", "")
        if not re.fullmatch(r"UTC|[A-Za-z_]+(/[A-Za-z0-9_+-]+)+", tz) or not known_timezone(tz):
            errors.append("PROFILE.md without `timezone` in the frontmatter: the person's IANA timezone (e.g. America/New_York)")
        if not LANGUAGE.fullmatch(meta.get("language", "")):
            errors.append("PROFILE.md without `language` in the frontmatter: the language of content and replies (e.g. en, pt-BR)")

    board = area.folder / "BOARD.md"
    if board.exists():
        _, body = read(board)
        n = len([l for l in body.split("\n") if l.strip()])
        size = len(body.encode("utf-8"))
        if n > BOARD_MAX_LINES or size > BOARD_MAX_BYTES:
            warnings.append(ForSleep("board too large to consolidate", f"BOARD.md with {n} lines and {size} bytes: consolidate"))
        if re.search(r"^## Log\b", body, re.M):
            errors.append("BOARD.md: ## Log section; move it to LOG.md")
        for title in BOARD_SECTIONS:
            if not re.search(heading(title), body, re.M):
                full = title + ("" if title in ("Loose ends", "Thread", OTHERS) else " <name>")
                why = ("move there, as 'Who: what', the loose ends someone else owes" if title == OTHERS
                       else "headings stay in English, as in templates/")
                errors.append(f"BOARD.md without '## {full}': {why}")
        for title in re.findall(r"^## +(.+?)\s*$", body, re.M):
            if title != "Log" and not any(title == k or title.startswith(f"{k} ") for k in BOARD_OPTIONAL + BOARD_SECTIONS):
                errors.append(f"BOARD.md: section '## {title}' outside the template; nothing reads its items; move them to the right section")
        notes = [l for l in section(body, "Attention") if clean(l[2:]).lower().rstrip(".") not in EMPTY]
        if len(notes) > ATTENTION_MAX:
            warnings.append(f"BOARD.md: more than {ATTENTION_MAX} lines in ## Attention; keep the most important")
        for l in notes:
            if not ATTENTION_MARKER.search(l):
                errors.append(f"BOARD.md (Attention) '{clean(l[2:])[:50]}': no '[recommendation YYYY-MM-DD]'; it is a reading, never a fact")
        if len([l for l in section(body, "Thread") if clean(l[2:]).lower() not in EMPTY]) > THREADS:
            warnings.append(f"BOARD.md: more than {THREADS} threads; keep the newest, one per topic")
        overdue = 0
        for it in board_items(body):
            if it["empty"]:
                continue
            label = f"BOARD.md ({it['section']}) '{it['text'][:50]}'"
            errors += [f"{label}: {e}" for e in it["errors"]]
            if not it["since"]:
                errors.append(f"{label}: no '| since YYYY-MM-DD'")
            if it["section"] == OTHERS and not owner(it["text"]):
                errors.append(f"{label}: no 'Who: what' (whom {NAME} is waiting on)")
            if it["every"] and not it["due"]:
                errors.append(f"{label}: 'every' without '| due': the next occurrence counts from it")
            loose = [d for d in dates_in_text(it["text"]) if not it["due"] or not same_day(d, it["due"])]
            if not it["due"]:
                loose += [d for d in later_dates(it["text"], it["since"]) if d not in loose]
            if loose:
                errors.append(f"{label}: due date in the text ({', '.join(loose)}); use '| due YYYY-MM-DD', one per item, or reword it if it is not one")
            if it["due"] and it["due"] < today and it["section"] != OTHERS:
                overdue += 1
            if (it["section"] in AGING_SECTIONS and it["since"] and LINK.search(it["text"]) and not it["due"]
                    and not it["for"] and not it["pin"] and (today - it["since"]).days > DAYS_AGED):
                warnings.append(ForSleep("aged item to move to its record", f"{label}: aged, since {it['since']}; move it, fields and all, to the linked record's ## Open"))
        if overdue:
            warnings.append(f"BOARD.md: {overdue} item(s) overdue; the opening asks {NAME}")

    outside = outside_schema(root, area)
    nfc = lambda text: unicodedata.normalize("NFC", text)  # file names may come decomposed
    asked = nfc("\n".join(text_of(b) for b in (root / "areas").glob("*/BOARD.md"))) if outside else ""
    for f in outside:
        text = f"{f.relative_to(root)}: outside the schema, nothing reads it; sleep consolidates it like a capture (what is not memory goes to drafts/)"
        warnings.append(text if nfc(f.name) in asked else ForSleep("file outside the schema", text))  # already a question: only <name> can move it on
    inbox = root / "inbox" / area.name
    for f in sorted(inbox.iterdir()) if inbox.is_dir() else []:
        if f.is_file() and f.suffix != ".md" and not f.name.startswith("."):
            errors.append(f"inbox/{area.name}/{f.name}: not a .md capture (a Google Doc?); recreate it as plain Markdown")
    if area.name == "core" and (root / "inbox").is_dir():
        for d in sorted(p for p in (root / "inbox").iterdir() if p.is_dir()):
            if d.name not in areas(root) + ["core"]:
                errors.append(f"inbox/{d.name}/: no area by that name; move its captures to the right inbox and delete it")
    for f in area.inbox:
        meta, body = read(f)
        if "\ufffd" in body:
            errors.append(f"inbox/{f.name}: not valid UTF-8; save it as UTF-8")
        if not CAPTURE_NAME.match(f.name):
            warnings.append(f"inbox/{f.name}: name outside the YYYYMMDD-HHMM-origin-topic.md pattern")
        if meta.get("type") != "capture":
            errors.append(f"inbox/{f.name}: type must be capture")
        if meta.get("area") != area.name:
            errors.append(f"inbox/{f.name}: area '{meta.get('area')}' in the folder of {area.name}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", meta.get("date", "")):
            errors.append(f"inbox/{f.name}: invalid date")
        if meta.get("origin") not in ORIGINS:
            errors.append(f"inbox/{f.name}: invalid origin")
        if meta.get("mode", "normal") not in MODES:
            errors.append(f"inbox/{f.name}: invalid mode")
        if not body.strip():
            errors.append(f"inbox/{f.name}: empty capture")
        if SECRETS.search(body):
            errors.append(f"inbox/{f.name}: looks like it holds a secret")
        # capture outside the template (common with outside agents): sleep normalizes it when consolidating
        sections = re.findall(r"^#+ *(.*?)\s*$", body, re.M)
        outside = [t for t in sections if t not in CAPTURE_SECTIONS]
        if outside:
            warnings.append(f"inbox/{f.name}: section outside the template ({'; '.join(outside)})")
        current, unmarked = None, 0
        for l in body.split("\n"):
            if l.startswith("#"):
                current = l.lstrip("# ").strip()
            elif l.startswith("- ") and current != "Thread" and not MARKER.search(l) and not LEFT_ON_PURPOSE.match(l):
                unmarked += 1
        if unmarked:
            warnings.append(f"inbox/{f.name}: {unmarked} line(s) without a marker; they count as [hypothesis]")
        for ref in sorted(set(LINK.findall(body))):
            if not exists(root, area, ref):
                warnings.append(f"inbox/{f.name}: [[{ref}]] does not exist; a new topic goes described, without a link")
    lock = root / "SLEEP-IN-PROGRESS.md"
    if area.name == "core" and lock.exists():
        started = read(lock)[0].get("started", "")
        try:
            age = (dt.datetime.now(TZ) - dt.datetime.fromisoformat(started[:16]).replace(tzinfo=TZ)).total_seconds() / 60
            if age > 60:
                warnings.append(f"SLEEP-IN-PROGRESS.md from {started}: a previous sleep got stuck; check and delete the lock")
        except ValueError:
            warnings.append("SLEEP-IN-PROGRESS.md without a valid started")
    if len(area.inbox) > INBOX_MAX:
        warnings.append(f"inbox with {len(area.inbox)} captures: run sleep")
    return errors, warnings


# ---------- state ----------

def now():
    return dt.datetime.now(TZ).isoformat(timespec="minutes")


def local_today():
    return dt.datetime.now(TZ).date()


def initiative_line(slug, meta, today):
    v = iso_date(meta.get("verified"))
    days = f" ({(today - v).days}d)" if v else ""
    return (f"- [[{slug}]] | {meta.get('priority', '?')} | {meta.get('owner', '?')} | "
            f"verified {meta.get('verified', '?')}{days} | {meta.get('next', '')}")


def clean(text):
    """Item text without markers, links, bold or the owner's '<name>:'."""
    t = re.sub(r"\(\s*\)", "", NOTATION.sub("", text).replace("**", ""))
    t = re.sub(r"\s+([.,;:)])", r"\1", re.sub(r"\s+", " ", t)).strip(" .;,")
    label = re.match(r"^([^:]{1,40}):\s*", t)
    return t[label.end():] if label and is_owner(label.group(1)) else t


def short(text, limit=TEXT_MAX):
    """The gist of the item, before the first detail; a short label ("Goal: ...") stays; a question goes up to its
    question mark, so what is being asked stays; "Dr. Souza" is not the end of a sentence."""
    t = clean(text)
    label = re.match(r"^[^:]{1,25}: ", t)
    start = label.end() if label else 0
    asks = re.search(r"\?(?=\s|$)", t)  # not the one in a link
    room = 2 * limit if limit >= TEXT_MAX else limit  # what is asked often comes last, so a question may run longer
    if asks and asks.start() < room:
        t, limit = t[:asks.start() + 1], room
    else:
        cut = next((m for m in re.finditer(r" \(|[.:;] ", t) if m.start() >= max(start, 15)
                    and not (m.group(0) == ". " and ABBREVIATION.search(t[:m.start()]))), None)
        if cut:
            t = t[:cut.start()]
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0].rstrip(" .;,:(") + "..."
    return t[:1].upper() + t[1:]


def gist(text):
    """The gist for the screen, with the label ("Diego: ...") in bold."""
    t = short(text)
    label = re.match(r"^([^:*]{1,25}): ", t)
    return f"**{label.group(1)}:** {t[label.end():]}" if label else t


def tag(text):
    return short(text, TAG_MAX)


def short_date(d, today, approx=False):
    md = f"{MONTHS[d.month - 1]} {d.day}" + ("" if d.year == today.year else f", {d.year}")
    days = (d - today).days
    if approx:
        return f"~{md}"
    if days in (0, 1):
        return ("today", "tomorrow")[days]
    return f"{WEEKDAYS[d.weekday()]} {md}" if 1 < days < 7 else md


def area_title(name):
    return name.replace("-", " ").title()


def due_items(root, names):
    """(due, approx, area, item) for every open item with a due date, pending captures included, by date."""
    out = []
    for name in names:
        out += [(it["due"], it["approx"], name, it) for it in open_items(Area(root, name)) if it["due"]]
    return sorted(out, key=lambda x: (x[0], x[2]))


def block(title, lines, tags=(), limit=BLOCK_ITEMS, start=None):
    """Up to `limit` lines, numbered from `start` when given; the rest named by their tags in one line, so
    nothing hides behind a number."""
    rest = list(tags)[limit:len(lines)]
    # a numbered list that doesn't start at 1 is a list only after a blank line (Markdown)
    out = [title] + ([""] if start else []) + [f"{start + i}. {l}" if start else f"- {l}" for i, l in enumerate(lines[:limit])]
    if len(lines) > limit:
        named = f": {'; '.join(rest[:3])}" + ("; ..." if len(rest) > 3 else "") if rest else ""
        out.append(f"- and {len(lines) - limit} more{named}")
    return "\n".join(out)


def ref(it, area=None):
    """What a number stands for, for the agent: the item as on the board, and whether a capture brought it."""
    fields = [f"since {it['since']}"] if it.get("since") else []
    fields += [f"due {'~' if it['approx'] else ''}{it['due']}"] if it.get("due") else []
    fields += [f"for {it['for']}"] if it.get("for") else []
    fields += [f"last {it['last']}"] if it.get("last") else []
    fields += [f"prep {it['prep']}"] if it.get("prep") else []
    fields += [f"every {it['every']}"] if it.get("every") else []
    fields += ["pin"] if it.get("pin") else []
    where = f"[{area}] " if area else ""
    pending = " (pending capture, not yet consolidated)" if it.get("noted") else ""
    return f"{where}({it['section']}) {it['text']}" + "".join(f" | {f}" for f in fields) + pending


def for_agent(*lines):
    """The part only the agent reads: how to show what came above, then `lines`."""
    show = ([f"Show what is above in {SPEAKS}: translate every label, weekday, month, \"today\", \"tomorrow\" "
             "and the last line; keep the items, numbers, order and blank lines."] if not SPEAKS.startswith("en") else [])
    return "\n".join([AGENT_SEPARATOR] + show + [l for l in lines if l])


class Numbered:
    """Blocks numbered across one reply, so <name> can answer "1 done, 3 on Friday"; `refs` says, for the
    agent, what each number stands for. An entry is (line, ref, tag)."""

    def __init__(self):
        self.refs = []

    def block(self, title, entries, limit=BLOCK_ITEMS):
        start = len(self.refs) + 1
        self.refs += [r for _, r, _ in entries[:limit]]
        return block(title, [l for l, _, _ in entries], [t for _, _, t in entries], limit, start)

    def agent(self):
        return ([f"Numbers (to capture {NAME}'s answer):"] + [f"{n}. {r}" for n, r in enumerate(self.refs, 1)]
                if self.refs else [])


def entry(it, line, area=None):
    return line, ref(it, area), tag(it["text"])


def when(it, today):
    """The item's due date or, without one, since when it has waited."""
    if it["due"]:
        return short_date(it["due"], today, it["approx"])
    if it.get("last"):
        return f"last news {short_date(it['last'], today)}"
    return f"since {short_date(it['since'], today)}" if it["since"] else "no date"


def noted(it, today):
    return f" (noted {short_date(it['noted'], today)})" if it.get("noted") else ""


def follow_ups(items, today):
    """Waiting on others, overdue or with no news for over DAYS_FOLLOW_UP days: time to nudge. A nudge or any news
    (`last`) buys those days, overdue or not, so it doesn't ask for another one the next morning."""
    news = lambda it: max([d for d in (it["since"], it.get("noted"), it.get("last")) if d], default=None)
    recent = lambda it: bool(it.get("last")) and (today - it["last"]).days <= DAYS_FOLLOW_UP
    late = [it for it in items if it["section"] == OTHERS and (
        it["due"] < today and not recent(it) if it["due"] else bool(news(it)) and (today - news(it)).days > DAYS_FOLLOW_UP)]
    return sorted(late, key=lambda it: it["due"] or news(it) or dt.date.min)


def waited(it, today):
    """' · since <date>' when someone has waited on <name> for over DAYS_WAITING days."""
    old = it["since"] and (today - it["since"]).days > DAYS_WAITING
    return f" · since {short_date(it['since'], today)}" if old else ""


def attention(area, today=None):
    """What sleep wrote for the top of the opening, without notation, and the day it wrote it. With `today`, its dates
    as on the rest of the screen; without it, as written, for files read on other days ("tomorrow" wouldn't last)."""
    _, board = area.file("BOARD.md") or ({}, "")
    lines = [l for l in section(board, "Attention") if clean(l[2:]).lower().rstrip(".") not in EMPTY]
    days = [iso_date(m.group(1)) for m in map(ATTENTION_MARKER.search, lines) if m]
    readable = lambda m: short_date(iso_date(m.group(0)), today) if today and iso_date(m.group(0)) else m.group(0)
    return ([re.sub(r"\b\d{4}-\d{2}-\d{2}\b", readable, clean(l[2:])) for l in lines],
            max((d for d in days if d), default=None))


def log_bodies(area):
    """The text of LOG.md and of the months archived in log/."""
    log = area.file("LOG.md")
    return ([log[1]] if log else []) + [read(f)[1] for f in sorted((area.folder / "log").glob("*.md"))]


def hidden(area, today):
    """(day, slug, where, text) of the commitments dated only in a record (`next`, ## Risks, ## Consequences, ## Open):
    a date ahead, or a gone one with a due word before it (the rest is history), that no open item carries. An item
    carries it with the same due date and the record linked or two words in common: a date alone is a coincidence."""
    items = open_items(area)
    found = []
    for slug, (_, meta, body) in sorted(area.records.items()):
        if meta.get("status") in ("done", "cancelled", "superseded", "discarded"):
            continue
        lines = ([("next", meta["next"])] if meta.get("next") else []) + [(s, l[2:]) for s in RECORD_DATED for l in section(body, s)]
        for where, text in lines:
            bare = re.sub(r"\|\s*since\s+\S+", "", NOTATION.sub("", text))  # the line's own age is no commitment
            for m in TEXT_DATE.finditer(bare):
                day = text_day(m.group(1), today) if FULL_DATE.fullmatch(m.group(1)) else None
                if not day or (day < today and not DUE_WORDS.search(bare[max(0, m.start() - 30):m.start()].lower())):
                    continue
                carried = any(it["due"] == day and (slug in LINK.findall(it["text"]) or len(words(it["text"]) & words(text)) >= 2)
                              for it in items)
                if not carried:
                    found.append((day, slug, where, clean(text)))
    return sorted(found)


def waits_on_owner(it):
    """Someone waits on <name>: in "Waiting on", or anywhere of theirs with `for` (sleep may file it in "Loose ends")."""
    return it["section"] == "Waiting on" or bool(it["for"] and it["section"] != OTHERS)


def undated(items):
    """<name>'s to-dos and questions with no due date, nobody waiting and no pin: nothing else brings them back.
    Oldest first."""
    rows = [it for it in items if it["section"] in ("Loose ends", "Questions for") and not it["due"] and not it["for"] and not it["pin"]]
    return sorted(rows, key=lambda it: it["since"] or dt.date.min)


def in_sight(it, today):
    """A due date to show now: within DAYS_NEXT days, or up to the item's own `prep` days ahead."""
    days = (it["due"] - today).days
    return days < DAYS_NEXT or days <= (it.get("prep") or -1)


def in_turn(rows, today, limit=UNDATED_ITEMS):
    """`limit` of the rows, a different few each day, in their order: every one comes back within days, without
    state, and two openings on the same day show the same ones."""
    if len(rows) <= limit:
        return rows
    start = today.toordinal() * limit % len(rows)
    return [rows[i] for i in sorted((start + k) % len(rows) for k in range(limit))]


# What waits without a date or went quiet: (key, icon, title, words in the opening's "Also" line or None)
REVIEW = (("questions", "❓", "Questions for you", ("question for you", "questions for you")),
          ("parked", "🧊", "Parked (left the board after 14 days)", ("parked", "parked")),
          ("decide", "🔍", "Decisions to review (did it work?)", ("decision to review", "decisions to review")),
          ("confirm", "✅", "Decisions to confirm", ("decision to confirm", "decisions to confirm")),
          ("unchecked", "🧭", f"Initiatives not checked in {DAYS_STALE} days", ("initiative not checked", "initiatives not checked")),
          ("quiet", "🔁", "Waiting on others, no news", None),
          ("undated", "📝", "Your to-dos without a date", None))
PARKED = re.compile(r"\| since (\d{4}-\d{2}-\d{2})|\bsince (\d{4}-\d{2}-\d{2})")
LAST_CONTACT = re.compile(r"^- Last contact:\s*(\d{4}-\d{2}-\d{2}),?\s*(.*)")
RECORD_REF = re.compile(r"\(parked in the ## \w+ of (\S+)\)|\((?:decision|initiative) (\S+)\)")
THEIRS = " (waiting on others: follow up, not the owner's)"


def review_items(area, today):
    """{key of REVIEW: [entry]}: the board's questions, quiet follow-ups and undated to-dos; the items parked in
    the records; decisions to review or confirm; active initiatives not checked in DAYS_STALE days."""
    out = {key: [] for key, *_ in REVIEW}
    for it in open_items(area):
        if it["section"] == "Questions for":
            out["questions"].append(entry(it, f"{gist(it['text'])}{waited(it, today)}{noted(it, today)}"))
        elif it["section"] == OTHERS and not it["due"] and it in follow_ups([it], today):
            out["quiet"].append(entry(it, f"{when(it, today)} · {gist(it['text'])}"))
        elif it["section"] == "Loose ends" and not it["due"]:
            out["undated"].append(entry(it, f"{gist(it['text'])}{noted(it, today)}"))
    for slug, (_, meta, body) in sorted(area.records.items()):
        title, kind, status = meta.get("title") or slug, meta.get("type"), meta.get("status")
        for part in ("Open", "Addenda"):
            for l in section(body, part):
                since = PARKED.search(l)
                if since:  # an impossible date ("since 2026-02-30") still shows the item, without it
                    day = iso_date(since.group(1) or since.group(2))
                    when_ = f" · since {short_date(day, today)}" if day else ""
                    out["parked"].append((f"{short(l[2:].split(' | ')[0])} · {title}{when_}",
                                          f"(parked in the ## {part} of {slug}) {l[2:]}", tag(l[2:])))
        if kind == "decision":
            review, made = iso_date(meta.get("review_on")), iso_date(meta.get("date"))
            decided = f" · decided {short_date(made, today)}" if made else ""
            if review and review <= today and "## Outcome" not in body and status not in ("superseded", "discarded"):
                out["decide"].append((f"{title}{decided} · review since {short_date(review, today)}",
                                      f"(decision {slug}) review_on {review}; the answer becomes its ## Outcome", tag(title)))
            if status == "proposed" or meta.get("confirmed") == "inherited":
                out["confirm"].append((f"{title} · {status}, confirmed: {meta.get('confirmed')}",
                                       f"(decision {slug}) {status}, confirmed {meta.get('confirmed')}", tag(title)))
        verified = iso_date(meta.get("verified"))
        if kind == "initiative" and status == "active" and verified and (today - verified).days > DAYS_STALE:
            out["unchecked"].append((f"{title} · checked {short_date(verified, today)} · next: {short(meta.get('next', ''))}",
                                     f"(initiative {slug}) verified {verified}; recheck at the source", tag(title)))
    return out


def also(review):
    """The opening's "Also" line: how many of each kind wait without a date (the weekly review lists them)."""
    return "; ".join(f"{len(review[k])} {forms[len(review[k]) > 1]}" for k, _, _, forms in REVIEW if forms and review[k])


def topic(text):
    """A thread's topic: its label ('Hiring: salary still open'), or its start."""
    return owner(text) or tag(text)


def series(version):
    """The first two numbers of the version, which change the memory format."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:2]) or (0, 0)


def sleep_reasons(root, area, inbox_min=1):
    """Why the area (or core) needs sleep; an empty list = it doesn't."""
    today = local_today()
    reasons = []
    if len(area.inbox) >= inbox_min:
        reasons.append(f"{len(area.inbox)} capture(s) in the inbox")
    st = area.file("STATE.md")
    generated = iso_date(st[0].get("generated")) if st else None
    if not generated:
        reasons.append("state never generated")
    else:
        if (today - generated).days > DAYS_STATE:
            reasons.append(f"state {(today - generated).days} days old")
        version = st[0].get("system_version", "")
        if series(version) < series(VERSION):
            reasons.append(f"memory at version {version or '?'}, system at {VERSION}")
    errors, warnings = validate(root, area)
    if errors:
        reasons.append(f"{len(errors)} validator error(s); due dates may be missing")
    fix = [w.reason for w in warnings if isinstance(w, ForSleep)]
    reasons += [f"{r}: {fix.count(r)}" for r in dict.fromkeys(fix)]
    return reasons


def pending(root):
    queue = [(n, sleep_reasons(root, Area(root, n))) for n in areas(root) + ["core"]]
    queue = [(n, r) for n, r in queue if r]
    for name, reasons in queue:
        print(f"{name}: {'; '.join(reasons)}")
    if not queue:
        print("nothing pending")
    return 0


def opening(root, area, extra=(), describe=str):
    """The assistant's first reply, ready to show, computed now (local mode), pending captures included.

    `extra`: ready blocks from other sources (lookup.py), placed after the follow-ups.
    `describe`: completes an item's text (lookup.py gives each "#123" its title)."""
    today = local_today()
    items = open_items(area)
    n = Numbered()
    dated = sorted((it for it in items if it["due"]), key=lambda it: it["due"])
    overdue = [it for it in dated if it["due"] < today and it["section"] != OTHERS]
    upcoming = [it for it in dated if it["due"] >= today]
    week = [it for it in upcoming if (it["due"] - today).days < DAYS_NEXT]
    ahead = [it for it in upcoming if it not in week and in_sight(it, today)]  # a block of their own: a busy week would bury them
    week = week or [it for it in upcoming[:1] if (it["due"] - today).days <= DAYS_AHEAD and it not in ahead]
    pinned = [it for it in items if it["pin"] and it not in overdue + week + ahead]
    follow = [it for it in follow_ups(items, today) if it not in pinned]
    waiting = sorted((it for it in items if waits_on_owner(it)),  # first due, then who waits the longest
                     key=lambda it: (it["due"] is None, it["due"] or it["since"] or dt.date.min))
    loose = undated(items)
    running = threads(area)
    day = f"{WEEKDAYS[today.weekday()]}, {MONTHS[today.month - 1]} {today.day}"
    head = f"**{area_title(area.name)}** · {day} · 🧵 {short(running[0]) if running else 'no thread in progress'}"
    if len(running) > 1:
        head += f" · also in progress: {'; '.join(topic(t) for t in running[1:])}"
    blocks = [head]
    notes, made = attention(area, today)
    if notes:
        blocks.append(block("🎯 **Attention**" + (f" (sleep of {short_date(made, today)})" if made else ""), notes, limit=ATTENTION_MAX))
    line = lambda it: f"{when(it, today)} · {describe(gist(it['text']))}{noted(it, today)}"
    if pinned:
        blocks.append(n.block(f"📌 **You asked not to forget** ({len(pinned)})", [entry(it, line(it)) for it in pinned]))
    if overdue:
        blocks.append(n.block("🔴 **Overdue** (done, postpone or drop?)", [entry(it, line(it)) for it in overdue]))
    if week:
        title = "📅 **Next due**" if len(week) == 1 else f"📅 **Next due dates** ({len(week)})"
        blocks.append(n.block(title, [entry(it, line(it)) for it in week]))
    if ahead:
        blocks.append(n.block(f"🔭 **Coming up, as you asked** ({len(ahead)})", [entry(it, line(it)) for it in ahead]))
    if follow:
        blocks.append(n.block(f"🔁 **Follow up** ({len(follow)}; nudge?)", [entry(it, line(it)) for it in follow]))
    blocks += list(extra)
    waiting = [it for it in waiting if it not in overdue + week + ahead + pinned]  # already numbered above
    if waiting:
        due = lambda it: f"{short_date(it['due'], today, it['approx'])} · " if it["due"] else ""
        blocks.append(n.block(f"⏳ **Waiting on you** ({len(waiting)})", [entry(
            it, f"{due(it)}{describe(gist(it['text']))}{waited(it, today)}{noted(it, today)}") for it in waiting]))
    if loose:
        blocks.append(n.block(f"🕸️ **Without a date** ({len(loose)}; do, date or drop?)",
                              [entry(it, line(it)) for it in in_turn(loose, today)]))
    limit = today + dt.timedelta(days=DAYS_OTHER_AREAS)
    others = [p for p in due_items(root, [a for a in areas(root) if a != area.name])
              if p[0] <= limit or (p[3]["prep"] and in_sight(p[3], today))]
    summary = []
    for a in [x for x in areas(root) if x != area.name]:
        late = [p for p in others if p[2] == a and p[0] < today and p[3]["section"] != OTHERS]
        nudge = [p for p in others if p[2] == a and p[0] < today and p[3]["section"] == OTHERS]
        soon = [p for p in others if p[2] == a and p[0] >= today]
        parts = ([f"{len(late)} overdue"] if late else []) + ([f"{len(nudge)} to follow up"] if nudge else [])
        if soon:
            parts.append(f"1 due {short_date(soon[0][0], today, soon[0][1])}" if len(soon) == 1
                         else f"{len(soon)} due by {short_date(soon[-1][0], today, soon[-1][1])}")
        cold = undated(open_items(Area(root, a)))
        oldest = next((it["since"] for it in cold if it["since"]), None)
        if oldest and (today - oldest).days > DAYS_AGED:
            parts.append(f"{len(cold)} without a date since {short_date(oldest, today)}")
        if parts:
            summary.append(f"{area_title(a)}, {' and '.join(parts)}")
    if summary:
        blocks.append(f"🗂️ **From other areas:** {'; '.join(summary)}")
    review = review_items(area, today)
    if also(review):
        blocks.append(f"➕ **Also:** {also(review)}.")
    reasons = sleep_reasons(root, area, inbox_min=INBOX_MAX + 1)
    notes = []
    repo = Path(__file__).resolve().parent.parent  # hooks only where someone set them; no repository in chat
    cwd = Path.cwd().resolve()
    local = repo / ".claude" / "settings.local.json"
    guarded = local.exists() and "guard.py" in text_of(local)
    if ((repo / ".claude" / "settings.json").exists() or guarded) and repo not in (cwd, *cwd.parents):
        notes.append(f"protection hooks off (session outside {str(repo).replace(str(Path.home()), '~')})")
    elif (repo / "tools").is_dir() and not guarded and any(limits(root).values()):
        notes.append("protections are only rules here: the guard is off (/protect turns it on)")
    if reasons:
        notes.append(f"worth running /sleep ({'; '.join(reasons)})")
    st = area.file("STATE.md")
    if st and series(st[0].get("system_version", "")) > series(VERSION):
        notes.append(f"memory at version {st[0]['system_version']}, newer than this system ({VERSION}): "
                     "update the repository (git pull) or reinstall the skill")
    if notes:
        blocks.append(f"⚠️ **Heads-up:** {'. '.join(x[:1].upper() + x[1:] for x in notes)}.")
    total = sum(len(v) for v in review.values())
    blocks.append(f"Weekly review: {total} item(s) waiting without a date. Go through them now, or which topic?"
                  if today.weekday() == REVIEW_DAY and total else "Which topic?")
    core = Area(root, "core").inbox
    agent = [f"Before replying, read in {root}: core/PROFILE.md and core/PREFERENCES.md (they override any default of "
             f"yours), core/PRINCIPLES.md ({NAME}'s decision criteria: check them before recommending), "
             f"areas/{area.name}/AREA.md (you become this assistant) and each inbox/core capture listed below.",
             f"Inbox: {len(area.inbox)} capture(s) from the area and {len(core)} from core not yet consolidated "
             "(already counted above; \"noted\" = from a pending capture)."]
    agent += [f"- inbox/{f.parent.name}/{f.name}" for f in core + area.inbox] + n.agent()
    if total:
        agent.append(f"\"Also\" and the weekly review: memory.py review <root> {area.name}")
    return "\n\n".join(blocks) + "\n\n" + for_agent(CALENDAR, *agent)


def owed(area, others=()):
    """What the owner owes, pending captures included: items with `for` (people), their loose ends, and how many
    wait on them. Waiting on others is what others owe, so it stays out.

    An item whose label ("Name: ...") is a known other person is not the owner's either (a board from before
    "Waiting on others"): `others` (the area's GitHub `Names`) or someone in core/people. Any other label is
    often the topic, so the item stays: hiding one of the owner's to-dos is worse than showing someone else's."""
    known = {fold(n) for n in others} | {fold(m.get("title", "")) for _, m, _ in Area(area.root, "core").records.values()}
    known -= {"", fold(NAME)}
    people, todos, waiting = [], [], 0
    for it in open_items(area):
        who = owner(it["text"])
        if it["section"] == OTHERS or (who and fold(who) in known):
            continue
        if it["for"]:
            people.append(it)
        elif it["section"] == "Loose ends":
            todos.append(it)
        elif it["section"] == "Waiting on":
            waiting += 1
    key = lambda it: (it["due"] is None, it["due"] or dt.date.max)
    return sorted(people, key=key), sorted(todos, key=key), waiting


def area_state(root, area):
    today = local_today()
    errors, warnings = validate(root, area)
    _, board = area.file("BOARD.md") or ({}, "(no BOARD.md)\n")
    items = open_items(area)
    running = threads(area)
    waiting = [it for it in items if waits_on_owner(it)]
    others = [it for it in items if it["section"] == OTHERS]
    loose = undated(items)
    fields = lambda it: ((f" | since {it['since']}" if it["since"] else "")
                         + (f" | due {'~' if it['approx'] else ''}{it['due']}" if it["due"] else "")
                         + (f" | last {it['last']}" if it["last"] else "") + (f" | prep {it['prep']}" if it["prep"] else "")
                         + (f" | every {it['every']}" if it["every"] else "") + (" | pin" if it["pin"] else "")
                         + (" (from a pending capture)" if it.get("noted") else ""))
    out = ["---", "type: state", f"area: {area.name}", f"generated: {now()}",
           f"system_version: {VERSION}", "---",
           f"# State of area {area.name} (generated by sleep; do not edit)", "",
           f"## Opening (overdue = due before today; computed on {today})",
           f"- Threads: {' | '.join(short(t) for t in running) or 'no thread in progress'}",
           f"- Waiting on you ({len(waiting)}):{'' if waiting else ' none'}"]
    out += [f"  - {short(it['text'])}{fields(it)}" for it in waiting]
    out += [f"- Waiting on others ({len(others)}; follow up when overdue or quiet for {DAYS_FOLLOW_UP} days):"
            + ("" if others else " none")]
    out += [f"  - {short(it['text'])}{fields(it)}" for it in others]
    turn = in_turn(loose, today)
    out += [f"- Without a date ({len(loose)}, oldest first; the opening shows this turn's):" + ("" if loose else " none")]
    out += [f"  - {short(it['text'])}{fields(it)}{' (this turn)' if it in turn else ''}" for it in loose]
    out += [f"- Pinned, {NAME} asked not to forget ({sum(it['pin'] for it in items)}):"]
    out += [f"  - {short(it['text'])}{fields(it)}" for it in items if it["pin"]] + ["- Due dates:"]
    out += [f"  - {'~' if a else ''}{d} · {short(it['text'])}{THEIRS if it['section'] == OTHERS else ''}"
            + (f" (show {it['prep']} days ahead)" if it["prep"] else "")
            for d, a, _, it in due_items(root, [area.name])] or ["  - none"]
    review = review_items(area, today)
    out += ["", "## Review (the opening's \"Also\" line and the weekly review)", f"- Also: {also(review) or 'none'}"]
    for key, _, title, _ in REVIEW:
        if review[key] and key not in ("questions", "quiet", "undated"):  # those are on the board below
            slug = lambda r: (lambda s: f" [[{s.group(1) or s.group(2)}]]" if s else "")(RECORD_REF.search(r))
            out += [f"- {title}:"] + [f"  - {l}{slug(r)}" for l, r, _ in review[key]]
    out += ["", "## Board", re.sub(r"^(#+) ", r"#\1 ", without_log(board).strip(), flags=re.M), ""]
    active = [(s, m) for s, (_, m, _) in area.records.items() if m.get("type") == "initiative" and m.get("status") == "active"]
    order = {"high": 0, "medium": 1, "low": 2, "tbd": 3}
    active.sort(key=lambda x: (order.get(x[1].get("priority"), 9), x[0]))
    out.append("## Active initiatives (slug | priority | owner | verified | next)")
    out += [initiative_line(s, m, today) for s, m in active] or ["- none"]
    out += ["", "## Inbox not yet consolidated"]
    out += [f"- {f.name}" for f in area.inbox] or ["- empty"]
    out += ["", f"## Integrity: {len(errors)} error(s), {len(warnings)} warning(s)"]
    out += [f"- ERROR {e}" for e in errors] + [f"- WARNING {w}" for w in warnings]
    return "\n".join(out) + "\n"


def root_key(root, path):
    """A folder's path with the root's current name in front (MAP.md or ids.json may carry another)."""
    rest = path.partition("/")[2]
    return f"{root.name}/{rest}" if rest else root.name


def drive_ids(root):
    """Folder ids that Google Drive for desktop writes on each folder (local mode, on a Mac); empty elsewhere."""
    ids = {}
    for p in [root] + sorted(q for q in root.rglob("*") if q.is_dir()):
        try:
            r = subprocess.run(["xattr", "-p", "com.google.drivefs.item-id#S", str(p)], capture_output=True, text=True)
        except FileNotFoundError:
            return {}
        if r.stdout.strip():
            ids["/".join((root.name,) + p.relative_to(root).parts)] = r.stdout.strip()
    return ids


def core_state(root, ids):
    today = local_today()
    out = ["---", "type: state", "area: core", f"generated: {now()}", f"system_version: {VERSION}", "---",
           "# View of all areas (generated by sleep; do not edit)", ""]
    notes = [f"- [{name}] {l}" for name in areas(root) for l in attention(Area(root, name))[0]]
    out += ["## Attention, all areas"] + (notes or ["- none"]) + [""]
    waiting, others, loose, pins, status = [], [], [], [], []
    for name in areas(root):
        a = Area(root, name)
        items = open_items(a)
        for it in items:
            since = f" (since {it['since']})" if it["since"] else ""
            due = f" (due {it['due']})" if it["due"] else ""
            last = f" (last news {it['last']})" if it["last"] else ""
            if waits_on_owner(it):
                waiting.append(f"- [{name}] {it['text']}{since}")
            elif it["section"] == OTHERS:
                others.append(f"- [{name}] {it['text']}{since}{due}{last}")
            if it["pin"]:
                pins.append(f"- [{name}] {it['text']}{since}{due}")
        loose += [f"- [{name}] {it['text']}" + (f" (since {it['since']})" if it["since"] else "") for it in undated(items)]
        st = a.file("STATE.md")
        generated = st[0].get("generated", "never") if st else "never"
        status.append(f"- {name}: state generated {generated}; inbox with {len(a.inbox)} capture(s)")
    core = Area(root, "core")
    status.append(f"- core: inbox with {len(core.inbox)} capture(s)")
    out += [f"## Due dates, all areas (by date; overdue = before today; computed on {today})"]
    out += [f"- {'~' if ap else ''}{d} [{n}] {it['text']}{THEIRS if it['section'] == OTHERS else ''}"
            + (f" (show {it['prep']} days ahead)" if it["prep"] else "")
            for d, ap, n, it in due_items(root, areas(root))] or ["- none"]
    out += ["", f"## Waiting on {NAME}, all areas"] + (waiting or ["- none"])
    out += ["", f"## Waiting on others, all areas (follow up when overdue or quiet for {DAYS_FOLLOW_UP} days)"]
    out += others or ["- none"]
    out += ["", "## Without a date, all areas"] + (loose or ["- none"])
    out += ["", f"## Pinned, {NAME} asked not to forget, all areas"] + (pins or ["- none"])
    out += ["", "## Status"] + status
    state = "\n".join(out) + "\n"

    map_ = ["---", "type: map", f"generated: {now()}", f"system_version: {VERSION}", "---",
            f"# Map of {root.name} (generated by sleep; do not edit)", "",
            "Folder ids for `parentId = '<id>'` in the Google Drive connector; the root is the first under Folders.", "",
            "## Areas"]
    for n in areas(root):
        r = Area(root, n).file("AREA.md")
        aliases = as_list(r[0].get("aliases")) if r else []
        map_.append(f"- {n}" + (f" (aliases: {', '.join(aliases)})" if aliases else ""))
    map_ += ["", "## Folders"]
    map_ += [f"- {path}: {fid}" for path, fid in sorted(ids.items())] or ["- (ids not provided)"]
    return state, "\n".join(map_) + "\n"


# ---------- brief, review and person ----------

def brief(root, until=None):
    """Every area at once, for the start of the day or "what do I have until Friday?": overdue, due dates up to
    `until` (the next DAYS_NEXT days without it), follow-ups, and one line each for what waits on <name>."""
    today = local_today()
    end = until or today + dt.timedelta(days=DAYS_NEXT - 1)
    n = Numbered()
    names = areas(root)
    rows = [(a, it) for a in names for it in open_items(Area(root, a))]
    line = lambda a, it: f"{when(it, today)} · {area_title(a)} · {gist(it['text'])}{noted(it, today)}"
    dated = sorted(((a, it) for a, it in rows if it["due"]), key=lambda x: x[1]["due"])
    overdue = [(a, it) for a, it in dated if it["due"] < today and it["section"] != OTHERS]
    soon = [(a, it) for a, it in dated if today <= it["due"] <= end]
    ahead = [(a, it) for a, it in dated if not until and it["due"] > end and in_sight(it, today)]
    pins = [(a, it) for a, it in rows if it["pin"] and (a, it) not in overdue + soon + ahead]
    follow = [(a, it) for a, it in rows if it in follow_ups([it], today) and (a, it) not in pins]
    follow.sort(key=lambda x: x[1]["due"] or x[1]["since"] or x[1].get("noted") or dt.date.min)
    day = f"{WEEKDAYS[today.weekday()]}, {MONTHS[today.month - 1]} {today.day}"
    blocks = [f"**All areas** · {day}"]
    tops = [f"{area_title(a)} · {notes[0]}" for a in names for notes in [attention(Area(root, a), today)[0]] if notes]
    if tops:
        blocks.append(block("🎯 **Attention**", tops, limit=ATTENTION_MAX))
    if pins:
        blocks.append(n.block(f"📌 **You asked not to forget** ({len(pins)})", [entry(it, line(a, it), a) for a, it in pins]))
    if overdue:
        blocks.append(n.block("🔴 **Overdue** (done, postpone or drop?)", [entry(it, line(a, it), a) for a, it in overdue]))
    title = f"until {short_date(end, today)}" if until else f"next {DAYS_NEXT} days"
    later = [it["due"] for _, it in dated if max(end, today) < it["due"] and (it["due"] - today).days <= DAYS_AHEAD]
    after = [(a, it) for a, it in dated if later and it["due"] == later[0] and (a, it) not in ahead]  # every item of the next due day
    if soon:
        blocks.append(n.block(f"📅 **Due dates, {title}** ({len(soon)})", [entry(it, line(a, it), a) for a, it in soon]))
    elif after:  # nothing in the range: the next one, so "nothing" doesn't hide tomorrow
        blocks.append(n.block(f"📅 **Due dates, {title}:** none. **Next**", [entry(it, line(a, it), a) for a, it in after]))
    else:
        blocks.append(f"📅 **Due dates, {title}:** none.")
    if ahead:
        blocks.append(n.block(f"🔭 **Coming up, as you asked** ({len(ahead)})", [entry(it, line(a, it), a) for a, it in ahead]))
    if follow:
        blocks.append(n.block(f"🔁 **Follow up** ({len(follow)}; nudge?)", [entry(it, line(a, it), a) for a, it in follow]))
    cold = sorted(((a, it) for a, it in rows if it in undated([it])), key=lambda x: x[1]["since"] or dt.date.min)
    if cold:
        blocks.append(n.block(f"🕸️ **Without a date** ({len(cold)}; do, date or drop?)",
                              [entry(it, line(a, it), a) for a, it in in_turn(cold, today)]))
    waiting = []
    for a in names:
        mine = [it for x, it in rows if x == a and waits_on_owner(it)]
        oldest = min((it["since"] for it in mine if it["since"]), default=None)
        if mine:
            waiting.append(f"{area_title(a)} {len(mine)}" + (f" (oldest since {short_date(oldest, today)})"
                                                              if oldest and (today - oldest).days > DAYS_WAITING else ""))
    if waiting:
        blocks.append(f"⏳ **Waiting on you:** {'; '.join(waiting)}")
    more = [f"{area_title(a)}: {also(review_items(Area(root, a), today))}" for a in names]
    more = [m_ for m_ in more if not m_.endswith(": ")]
    if more:
        blocks.append(f"➕ **Also:** {'; '.join(more)}.")
    late = [f"{a}: {'; '.join(r)}" for a in names + ["core"] for r in [sleep_reasons(root, Area(root, a), INBOX_MAX + 1)] if r]
    if late:
        blocks.append(f"⚠️ **Heads-up:** worth running /sleep ({'; '.join(late)}).")
    choices = []
    for a in names:
        r = Area(root, a).file("AREA.md")
        aliases = as_list(r[0].get("aliases")) if r else []
        choices.append(a + (f" ({', '.join(aliases)})" if aliases else ""))
    blocks.append(f"Which area? {', '.join(choices)}")
    return "\n\n".join(blocks) + "\n\n" + for_agent(CALENDAR, "Pending captures are already counted (\"noted\").", *n.agent())


def review(root, names):
    """The weekly review: everything that waits without a date or went quiet, area by area, numbered."""
    today = local_today()
    n, blocks = Numbered(), []
    for a in names:
        found = review_items(Area(root, a), today)
        if not any(found.values()):
            continue
        blocks.append(f"**Weekly review · {area_title(a)}** · {WEEKDAYS[today.weekday()]}, {MONTHS[today.month - 1]} {today.day}")
        blocks += [n.block(f"{icon} **{title}** ({len(found[key])})", [(l, f"[{a}] {r}", t) for l, r, t in found[key]], limit=10)
                   for key, icon, title, _ in REVIEW if found[key]]
    if not blocks:
        return f"Nothing waiting without a date in {', '.join(area_title(a) for a in names)}.\n\n{for_agent()}"
    blocks.append("Which first? (e.g. \"1 done, 2 drop, 3 Friday\")")
    return "\n\n".join(blocks) + "\n\n" + for_agent(*n.agent())


def person(root, name):
    """Everything open with someone, in every area: what <name> owes them, what they owe, other mentions,
    threads, the last dated event naming them (LOG.md, or a record's "Last contact") and the records naming them."""
    today = local_today()
    first = name.split()[0] if name.split() else ""  # "Diego" finds "Diego Souza", unless it is the owner's name too
    keys = {fold(name)} | ({fold(first)} if len(name.split()) > 1 and not is_owner(first) else set())
    hit = lambda text: any(re.search(rf"\b{re.escape(k)}\b", fold(text or "")) for k in keys if k)
    n = Numbered()
    owe, owes, other, running, records, logs = [], [], [], [], [], []
    for a in areas(root):
        area = Area(root, a)
        for it in open_items(area):
            text = clean(it["text"])  # markers out: "[<name> date]" would name the owner on every line
            if it["section"] == OTHERS and hit(owner(it["text"])):
                owes.append((a, it))
            elif hit(it["for"]) or (it["section"] == "Waiting on" and hit(text)):
                owe.append((a, it))
            elif hit(text):
                other.append((a, it))
        running += [(a, t) for t in threads(area) if hit(t)]
        records += [(a, s, m_.get("title") or s) for s, (_, m_, b) in sorted(area.records.items())
                    if hit(m_.get("title")) or hit(clean(b))]
        for body in log_bodies(area):
            for l in section(body, "Log", prefix=True):
                if iso_date(l[2:12]) and hit(clean(l)):
                    logs.append((iso_date(l[2:12]), a, l[2:].split(":", 1)[-1]))
    for a in areas(root) + ["core"]:
        for _, m_, b in Area(root, a).records.values():
            for l in section(b, "Facts"):
                last = LAST_CONTACT.match(l)
                if last and iso_date(last.group(1)) and (hit(m_.get("title")) or hit(clean(l))):
                    logs.append((iso_date(last.group(1)), a, last.group(2)))
    facts = [clean(l[2:]) for _, m_, b in Area(root, "core").records.values() if hit(m_.get("title"))
             for l in section(b, "Facts")[:3]]
    if not (owe or owes or other or running or records or logs or facts):
        return f"Nothing open with {name} in the records.\n\n{for_agent()}"
    line = lambda a, it: f"{area_title(a)} · {when(it, today)} · {gist(it['text'])}{noted(it, today)}"
    blocks = [f"**{name}** · {WEEKDAYS[today.weekday()]}, {MONTHS[today.month - 1]} {today.day}"]
    if facts:
        blocks.append("; ".join(short(f) for f in facts))
    for title, rows in ((f"You owe {name}", owe), (f"{name} owes you", owes), ("Also mentioned", other)):
        if rows:
            blocks.append(n.block(f"**{title}** ({len(rows)})", [entry(it, line(a, it), a) for a, it in rows]))
    if running:
        blocks.append("🧵 **In progress:** " + "; ".join(f"{area_title(a)} · {short(t)}" for a, t in running))
    if logs:
        d, a, what = max(logs)
        where = "" if a == "core" else f" · {area_title(a)}"
        blocks.append(f"**Last contact:** {short_date(d, today)}{where} · {short(what)}")
    if records:
        blocks.append("**In the records:** " + "; ".join(f"{t} ({area_title(a)})" for a, _, t in records[:5])
                      + (f"; and {len(records) - 5} more" if len(records) > 5 else ""))
    refs = f"Records: {', '.join(f'{a}:{s}' for a, s, _ in records)}" if records else ""
    return "\n\n".join(blocks) + "\n\n" + for_agent(*n.agent(), refs)


def digest(root, area):
    """The area on one screen, for sleep to write ## Attention: what is open, what is at stake and what the opening
    doesn't show, such as risks, consequences and the dates that live only in a record."""
    today = local_today()
    _, board = area.file("BOARD.md") or ({}, "")
    records = sorted(area.records.items())
    out = [f"# Digest of {area.name}, {today}"]
    for title in BOARD_OPTIONAL:
        out += [f"## {title}"] + [f"- {clean(l[2:])}" for l in section(board, title)]
    out += ["## Open items"] + [f"- {ref(it)}" for it in open_items(area)]
    out += ["## Threads"] + [f"- {t}" for t in threads(area)]
    out += ["## Active initiatives (slug | priority | owner | verified | next)"]
    for slug, (_, meta, body) in records:
        if meta.get("type") == "initiative" and meta.get("status") == "active":
            out.append(initiative_line(slug, meta, today))
            out += [f"  - risk: {clean(l[2:])}" for l in section(body, "Risks")]
    out += [f"## Decisions of the last {DAYS_LOG} days, or waiting for their review"]
    for slug, (_, meta, body) in records:
        made, review = iso_date(meta.get("date")), iso_date(meta.get("review_on"))
        recent = made and (today - made).days <= DAYS_LOG
        pending_review = review and "## Outcome" not in body and (review - today).days <= DAYS_AHEAD
        if meta.get("type") == "decision" and meta.get("status") in ("approved", "proposed") and (recent or pending_review):
            out.append(f"- [[{slug}]] | {meta.get('status')} | {meta.get('date', '')} | {meta.get('title', '')}" + (f" | review_on {review}" if review else ""))
            out += [f"  - consequence: {clean(l[2:])}" for l in section(body, "Consequences")]
    out += ["## Dates only in a record, on no open item"]
    out += [f"- {day} | [[{slug}]] | {where} | {text}" for day, slug, where, text in hidden(area, today)] or ["- none"]
    out += [f"## Due in other areas, next {DAYS_AHEAD} days"]
    limit = today + dt.timedelta(days=DAYS_AHEAD)
    out += [f"- {d} [{a}] {clean(it['text'])}" for d, _, a, it in due_items(root, [x for x in areas(root) if x != area.name]) if d <= limit] or ["- none"]
    log = area.file("LOG.md")
    out += ["## Latest in LOG.md"] + (section(log[1], "Log", prefix=True)[:10] if log else [])
    return "\n".join(out) + "\n"


def archive_log(area, today):
    """Moves LOG.md entries over DAYS_LOG days old, with their indented details, to the top of log/<YYYY-MM>.md, whose
    content stays as it is: nothing dated is lost, and LOG.md, the one the agents read, stays short. Writes the archive
    first, so an interrupted run only repeats; a file that isn't valid UTF-8 (the validator flags it) is left alone."""
    f = area.folder / "LOG.md"
    text = text_of(f) if f.exists() else ""
    if "�" in text:
        return 0
    kept, moved, month = [], {}, None
    for l in text.split("\n"):
        if month and l[:1] in (" ", "\t"):
            moved[month][-1] += f"\n{l}"
            continue
        day = iso_date(l[2:12]) if l.startswith("- ") else None
        month = day.strftime("%Y-%m") if day and (today - day).days > DAYS_LOG else None
        if month:
            moved.setdefault(month, []).append(l)
        else:
            kept.append(l)
    for month, entries in moved.items():
        g = area.folder / "log" / f"{month}.md"
        g.parent.mkdir(exist_ok=True)
        lines = (text_of(g).rstrip("\n") if g.exists() else f"---\ntype: log\n---\n## Log ({month})").split("\n")
        known = set(lines)
        at = next((i + 1 for i, l in enumerate(lines) if l.startswith("## Log")), len(lines))
        lines[at:at] = [e for e in sorted(entries, key=lambda e: e[2:12], reverse=True) if e.split("\n")[0] not in known]
        g.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if moved:
        f.write_text("\n".join(kept), encoding="utf-8")
    return sum(len(v) for v in moved.values())


# ---------- capture ----------

def capture_problems(body):
    """What would make the opening read a capture wrong, or lose it: sections outside the template, malformed fields,
    a due date left in the text, a closing word other than "Done:", a secret. To fix before it is written."""
    problems = []
    if not body.strip():
        problems.append("empty body")
    if body.lstrip().startswith("---"):
        problems.append("send only the body: the frontmatter is written here")
    outside = [t for t in re.findall(r"^#+ *(.*?)\s*$", body, re.M) if t not in CAPTURE_SECTIONS]
    if outside:
        problems.append(f"sections outside the template ({'; '.join(outside)}): only {', '.join(CAPTURE_SECTIONS)}")
    if SECRETS.search(body):
        problems.append("looks like it holds a secret; memory never stores one")
    for l in section(body, "To-dos") + section(body, "Questions"):
        it = board_item("", l)
        label = f"'{clean(l[2:])[:50]}'"
        if NOT_DONE.match(l):
            problems.append(f"{label}: a closed to-do starts with '- Done:'")
        problems += [f"{label}: {e}" for e in it["errors"]]
        if it["every"] and not it["due"]:
            problems.append(f"{label}: 'every' needs '| due'")
        if not DONE.match(l) and not it["due"]:
            loose = dates_in_text(it["text"]) + later_dates(it["text"], local_today())
            if loose:
                problems.append(f"{label}: due date in the text ({', '.join(dict.fromkeys(loose))}); use '| due YYYY-MM-DD'")
    return problems


def write_capture(root, area, origin, topic, body, forget=False):
    """Writes a capture from its body: names the file, stamps the time to the second, so sessions in the same minute
    keep their order, and never overwrites another session's file. Refuses what capture_problems finds: nothing is
    written, and the agent fixes it on the spot, while the person is still there to ask."""
    problems = ([] if origin in ORIGINS else [f"invalid origin ({origin}): {', '.join(sorted(ORIGINS))}"]) + capture_problems(body)
    if problems:
        print("nothing written; fix and repeat:")
        for p in problems:
            print(f"- {p}")
        return 1
    stamp = dt.datetime.now(TZ)
    slug = re.sub(r"[^a-z0-9]+", "-", fold(topic))[:60].strip("-") or "capture"
    folder = root / "inbox" / area.name
    folder.mkdir(parents=True, exist_ok=True)
    head = (f"---\ntype: capture\narea: {area.name}\ndate: {stamp:%Y-%m-%dT%H:%M:%S}\norigin: {origin}\n"
            f"mode: {'forget' if forget else 'normal'}\n---\n")
    n = 1
    while True:
        f = folder / f"{stamp:%Y%m%d-%H%M}-{origin}-{slug}{'' if n == 1 else f'-{n}'}.md"
        try:
            with open(f, "x", encoding="utf-8") as out:
                out.write(head + body.strip() + "\n")
            break
        except FileExistsError:
            n += 1
    print(f"written inbox/{area.name}/{f.name}")
    return 0


# ---------- new memory and areas ----------

def from_template(src, dest, name, today, fields=(), area=None):
    """A template copied with <name>, <area> and the `updated` date filled in, and frontmatter fields set."""
    text = text_of(src).replace("<name>", name)
    if area:
        text = text.replace("<area>", area)
    text = re.sub(r"^updated: YYYY-MM-DD$", f"updated: {today}", text, count=1, flags=re.M)
    for key, value in fields:
        text = re.sub(rf"^{key}:.*$", lambda _: f"{key}: {value}", text, count=1, flags=re.M)
    dest.write_text(text, encoding="utf-8")


def new_memory(root, name, tz, language):
    """A new memory: core/ from templates/ with the profile fields, core/people/ and inbox/core/."""
    if (root / "core" / "PROFILE.md").exists():
        print(f"there is already a memory in {root}; nothing changed")
        return 1
    if not TEMPLATES.is_dir():
        print("templates/ not found: run memory.py from the hippOS repository")
        return 2
    if not re.fullmatch(r"UTC|[A-Za-z_]+(/[A-Za-z0-9_+-]+)+", tz) or not known_timezone(tz):
        print(f"unknown timezone: {tz} (IANA, e.g. America/New_York)")
        return 2
    if not LANGUAGE.fullmatch(language):
        print(f"invalid language: {language} (e.g. en, pt-BR)")
        return 2
    for folder in (root / "core" / "people", root / "inbox" / "core"):
        folder.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(timezone(tz)).date()
    for f in sorted((TEMPLATES / "core").glob("*.md")):
        dest = root / "core" / f.name
        if not dest.exists():
            fields = (("name", name), ("timezone", tz), ("language", language)) if f.name == "PROFILE.md" else ()
            from_template(f, dest, name, today, fields)
    print(f"created {root}")
    return 0


def new_area(root, area, aliases):
    """A new area: the files of templates/area/, its folders and its inbox."""
    if not SLUG.match(area) or area == "core":
        print(f"invalid area name: {area} (lowercase letters, digits and hyphens, e.g. side-project)")
        return 2
    if not (root / "core" / "PROFILE.md").exists():
        print(f"no memory in {root} yet: run `memory.py new` first")
        return 2
    folder = root / "areas" / area
    if folder.exists():
        print(f"area {area} already exists; nothing changed")
        return 1
    if not TEMPLATES.is_dir():
        print("templates/ not found: run memory.py from the hippOS repository")
        return 2
    for sub in FOLDERS + ("drafts",):
        (folder / sub).mkdir(parents=True)
    (root / "inbox" / area).mkdir(parents=True, exist_ok=True)
    for f in sorted((TEMPLATES / "area").glob("*.md")):
        fields = (("title", f"{area_title(area)} assistant"), ("aliases", f"[{', '.join(aliases)}]")) if f.name == "AREA.md" else ()
        from_template(f, folder / f.name, NAME, local_today(), fields, area)
    print(f"created {folder}")
    return 0


# ---------- index and context ----------

def index(area):
    for s, (_, m, _) in sorted(area.records.items(), key=lambda x: (x[1][1].get("type", ""), x[1][1].get("status", ""), x[0])):
        date = m.get("verified") or m.get("date") or m.get("updated") or ""
        print(f"{m.get('type', ''):11} {m.get('status', ''):11} {date:10} {s}  {m.get('title', '')}")


def context(root, area, slug):
    if slug not in area.records:
        print(f"missing slug: {slug}")
        return 1
    f, meta, body = area.records[slug]
    print(text_of(f))
    near = set(LINK.findall(body))
    for c in LISTS:
        near.update(as_list(meta.get(c)))
    for c in SIMPLE_REFS:
        if meta.get(c):
            near.add(meta[c])
    for other, (g, m, b) in area.records.items():
        if other == slug:
            continue
        if f"[[{slug}]]" in b or any(slug in as_list(m.get(c)) for c in LISTS) or slug in (m.get("supersedes"), m.get("superseded_by")):
            near.add(other)
    print("== NEIGHBORS (slug | type | status | title)")
    for v in sorted(near):
        if v in area.records:
            m = area.records[v][1]
            print(f"{v} | {m.get('type')} | {m.get('status', '')} | {m.get('title', '')}")
        else:
            print(f"{v} | (other area or missing)")
    citing = [p.name for p in area.inbox if slug in text_of(p)]
    if citing:
        print("== PENDING CAPTURES CITING THE SLUG")
        print("\n".join(citing))
    return 0


# ---------- fidelity ----------

def literals(text):
    """A capture's literals, outside markers, links and the lines that leave on purpose."""
    lines = [l for l in text.split("\n") if not LEFT_ON_PURPOSE.match(l)]
    return list(dict.fromkeys(m.group(0).rstrip(".,;:") for m in LITERAL.finditer(NOTATION.sub("", "\n".join(lines)))))


def present(lit, corpus, compact):
    if lit.startswith("`"):
        return lit.strip("`") in corpus
    if lit.startswith(CURRENCIES + ("http",)):  # R$ 34 is not found in R$ 340 or R$ 34,50
        return re.search(re.escape(re.sub(r"\s", "", lit).rstrip(".,;")) + r"(?![\d.,]*\d)", compact) is not None
    if re.fullmatch(r"\d{2}/\d{2}(/\d{2,4})?", lit):
        a, b = lit.split("/")[:2]  # dd/mm or mm/dd
        return lit in corpus or re.search(rf"\d{{4}}-({b}-{a}|{a}-{b})\b", corpus) is not None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", lit):
        return lit in corpus
    number = re.findall(r"\d+", lit)[-1]
    return re.search(rf"\b{number}\b", corpus) is not None


def lost_items(area, captures):
    """(capture, what) of each to-do or question of the area's captures that names no board item, no parked one and
    no closed one, and of each closed one with no line in LOG.md. Read from the files themselves: open_items would
    find each one in its own pending capture."""
    if not (area.folder / "BOARD.md").exists():
        return []
    mine = [f for f in captures if f.parent.name == area.name and read(f)[0].get("mode") != "forget"]
    closed = [(f.name, board_item("", f"- {d.group(1)}")["text"]) for f in mine for l in section(read(f)[1], "To-dos") for d in [DONE.match(l)] if d]
    kept = [it["text"] for it in board_items(area.file("BOARD.md")[1])]
    kept += [l[2:] for _, _, body in area.records.values() for part in ("Open", "Addenda") for l in section(body, part)]
    logged = []
    for l in (l for body in log_bodies(area) for l in section(body, "Log", prefix=True)):
        text = re.sub(r"^\d{4}-\d{2}-\d{2}:\s*", "", l[2:])
        d = DONE.match(f"- {text}")
        logged.append(d.group(1) if d else text)
    lost = []
    for f in mine:
        for l in section(read(f)[1], "To-dos") + section(read(f)[1], "Questions"):
            it = board_item("", l)
            if DONE.match(l) or it["empty"] or not words(it["text"]):
                continue
            if not any(matches(k, it["text"]) for k in kept) and not any(matches(it["text"], c) for _, c in closed):
                lost.append((f.name, f"not on the board: {clean(it['text'])}"))
    lost += [(name, f"closed, but not in LOG.md: {clean(c)}") for name, c in closed if not any(matches(x, c) for x in logged)]
    return lost


def fidelity(root, area, names):
    """Literals, to-dos and questions of each capture missing from the curated memory of the area and of core.

    An argument that is not an inbox capture is the before-copy of a split topic: each of its lines must be in the memory."""
    files = [f for f, _, _ in area.records.values()] + [f for f, _, _ in Area(root, "core").records.values()]
    files += [area.folder / n for n in ("BOARD.md", "LOG.md", "AREA.md")] + sorted((area.folder / "log").glob("*.md"))
    files += [root / "core" / n for n in ("PREFERENCES.md", "PROFILE.md", "PRINCIPLES.md")]
    corpus = "\n".join(text_of(f) for f in files if f.exists())
    compact = re.sub(r"[^\S\n]", "", corpus)  # lines stay apart: "R$ 34." is not "R$ 34.12" with the next line
    missing = 0
    in_inbox = {f.name for f in area.inbox + Area(root, "core").inbox}
    before = sorted(n for n in names if Path(n).name not in in_inbox)
    for name in before:
        if not Path(name).expanduser().is_file():
            print(f"{name}: neither an inbox capture nor an existing before-copy")
            missing += 1
            continue
        body = read(Path(name).expanduser())[1]
        lost = [l for l in body.split("\n") if l.startswith("- ") and re.sub(r"\s", "", l) not in compact]
        missing += len(lost)
        for l in lost:
            print(f"{Path(name).name}: lost line: {l[:100]}")
    names = {Path(n).name for n in names if Path(n).name in in_inbox}
    captures = area.inbox + ([] if area.name == "core" else Area(root, "core").inbox)
    if names or before:
        captures = [f for f in captures if f.name in names]
    for f in captures:
        meta, body = read(f)
        if meta.get("mode") == "forget":
            continue
        absent = [l for l in literals(body) if not present(l, corpus, compact)]
        missing += len(absent)
        if absent:
            print(f"{f.name}: {', '.join(absent)}")
    lost = lost_items(area, captures)
    missing += len(lost)
    for name, what in lost:
        print(f"{name}: {what[:120]}")
    print(f"fidelity: {len(captures)} capture(s), {missing} literal(s) or line(s) to check")
    return 1 if missing else 0


# ---------- main ----------

def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    if argv[1:2] == ["root"]:
        found = find_roots()
        if not found:
            print(f"no {ROOT_NAME} folder in Google Drive for desktop (HIPPOS_ROOT unset or missing): use connector mode")
            return 1
        print(found[0])
        if len(found) > 1:
            print(f"others, older: {', '.join(map(str, found[1:]))}; HIPPOS_ROOT pins one", file=sys.stderr)
        return 0
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, root = argv[1], Path(argv[2]).expanduser().resolve()  # "." has no name, and MAP.md is titled with it
    if cmd == "new":
        if len(argv) != 6:
            print(__doc__)
            return 2
        return new_memory(root, *argv[3:6])
    write = "--write" in argv
    if not root.exists():
        print(f"root does not exist: {root}")
        return 2
    configure(root)
    if cmd == "area":
        if len(argv) < 4:
            print(__doc__)
            return 2
        return new_area(root, argv[3], argv[4:])
    if cmd in ("state", "opening", "review", "index", "context", "fidelity", "person", "digest", "archive") and len(argv) < (5 if cmd == "context" else 4):
        print(__doc__)
        return 2
    if cmd == "capture" and len(argv) < 6:
        print(__doc__)
        return 2
    if cmd in WITH_AREA and len(argv) > 3 and not argv[3].startswith("--") and not (cmd in ("validate", "review") and argv[3] == "all"):
        argv[3] = area_from_argument(root, argv[3])
    if cmd in ("state", "opening", "review") and argv[3] == "core":
        print(f"{cmd} is per area" + (" (or all)" if cmd == "review" else "; core/STATE.md comes from: memory.py core <root> --write"))
        return 2
    if cmd == "validate":
        target = argv[3] if len(argv) > 3 and not argv[3].startswith("--") else "all"
        names = areas(root) + ["core"] if target == "all" else [target]
        total = 0
        for name in names:
            errors, warnings = validate(root, Area(root, name))
            for e in errors:
                print(f"[{name}] ERROR   {e}")
            for w in warnings:
                print(f"[{name}] WARNING {w}")
            print(f"[{name}] validate: {len(errors)} error(s), {len(warnings)} warning(s)")
            total += len(errors)
        return 1 if total else 0
    if cmd == "pending":
        return pending(root)
    if cmd == "state":
        area = Area(root, argv[3])
        text = area_state(root, area)
        if write:
            (area.folder / "STATE.md").write_text(text, encoding="utf-8")
            print(f"written {area.folder / 'STATE.md'}")
        else:
            print(text)
        return 0
    if cmd == "core":
        ids = {}
        if (root / "MAP.md").exists():
            folders = section(read(root / "MAP.md")[1], "Folders")
            ids = dict(m.groups() for m in map(re.compile(r"^- ([^:]+): (\S+)$").match, folders) if m)
        ids.update(drive_ids(root))
        if "--ids" in argv:
            extra = json.loads(Path(argv[argv.index("--ids") + 1]).read_text(encoding="utf-8"))
            ids.update({k: v for k, v in extra.items() if not k.endswith(".md")})
        ids = {root_key(root, k): v for k, v in ids.items() if (root / k.partition("/")[2]).is_dir()}
        state, map_ = core_state(root, ids)
        if write:
            (root / "core").mkdir(exist_ok=True)
            (root / "core" / "STATE.md").write_text(state, encoding="utf-8")
            (root / "MAP.md").write_text(map_, encoding="utf-8")
            print("written core/STATE.md and MAP.md")
        else:
            print(state)
            print(map_)
        return 0
    if cmd == "opening":
        print(opening(root, Area(root, argv[3])))
        return 0
    if cmd == "brief":
        until = iso_date(argv[3]) if len(argv) > 3 else None
        if len(argv) > 3 and not until:
            print(f"invalid date: {argv[3]} (YYYY-MM-DD)")
            return 2
        print(brief(root, until))
        return 0
    if cmd == "review":
        print(review(root, areas(root) if argv[3] == "all" else [argv[3]]))
        return 0
    if cmd == "person":
        print(person(root, " ".join(argv[3:])))
        return 0
    if cmd == "index":
        index(Area(root, argv[3]))
        return 0
    if cmd == "context":
        return context(root, Area(root, argv[3]), argv[4])
    if cmd == "fidelity":
        return fidelity(root, Area(root, argv[3]), set(argv[4:]))
    if cmd == "capture":
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        return write_capture(root, Area(root, argv[3]), argv[4], argv[5], sys.stdin.read() if sys.stdin else "", "--forget" in argv)
    if cmd == "digest":
        print(digest(root, Area(root, argv[3])))
        return 0
    if cmd == "archive":
        print(f"{archive_log(Area(root, argv[3]), local_today())} LOG entries moved to log/")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
