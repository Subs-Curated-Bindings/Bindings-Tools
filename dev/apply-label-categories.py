"""
Append a category to each quoted friendly-label in a JG profile, inside the
quotes, in the form  "Friendly Label | Category"  (Sub, 2026-05-30).

The category drives the chart color. Categories are Sub's 9 chart-footer
buckets (Combat, Flight Control, Turret, Power, Mining, Salvage, Camera,
Miscellaneous, Unbound).

Reads a JSON map {friendly-label-text: category}. For every library action
whose action-label's FIRST quoted substring matches a key, rewrites that quote
to "<label> | <category>" and leaves the rest of the value untouched. Idempotent:
skips a label that already contains " | ". Preserves BOM + line endings.

Usage:
  py tools/apply-label-categories.py "<profile.xml>" "<categories.json>" [--dry-run]
"""
import json, re, sys
import xml.etree.ElementTree as ET

QUOTE = re.compile(r'"([^"]*)"')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    profile, mapfile = args[0], args[1]
    cats = json.load(open(mapfile, encoding="utf-8"))

    with open(profile, "rb") as f:
        raw = f.read()
    has_bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")

    # Walk action-label <value> blocks
    label_pat = re.compile(
        r'(<property type="string">\s*<name>action-label</name>\s*<value>)([^<]*)(</value>)'
    )

    changed = 0
    unmatched = []

    def repl(m):
        nonlocal changed
        head, val, tail = m.group(1), m.group(2), m.group(3)
        q = QUOTE.search(val)
        if not q:
            return m.group(0)
        label = q.group(1).strip()
        if " | " in label:  # already categorized
            return m.group(0)
        cat = cats.get(label)
        if cat is None:
            if label and not label.startswith("Map to") and label != "Description":
                unmatched.append(label)
            return m.group(0)
        new_quote = f'"{label} | {cat}"'
        new_val = val[:q.start()] + new_quote + val[q.end():]
        changed += 1
        print(f'  + {label}  ->  {label} | {cat}')
        return head + new_val + tail

    new_text = label_pat.sub(repl, text)

    if unmatched:
        print("\nUNMATCHED quoted labels (no category in map):")
        for u in sorted(set(unmatched)):
            print(f"    {u}")

    if dry:
        print(f"\n(dry-run) Would categorize {changed} labels.")
        return

    out = new_text.encode("utf-8")
    if has_bom and not out.startswith(b"\xef\xbb\xbf"):
        out = b"\xef\xbb\xbf" + out
    with open(profile, "wb") as f:
        f.write(out)
    ET.parse(profile)
    print(f"\nCategorized {changed} labels. XML parses OK.")


if __name__ == "__main__":
    main()
