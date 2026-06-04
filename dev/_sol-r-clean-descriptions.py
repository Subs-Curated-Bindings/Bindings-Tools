#!/usr/bin/env python3
"""SOL-R description cleanup — clear orphaned ' — ' fragments to bare text.

After Sub cut the etched-name prefixes out of the SCM descriptions (moving the
moniker onto the action-label), the descriptions were left with orphans:
  ' — v_retract_landing_system'           (leading space + em-dash)
  '[Modifier] — Analog hat Y (...)'        (mode-tag + dash, name gone)
This strips the leading whitespace + em-dash (and a leading [Mode] tag if the
etched-name in front of it is gone) so the value is just the bare action text.

Only touches descriptions that are actually orphaned — descriptions with a real
etched-name in front of the dash (e.g. 'L-ENCODER.up — ...') are left alone.

Dry-run by default; pass --apply to write. Preserves line endings (newline="").
"""
import re, sys
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"

# orphan = value starts with optional ws then an em-dash, OR a leading [Mode] tag
# directly followed by an em-dash (etched-name that used to precede it is gone).
ORPHAN_DASH = re.compile(r"^\s*—\s*")
ORPHAN_MODETAG = re.compile(r"^\s*\[[^\]]+\]\s*—\s*")
VALUE = re.compile(r"(<value>)(.*?)(</value>)", re.S)


def clean(v):
    new = ORPHAN_MODETAG.sub("", v)
    if new == v:
        new = ORPHAN_DASH.sub("", v)
    return new.strip() if new != v else v


def main():
    apply = "--apply" in sys.argv
    text = JG.read_text(encoding="utf-8", newline="")
    changes = []

    def repl(m):
        pre, val, post = m.groups()
        nv = clean(val)
        if nv != val:
            changes.append((val, nv))
            return pre + nv + post
        return m.group(0)

    new_text = VALUE.sub(repl, text)

    print(f"{len(changes)} orphaned description(s) to clean:\n")
    for old, nv in changes:
        print(f"  - {old[:88]}")
        print(f"  + {nv[:88]}\n")

    if apply and changes:
        with open(JG, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        print("APPLIED.")
    elif not apply:
        print("(dry-run — pass --apply to write)")


if __name__ == "__main__":
    main()
