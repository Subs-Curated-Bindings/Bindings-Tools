#!/usr/bin/env python3
"""Slim JG profile <action type="description"> values down to the moniker only.

Reduces e.g. "L-A4.down — [H] Look Behind" to "L-A4.down" — the etched
chart-cluster ID that tools/extract-physical-control-map.py needs (it reads
split('—')[0]), dropping the friendly text + [H]/[DT] markers that drift and
that the website generator no longer reads (it derives markers from the JG
tempo/activationMode structure and friendly labels from quoted action-labels).

Safety:
  - Only the <value> of <action type="description"> properties is touched.
  - A value is slimmed ONLY if its head (before the em-dash, minus any trailing
    [tag]/(tag)) matches a moniker shape; anything else is left verbatim.
  - Preserves the file's UTF-8 BOM + LF line endings (newline='' + utf-8).

Usage:
  py tools/_nxt-slim-descriptions.py "<profile.xml>" [--dry-run]
"""
import argparse
import re

MONIKER = re.compile(r'^[A-Z0-9]+(?:-[A-Z0-9]+)*(?:\.[a-z0-9-]+)*$')
DESC = re.compile(r'(<name>description</name>\s*<value>)(.*?)(</value>)', re.S)


def moniker_of(val):
    head = val.split("—", 1)[0].strip()
    head = re.sub(r"\s*\[[^\]]*\]\s*$", "", head).strip()
    head = re.sub(r"\s*\([^)]*\)\s*$", "", head).strip()
    return head


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.profile, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    changed, skipped, already = [], [], 0

    def repl(m):
        nonlocal already
        orig = m.group(2)
        head = moniker_of(orig)
        if not (head and MONIKER.match(head)):
            skipped.append(orig)
            return m.group(0)
        if head == orig:
            already += 1
            return m.group(0)
        changed.append((orig, head))
        return m.group(1) + head + m.group(3)

    new = DESC.sub(repl, text)
    print(f"slimmed: {len(changed)}   already-bare: {already}   "
          f"left unchanged (non-moniker): {len(skipped)}")
    for o in skipped:
        print(f"  SKIP: {o!r}")
    if args.dry_run:
        for o, h in changed:
            print(f"  {o!r} -> {h!r}")
        return
    with open(args.profile, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    print(f"written ({len(new.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
