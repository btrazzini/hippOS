#!/usr/bin/env python3
"""hippOS memory tool. Python 3.8+, no dependencies.

Works on a local copy of the memory root in Drive (or the synced folder itself).
Never touches the network. The owner's name and timezone come from the frontmatter
of core/PROFILE.md (`name`, `timezone`).

  root                                   the root in Google Drive for desktop (Mac or Windows); HIPPOS_ROOT sets another
  new      <root> <name> <timezone> <language>   creates a memory from templates/ (never over an existing one)
  area     <root> <area> [alias ...]     adds an area from templates/ (never over an existing one)
  validate <root> [area|core|all]        schema, links, captures, board, overdue
  pending  <root>                        what sleep with no argument processes, and why
  state    <root> <area> [--write]       generates areas/<area>/STATE.md
  core     <root> [--write] [--ids f]    generates core/STATE.md and MAP.md
  opening  <root> <area>                 first reply, ready, computed now
  (GitHub and other area sources: tools/lookup.py)
  index    <root> <area>                 every record by type and status
  context  <root> <area> <slug>          the record and its neighbors
  fidelity <root> <area> [capture ...]   capture literals missing from the memory
"""
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

VERSION = "0.1.0"
TZ = dt.datetime.now().astimezone().tzinfo  # TZ, NAME, MARKER and NOTATION: configure(), from PROFILE.md
NAME = "owner"
DAYS_STALE = 14
DAYS_AGED = 14
DAYS_STATE = 3
DAYS_OTHER_AREAS = 3
BOARD_MAX_LINES = 80
BOARD_MAX_BYTES = 9000
INBOX_MAX = 15
ITEM_SECTIONS = ("Waiting on", "Loose ends", "Questions for")  # "Waiting on <name>", "Questions for <name>"
BOARD_SECTIONS = ITEM_SECTIONS + ("Thread",)
AGING_SECTIONS = ("Waiting on", "Questions for")
CAPTURE_SECTIONS = ("Decisions", "State", "To-dos", "Preferences", "Thread")
EMPTY = {"none", "nothing"}
TEXT_MAX = 70
BLOCK_ITEMS = 3
AGENT_SEPARATOR = "----- agent only, do not show -----"
PREFERENCES_MAX = 500  # words; read every session: for a rule to come in, another leaves or merges
TOPIC_MAX = 800  # words; above it, sleep splits the topic
CURRENCIES = ("R$", "US$", "$", "€", "£")
# Literals consolidation tends to lose: amounts, code, links, issues and PRs, dates, numbers
LITERAL = re.compile(r"(?:R\$|US\$|\$|€|£)\s?\d[\d.,]*|`[^`\n]{2,80}`|https?://[^\s)>\]]+|\b[\w.-]+/[\w.-]+#\d+|#\d{2,}"
                     r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}(?:/\d{2,4})?\b|\b\d{3,}\b")
LEFT_ON_PURPOSE = re.compile(r"^- (done|resolved|dropped|cancel|discard)", re.I)
FOLDERS = ("initiatives", "decisions", "topics")
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
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# Words right before a date that make it look like a due date (content is in the owner's language)
DUE_WORDS = re.compile(r"\b(?:by|due(?: on| by)?|deadline:?|until|before|around|renews?(?: on)?"
                       r"|até|vence(?: em)?|prazo:?|por volta de|renova(?: em)?)\s*$")
CAPTURE_NAME = re.compile(r"^\d{8}-\d{4}-[a-z-]+-[a-z0-9-]+\.md$")
FIELD = re.compile(r"^(since|due):?\s+(~?)(\S+)$")
FIELD_FOR = re.compile(r"^for:?\s+(.+)$")
MARKERS = r"fact|{name}|inherited|hypothesis|recommendation"
WITH_AREA = ("validate", "state", "opening", "index", "context", "fidelity")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ROOT_NAME = "hippOS"  # the memory folder, directly in My Drive
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
    global NAME, TZ, MARKER, NOTATION
    profile = root / "core" / "PROFILE.md"
    meta = read(profile)[0] if profile.exists() else {}
    NAME = meta.get("name") or "owner"
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


def section(body, title, prefix=False):
    """First-level items ('- ') of a '## <title>' section (or of one starting with it, with `prefix`)."""
    rest = r"[^\n]*" if prefix else r"\s*"
    m = re.search(rf"^## {re.escape(title)}{rest}\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return [l for l in m.group(1).split("\n") if l.startswith("- ")] if m else []


# ---------- board ----------

def board_item(title, line):
    """A board item: '- text | since YYYY-MM-DD | due [~]YYYY-MM-DD | for <who>'."""
    parts = line[2:].strip().split(" | ")
    fields, errors = {}, []
    while len(parts) > 1:
        who = FIELD_FOR.match(parts[-1].strip())
        if who:
            parts.pop()
            if "for" in fields:
                errors.append("repeated for field")
            fields["for"] = who.group(1).strip()
            continue
        m = FIELD.match(parts[-1].strip())
        if not m:
            break
        key, approx, value = m.groups()
        parts.pop()
        if key in fields:
            errors.append(f"repeated {key} field")
        elif len(value) != 10 or not iso_date(value):
            errors.append(f"{key} with an invalid date ({value})")
        elif approx and key == "since":
            errors.append("since does not take ~")
        else:
            fields[key] = (iso_date(value), bool(approx))
    text = " | ".join(parts).strip()
    due, approx = fields.get("due", (None, False))
    return {"section": title, "text": text, "since": fields.get("since", (None,))[0],
            "due": due, "approx": approx, "for": fields.get("for"), "empty": text.lower().rstrip(".") in EMPTY, "errors": errors}


def board_items(body):
    return [board_item(t, l) for t in ITEM_SECTIONS for l in section(body, t, prefix=True)]


def dates_in_text(text):
    """Dates that look like due dates in free text, outside markers and links (the format asks for '| due')."""
    bare = NOTATION.sub("", text)
    found = []
    for m in DATE.finditer(bare):
        before = bare[max(0, m.start() - 30):m.start()].lower()
        if DUE_WORDS.search(before):
            found.append(m.group(1))
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
            if not re.search(rf"^## {re.escape(title)}", body, re.M):
                full = title + ("" if title in ("Loose ends", "Thread") else " <name>")
                errors.append(f"BOARD.md without '## {full}': headings stay in English, as in templates/")
        overdue = 0
        for it in board_items(body):
            if it["empty"]:
                continue
            label = f"BOARD.md ({it['section']}) '{it['text'][:50]}'"
            errors += [f"{label}: {e}" for e in it["errors"]]
            if not it["since"]:
                errors.append(f"{label}: no '| since YYYY-MM-DD'")
            loose = [d for d in dates_in_text(it["text"]) if not it["due"] or d != it["due"].isoformat()]
            if loose:
                errors.append(f"{label}: due date in the text ({', '.join(loose)}); use '| due YYYY-MM-DD', one per item")
            if it["due"] and it["due"] < today:
                overdue += 1
            if (it["section"] in AGING_SECTIONS and it["since"] and LINK.search(it["text"])
                    and (today - it["since"]).days > DAYS_AGED):
                warnings.append(ForSleep("aged item to move to its record", f"{label}: aged, since {it['since']}; move it to the linked record's ## Open"))
        if overdue:
            warnings.append(f"BOARD.md: {overdue} item(s) overdue; the opening asks {NAME}")

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
    return re.sub(rf"^{re.escape(NAME)}:\s*", "", t)


def short(text, limit=TEXT_MAX):
    """The gist of the item, before the first detail; a short label ("Goal: ...") stays."""
    t = clean(text)
    label = re.match(r"^[^:]{1,25}: ", t)
    start = label.end() if label else 0
    cut = next((m for m in re.finditer(r" \(|[.:;] ", t) if m.start() >= max(start, 15)), None)
    if cut:
        t = t[:cut.start()]
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0].rstrip(" .;,:(") + "..."
    return t[:1].upper() + t[1:]


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
    """(due, approx, area, item) for every item with a due date, by date."""
    out = []
    for name in names:
        r = Area(root, name).file("BOARD.md")
        for it in board_items(r[1] if r else ""):
            if it["due"] and not it["empty"]:
                out.append((it["due"], it["approx"], name, it))
    return sorted(out, key=lambda x: (x[0], x[2]))


def thread_and_waiting(board):
    thread = section(board, "Thread")
    text = clean(thread[0][2:]) if thread else ""
    thread = "" if not text or text.lower().startswith("none") else short(text)
    waiting = [it for it in board_items(board) if it["section"] == "Waiting on" and not it["empty"]]
    return thread, waiting


def block(title, lines, total):
    rest = total - len(lines)
    return "\n".join([title] + [f"- {l}" for l in lines] + ([f"- and {rest} more"] if rest > 0 else []))


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


def opening(root, area, extra=()):
    """The assistant's first reply, ready to show, computed now (local mode).

    `extra`: ready blocks from other sources (lookup.py), placed after the due dates."""
    today = local_today()
    _, board = area.file("BOARD.md") or ({}, "")
    thread, waiting = thread_and_waiting(board)
    mine = due_items(root, [area.name])
    overdue = [p for p in mine if p[0] < today]
    upcoming = [p for p in mine if p[0] >= today]
    week = [p for p in upcoming if (p[0] - today).days < 7] or upcoming[:1]
    blocks = [f"**{area_title(area.name)}** · {thread or 'no thread in progress'}"]
    if overdue:
        lines = [f"{short_date(d, today, a)} · {short(it['text'])}" for d, a, _, it in overdue[:BLOCK_ITEMS]]
        blocks.append(block("**Overdue** (done, postpone or drop?)", lines, len(overdue)))
    if week:
        lines = [f"{short_date(d, today, a)} · {short(it['text'])}" for d, a, _, it in week[:BLOCK_ITEMS]]
        title = "**Next due**" if len(week) == 1 else "**Next due dates**"
        blocks.append(block(title, lines, len(week)))
    blocks += list(extra)
    if waiting:
        blocks.append(block(f"**Waiting on you** ({len(waiting)})", [short(waiting[0]["text"])], 1))
    limit = today + dt.timedelta(days=DAYS_OTHER_AREAS)
    others = [p for p in due_items(root, [n for n in areas(root) if n != area.name]) if p[0] <= limit]
    summary = []
    for n in sorted({p[2] for p in others}):
        late = [p for p in others if p[2] == n and p[0] < today]
        soon = [p for p in others if p[2] == n and p[0] >= today]
        parts = [f"{len(late)} overdue"] if late else []
        if soon:
            parts.append(f"1 due {short_date(soon[0][0], today, soon[0][1])}" if len(soon) == 1
                         else f"{len(soon)} due by {short_date(soon[-1][0], today, soon[-1][1])}")
        summary.append(f"{area_title(n)}, {' and '.join(parts)}")
    if summary:
        blocks.append(f"**From other areas:** {'; '.join(summary)}")
    reasons = sleep_reasons(root, area, inbox_min=INBOX_MAX + 1)
    notes = []
    repo = Path(__file__).resolve().parent.parent  # hooks only in the copy of whoever set them; no repository in chat
    cwd = Path.cwd().resolve()
    if (repo / ".claude" / "settings.json").exists() and repo not in (cwd, *cwd.parents):
        notes.append(f"protection hooks off (session outside {str(repo).replace(str(Path.home()), '~')})")
    if reasons:
        notes.append(f"worth running /sleep ({'; '.join(reasons)})")
    st = area.file("STATE.md")
    if st and series(st[0].get("system_version", "")) > series(VERSION):
        notes.append(f"memory at version {st[0]['system_version']}, newer than this system ({VERSION}): "
                     "update the repository (git pull) or reinstall the skill")
    if notes:
        blocks.append(f"**Heads-up:** {'. '.join(n[:1].upper() + n[1:] for n in notes)}.")
    blocks.append("Which topic?")
    core = Area(root, "core").inbox
    agent = [AGENT_SEPARATOR,
             f"Inbox: {len(area.inbox)} capture(s) from the area and {len(core)} from core not yet consolidated."]
    agent += [f"- inbox/{f.parent.name}/{f.name}" for f in core + area.inbox]
    return "\n\n".join(blocks) + "\n\n" + "\n".join(agent)


def owed(area, others=()):
    """What the owner owes per the board: items with `for` (people), their loose ends, and how many wait on them.

    An item whose label ("Name: ...") is a known other person is not the owner's: `others` (the area's GitHub
    `Names`) or someone in core/people. Any other label is often the topic, so the item stays: hiding one of
    the owner's to-dos is worse than showing someone else's."""
    known = {fold(n) for n in others} | {fold(m.get("title", "")) for _, m, _ in Area(area.root, "core").records.values()}
    known -= {"", fold(NAME)}
    _, board = area.file("BOARD.md") or ({}, "")
    people, todos, waiting = [], [], 0
    for it in board_items(board):
        if it["empty"]:
            continue
        owner = re.match(r"^\**([^:*]{1,40})\**:\s", it["text"])
        if owner and fold(owner.group(1)) in known:
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
    thread, waiting = thread_and_waiting(board)
    out = ["---", "type: state", f"area: {area.name}", f"generated: {now()}",
           f"system_version: {VERSION}", "---",
           f"# State of area {area.name} (generated by sleep; do not edit)", "",
           f"## Opening (overdue = due before today; computed on {today})",
           f"- Thread: {thread or 'no thread in progress'}",
           f"- Waiting on you ({len(waiting)}): {short(waiting[0]['text']) if waiting else 'none'}", "- Due dates:"]
    out += [f"  - {'~' if a else ''}{d} · {short(it['text'])}" for d, a, _, it in due_items(root, [area.name])] or ["  - none"]
    out += ["", "## Board", re.sub(r"^(#+) ", r"#\1 ", without_log(board).strip(), flags=re.M), ""]
    recs = area.records
    active = [(s, m) for s, (_, m, _) in recs.items() if m.get("type") == "initiative" and m.get("status") == "active"]
    order = {"high": 0, "medium": 1, "low": 2, "tbd": 3}
    active.sort(key=lambda x: (order.get(x[1].get("priority"), 9), x[0]))
    out.append("## Active initiatives (slug | priority | owner | verified | next)")
    out += [initiative_line(s, m, today) for s, m in active] or ["- none"]
    open_ = [(s, m) for s, (_, m, _) in recs.items() if m.get("type") == "decision"
             and (m.get("status") == "proposed" or m.get("confirmed") == "inherited")]
    out += ["", "## Proposed or unconfirmed decisions"]
    out += [f"- [[{s}]] | {m.get('status')} | confirmed: {m.get('confirmed')} | {m.get('title', '')}"
            for s, m in sorted(open_)] or ["- none"]
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
    waiting, status = [], []
    for name in areas(root):
        a = Area(root, name)
        r = a.file("BOARD.md")
        for it in board_items(r[1] if r else ""):
            if it["section"] == "Waiting on" and not it["empty"]:
                since = f" (since {it['since']})" if it["since"] else ""
                waiting.append(f"- [{name}] {it['text']}{since}")
        st = a.file("STATE.md")
        generated = st[0].get("generated", "never") if st else "never"
        status.append(f"- {name}: state generated {generated}; inbox with {len(a.inbox)} capture(s)")
    core = Area(root, "core")
    status.append(f"- core: inbox with {len(core.inbox)} capture(s)")
    out += [f"## Due dates, all areas (by date; overdue = before today; computed on {today})"]
    out += [f"- {'~' if ap else ''}{d} [{n}] {it['text']}" for d, ap, n, it in due_items(root, areas(root))] or ["- none"]
    out += ["", f"## Waiting on {NAME}, all areas"] + (waiting or ["- none"])
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
    if lit.startswith(CURRENCIES + ("http",)):
        return re.sub(r"\s", "", lit).rstrip(".,;") in compact
    if re.fullmatch(r"\d{2}/\d{2}(/\d{2,4})?", lit):
        a, b = lit.split("/")[:2]  # dd/mm or mm/dd
        return lit in corpus or re.search(rf"\d{{4}}-({b}-{a}|{a}-{b})\b", corpus) is not None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", lit):
        return lit in corpus
    number = re.findall(r"\d+", lit)[-1]
    return re.search(rf"\b{number}\b", corpus) is not None


def fidelity(root, area, names):
    """Literals of each capture missing from the curated memory of the area and of core.

    An argument that is not an inbox capture is the before-copy of a split topic: each of its lines must be in the memory."""
    files = [f for f, _, _ in area.records.values()] + [f for f, _, _ in Area(root, "core").records.values()]
    files += [area.folder / n for n in ("BOARD.md", "LOG.md", "AREA.md")]
    files += [root / "core" / n for n in ("PREFERENCES.md", "PROFILE.md", "PRINCIPLES.md")]
    corpus = "\n".join(text_of(f) for f in files if f.exists())
    compact = re.sub(r"\s", "", corpus)
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
    cmd, root = argv[1], Path(argv[2]).expanduser()
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
    if cmd in ("state", "opening", "index", "context", "fidelity") and len(argv) < (5 if cmd == "context" else 4):
        print(__doc__)
        return 2
    if cmd in WITH_AREA and len(argv) > 3 and not argv[3].startswith("--") and not (cmd == "validate" and argv[3] == "all"):
        argv[3] = area_from_argument(root, argv[3])
    if cmd in ("state", "opening") and argv[3] == "core":
        print(f"{cmd} is per area; core/STATE.md comes from: memory.py core <root> --write")
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
    if cmd == "index":
        index(Area(root, argv[3]))
        return 0
    if cmd == "context":
        return context(root, Area(root, argv[3]), argv[4])
    if cmd == "fidelity":
        return fidelity(root, Area(root, argv[3]), set(argv[4:]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
