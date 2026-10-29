#!/usr/bin/env python3
"""hippOS guard: a Claude Code PreToolUse hook that enforces the protections of each area. Python 3.8+, no dependencies.

The protections are three lines of the `## Limits` section of each AREA.md, items in backticks:

  - Never run: `infra/deploy`, `docker compose down`    shell commands that contain one are blocked
  - Never open: `beta*.example.com`                     addresses: browser, WebFetch and shell commands
  - Read only: `~/code/app`                             folders the editing tools can't write to

A pattern matches anywhere, ignoring case and repeated spaces; `*` stands for anything. A read-only folder
blocks Edit, Write, MultiEdit and NotebookEdit inside it; a shell command that writes there needs its own
`Never run` pattern. Every area's protections apply to every call: the hook can't tell which area is open.

  (hook)                 reads the tool call as JSON on stdin; exit 2 blocks it, with the reason on stderr
  show [root]            the protections of every area
  test [root] <text>     what happens to <text> as a shell command, an address and a file to edit
  install                turns the guard on for sessions opened in this repository (.claude/settings.local.json,
                         which is not versioned)
  uninstall              turns it off

The root is the one `memory.py root` finds (HIPPOS_ROOT pins another). Without a root, or on a call it can't
read, the guard lets the call through: it never locks a session.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memory as m  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SETTINGS = REPO / ".claude" / "settings.local.json"
COMMAND = f'python3 "{Path(__file__).resolve()}"'
MATCHER = "Bash|WebFetch|Edit|Write|MultiEdit|NotebookEdit|mcp__.*(navigate|open_url|preview_start|browser_batch)"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
LABEL = {kind: label for label, kind in m.LIMIT_LISTS.items()}


def pattern(item):
    """A list item as a regex: any case, any run of spaces, `*` for anything."""
    text = ".*".join(re.escape(part) for part in item.split("*"))
    return re.compile(re.sub(r"(?:\\\s|\s)+", r"\\s+", text), re.I)


def urls(value):
    """Every `url` inside a tool input (a browser batch carries one per action)."""
    if isinstance(value, dict):
        for key, v in value.items():
            if key == "url" and isinstance(v, str):
                yield v
            else:
                yield from urls(v)
    elif isinstance(value, list):
        for v in value:
            yield from urls(v)


def inside(path, folder):
    try:
        Path(path).expanduser().resolve().relative_to(Path(folder).expanduser().resolve())
        return True
    except ValueError:
        return False


def verdict(found, tool, tool_input):
    """(area, kind, item) of the first protection the call breaks, or None."""
    if tool == "Bash":
        command = " ".join(str(tool_input.get("command", "")).split())
        for kind in ("run", "open"):
            for area, item in found[kind]:
                if pattern(item).search(command):
                    return area, kind, item
    elif tool in EDIT_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        for area, item in found["read_only"]:
            if path and inside(path, item):
                return area, "read_only", item
    else:
        addresses = list(urls(tool_input))
        for area, item in found["open"]:
            if any(pattern(item).search(a) for a in addresses):
                return area, "open", item
    return None


def root_from(args):
    """The root given as the first argument, or the one memory.py finds; None without one."""
    if args and Path(args[0]).expanduser().is_dir():
        return Path(args[0]).expanduser(), args[1:]
    found = m.find_roots()
    return (found[0] if found else None), args


def hook():
    try:
        call = json.loads(sys.stdin.read() or "{}")
        root = root_from([])[0]
        if root is None:
            return 0
        m.configure(root)
        broken = verdict(m.limits(root), call.get("tool_name", ""), call.get("tool_input") or {})
    except Exception as e:  # never lock a session over the guard itself
        print(f"hippOS guard skipped: {e}", file=sys.stderr)
        return 0
    if broken:
        area, kind, item = broken
        print(f"Blocked by hippOS: `{item}` is under \"{LABEL[kind]}\" in the {area} area (AREA.md, ## Limits). "
              f"If it is really needed, ask {m.NAME} to do it in their own terminal.", file=sys.stderr)
        return 2
    return 0


def show(args):
    root, _ = root_from(args)
    if root is None:
        print("no hippOS root found (HIPPOS_ROOT unset, no Google Drive for desktop)")
        return 1
    found = m.limits(root)
    for kind, label in LABEL.items():
        print(f"{label}:")
        print("\n".join(f"  {item}  ({area})" for area, item in found[kind]) or "  none")
    print(f"guard {'on' if installed() else 'off'} for sessions opened in {REPO}")
    return 0


def test(args):
    root, rest = root_from(args)
    if root is None or not rest:
        print(__doc__)
        return 2
    found, text = m.limits(root), " ".join(rest)
    for tool, tool_input, what in (("Bash", {"command": text}, "as a shell command"),
                                   ("WebFetch", {"url": text}, "as an address"),
                                   ("Edit", {"file_path": text}, "as a file to edit")):
        broken = verdict(found, tool, tool_input)
        print(f"{what}: " + (f"blocked by `{broken[2]}` ({LABEL[broken[1]]}, {broken[0]})" if broken else "allowed"))
    return 0


def settings():
    return json.loads(m.text_of(SETTINGS)) if SETTINGS.exists() else {}


def installed():
    return any(h.get("command") == COMMAND for e in settings().get("hooks", {}).get("PreToolUse", [])
               for h in e.get("hooks", []))


def install():
    if installed():
        print(f"guard already on for sessions opened in {REPO}")
        return 0
    current = settings()
    current.setdefault("hooks", {}).setdefault("PreToolUse", []).append(
        {"matcher": MATCHER, "hooks": [{"type": "command", "command": COMMAND, "timeout": 10}]})
    SETTINGS.parent.mkdir(exist_ok=True)
    SETTINGS.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"guard on for sessions opened in {REPO} ({SETTINGS.name}, not versioned)")
    return 0


def uninstall():
    current = settings()
    entries = current.get("hooks", {}).get("PreToolUse", [])
    kept = [e for e in entries if not any(h.get("command") == COMMAND for h in e.get("hooks", []))]
    if len(kept) == len(entries):
        print("guard was not on")
        return 0
    current["hooks"]["PreToolUse"] = kept
    SETTINGS.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"guard off for sessions opened in {REPO}")
    return 0


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) == 1:
        if sys.stdin.isatty():  # run by hand, not by Claude Code
            print(__doc__)
            return 2
        return hook()
    cmd, args = argv[1], argv[2:]
    if cmd == "show":
        return show(args)
    if cmd == "test":
        return test(args)
    if cmd == "install":
        return install()
    if cmd == "uninstall":
        return uninstall()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
