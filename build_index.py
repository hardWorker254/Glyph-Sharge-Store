#!/usr/bin/env python3
"""Builds ``index.json`` from the scripts in ``animations/``.

**The index is generated, never hand-written.** It exists so the app has one
small file to fetch and something to check a script's hash against — and the
moment a person can edit it, the catalogue and its files can disagree about
what an animation is, which is the one failure this layout exists to make
impossible.

``devices`` is read out of each script's own header rather than typed in here,
so the two copies of that fact are one fact.

    python3 build_index.py            # write index.json
    python3 build_index.py --check    # fail if it is out of date (for CI)

Only the standard library. A catalogue gets built on whatever machine a
contributor happens to have, and a tool that needs a package installed is a
tool that will not be run.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

# The directory holding the scripts, relative to this file's repository root.
ANIMATIONS_DIR = "animations"
INDEX_PATH = "index.json"
INDEX_FORMAT = 1

#: Models the app can be asked about. Mirrors ``DeviceType`` in the app.
KNOWN_DEVICES = ("PHONE1", "PHONE2", "PHONE2A", "PHONE3A")

#: Where the app fetches scripts from. Must match the ``url`` the phone
#: resolves, and the path is case-sensitive: a wrong case here produces an
#: index full of dead links rather than an obvious failure — the catalogue
#: loads, every card renders, and every install ends in a hash error nobody
#: can explain.
CDN_BASE = (
    "https://raw.githubusercontent.com/hardWorker254/Glyph-Sharge-Store"
    "/refs/heads/main"
)

#: ``.glyphlua`` — plain Lua, no container to unwrap.
SUFFIX = ".glyphlua"

#: An id the app will actually keep. Anything else is silently replaced on
#: import, so catching it here turns a confusing bug into a failed build.
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

_SPLIT_DEVICES = re.compile(r"[,;]")


def read_field(header: str, key: str) -> str:
    """The value of ``-- key: value`` in *header*, or ``""``.

    The key is matched case-insensitively and the value is everything after the
    *first* colon, which is what the app's own reader does — so a description
    containing a colon survives the round trip instead of being cut in half.
    """
    match = re.search(rf"^--\s*{re.escape(key)}\s*:\s*(.+)$", header, re.MULTILINE | re.I)
    return match.group(1).strip() if match else ""


def header_of(source: str) -> str:
    """The header block: the run of ``--`` lines at the top.

    The first line that is not a comment ends it. Same rule the app uses, so a
    script written for the app reads the same way here — including a commented
    line *inside* the body, which is not header and is not read as one.
    """
    lines = []
    for line in source.splitlines():
        if not line.lstrip().startswith("--"):
            break
        lines.append(line)
    return "\n".join(lines)


def body_of(source: str) -> str:
    """The Lua below the header.

    The app refuses a file with no body, so a header-only file is not an
    animation and does not belong in a catalogue.
    """
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("--"):
            return "\n".join(lines[index:]).strip("\n")
    return ""


def parse_devices(raw: str) -> list[str]:
    """Models named in a ``devices:`` field.

    Unrecognised names are dropped, and **an empty result means every model** —
    for the same reason the app treats it that way in a header: ``PHONE4`` from
    a future release is an honest claim rather than a mistake, and refusing the
    entry over it would leave that animation uninstallable anywhere. An omitted
    field is the same statement, made less clearly.
    """
    named = [
        part.strip().upper()
        for part in _SPLIT_DEVICES.split(raw or "")
        if part.strip()
    ]
    known = [device for device in named if device in KNOWN_DEVICES]
    return known or list(KNOWN_DEVICES)


def read_animation(path: Path) -> dict:
    """One catalogue entry, or a reason it cannot become one."""
    raw_bytes = path.read_bytes()
    text = raw_bytes.decode("utf-8")
    header = header_of(text)

    if not body_of(text).strip():
        return {"error": "no Lua below the header"}

    # Order is declaration order, not set order: two runs over one set of models
    # must produce byte-identical JSON, or `--check` fails over a file nobody
    # touched.
    devices = parse_devices(read_field(header, "devices"))

    animation_id = read_field(header, "id") or path.stem
    name = read_field(header, "name") or animation_id
    author = read_field(header, "author")
    license_ = read_field(header, "license")

    # The fields an install cannot do without, plus the two that are about
    # rights rather than code. An entry missing one is refused here rather than
    # shipped and dropped on the phone.
    problems = []
    if not ID_PATTERN.match(animation_id):
        problems.append(
            f"id '{animation_id}' is not [a-zA-Z0-9_-] — "
            "the app would replace it on import"
        )
    if not author:
        problems.append("no author")
    if not license_:
        problems.append("no license")

    if problems:
        return {"error": "; ".join(problems)}

    try:
        version = int(read_field(header, "version") or "1")
    except ValueError:
        version = 1

    try:
        updated = int(read_field(header, "updated") or "0")
    except ValueError:
        updated = 0

    return {
        "id": animation_id,
        "name": name,
        "author": author,
        "license": license_,
        "description": read_field(header, "description"),
        "version": version,
        "devices": devices,
        "url": f"{CDN_BASE}/{ANIMATIONS_DIR}/{path.name}",
        # Over the bytes on disk, which is what the phone will download. Not
        # over the decoded text: a newline-normalising read would produce a
        # hash no fetch could ever match.
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "_updated": updated,
    }


def build(root: Path) -> tuple[dict, int]:
    """The whole index, and how many scripts had to be refused."""
    animations = root / ANIMATIONS_DIR
    if not animations.is_dir():
        raise SystemExit(
            f"no {ANIMATIONS_DIR}/ directory — run this from the repository root"
        )

    entries = []
    refused = 0

    # Sorted by file name, so the walk order cannot vary between machines.
    for path in sorted(animations.glob(f"*{SUFFIX}")):
        entry = read_animation(path)
        if "error" in entry:
            print(f"✗ {path.name}: {entry['error']}", file=sys.stderr)
            refused += 1
            continue
        entries.append(entry)

    # Sorted by id, so re-sorting the directory does not produce a diff in the
    # one file every phone downloads.
    entries.sort(key=lambda item: item["id"])

    newest = max([entry.pop("_updated", 0) for entry in entries] or [0])

    return (
        {"format": INDEX_FORMAT, "updated": newest, "items": entries},
        refused,
    )


def render(index: dict) -> str:
    """The file exactly as it is written, so ``--check`` can compare text.

    ``sort_keys`` is off on purpose — the key order below is the order a reader
    wants, and it is stable across runs.
    """
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent
    check_only = "--check" in argv

    index, refused = build(root)
    text = render(index)

    if check_only:
        try:
            committed = (root / INDEX_PATH).read_text(encoding="utf-8")
        except FileNotFoundError:
            print(
                f"✗ {INDEX_PATH} does not exist. Run without --check to build it.",
                file=sys.stderr,
            )
            return 1

        if committed != text:
            print(
                f"✗ {INDEX_PATH} is out of date with {ANIMATIONS_DIR}/.\n"
                "  Run `python3 build_index.py` and commit the result.",
                file=sys.stderr,
            )
            return 1

        print(f"✓ {INDEX_PATH} matches {len(index['items'])} script(s)")
        return 1 if refused else 0

    (root / INDEX_PATH).write_text(text, encoding="utf-8")
    print(f"✓ wrote {INDEX_PATH} with {len(index['items'])} item(s)")
    if refused:
        print(f"  {refused} script(s) were refused — see above.", file=sys.stderr)
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
