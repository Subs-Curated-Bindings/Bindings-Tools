"""
Reorder a JG R14 profile's <library> so every action is defined before any
action that references it (forward refs eliminated).

Why: when you add an action through JG R14's editor, it gets appended at the
end of <library>. If the action is referenced by an earlier action (a root,
tempo, etc.), that's a forward reference. The skill's `references/converter.md`
flags this as risky; in practice JG R14.2 tolerates it, but the safe state is
zero forward refs.

Approach: build a dependency graph from <action-id> children inside each
action, then topologically sort the library so dependencies always come
first. Preserves exact whitespace/indent of action blocks (block-based move,
no XML re-serialization). Preserves UTF-8 BOM and line-ending style.

Usage:
  python fix-library-order.py "<profile.xml>"            # apply
  python fix-library-order.py "<profile.xml>" --dry-run  # report only
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET


def collect_refs(action_el):
    """Return the set of action-ids that this action references."""
    refs = set()
    # <actions><action-id>...</action-id></actions>  -- root, condition, chain
    for aid in action_el.findall(".//action-id"):
        if aid.text:
            refs.add(aid.text.strip())
    # Tempo: <short-action> / <long-action>
    for tag in ("short-action", "long-action"):
        for el in action_el.findall(f".//{tag}"):
            if el.text:
                refs.add(el.text.strip())
    # Smart-toggle, double-tap, hat-buttons: <action-id> children already covered above
    return refs


def topo_order(library_actions):
    """Return a topologically-sorted list of action ids.
    Dependencies come first. Stable: preserves original order among siblings."""
    id_to_action = {a.get("id"): a for a in library_actions}
    deps = {a.get("id"): collect_refs(a) & set(id_to_action) for a in library_actions}
    original_order = {a.get("id"): i for i, a in enumerate(library_actions)}

    emitted = []
    remaining = set(id_to_action.keys())
    while remaining:
        ready = sorted(
            (aid for aid in remaining if not (deps[aid] - set(emitted))),
            key=lambda x: original_order[x],
        )
        if not ready:
            print("ERROR: dependency cycle detected. Remaining:", remaining, file=sys.stderr)
            return None
        for aid in ready:
            emitted.append(aid)
            remaining.discard(aid)
    return emitted


def apply(profile_path, dry_run=False):
    tree = ET.parse(profile_path)
    root_el = tree.getroot()
    library = root_el.find("library")
    actions = library.findall("action")
    original_ids = [a.get("id") for a in actions]
    target_order = topo_order(actions)
    if target_order is None:
        return 1

    # Detect forward refs in the original order
    pos = {aid: i for i, aid in enumerate(original_ids)}
    id_to_action = {a.get("id"): a for a in actions}
    fwd = []
    for a in actions:
        parent_idx = pos[a.get("id")]
        for child_id in collect_refs(a):
            if child_id in pos and pos[child_id] > parent_idx:
                fwd.append((a.get("id")[:8], child_id[:8]))

    if not fwd:
        print("No forward references. Library order is already correct.")
        return 0

    print(f"Found {len(fwd)} forward reference(s):")
    for p, c in fwd:
        print(f"  {p} -> {c}")

    if target_order == original_ids:
        print("(unexpected: forward refs detected but topo order matches original)")
        return 1

    if dry_run:
        print(f"\n(dry-run) Would reorder {len(target_order)} library actions to eliminate all forward refs.")
        return 0

    # --- Apply: rewrite library by moving action blocks in-place. ---
    with open(profile_path, "rb") as f:
        raw = f.read()
    has_bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in text[:4096] else "\n"

    # Identify the library content range.
    lib_open_match = re.search(r"(    <library>\r?\n)", text)
    lib_close_match = re.search(r"(    </library>)", text)
    if not lib_open_match or not lib_close_match:
        print("ERROR: could not locate <library>...</library> bounds", file=sys.stderr)
        return 1
    body_start = lib_open_match.end()
    body_end = lib_close_match.start()  # points at start of '    </library>' line, so body includes last action's trailing newline
    library_body = text[body_start:body_end]

    # Slice every action block out by id. Each block starts at 8-space indent.
    block_pat = re.compile(
        r'        <action id="([^"]+)" type="[^"]+">.*?\r?\n        </action>\r?\n',
        re.DOTALL,
    )
    blocks = {}
    for m in block_pat.finditer(library_body):
        blocks[m.group(1)] = m.group(0)

    if set(blocks.keys()) != set(original_ids):
        missing = set(original_ids) - set(blocks.keys())
        extra = set(blocks.keys()) - set(original_ids)
        print(f"ERROR: block extraction mismatch. missing={missing}, extra={extra}", file=sys.stderr)
        return 1

    new_body = "".join(blocks[aid] for aid in target_order)
    new_text = text[:body_start] + new_body + text[body_end:]

    out = new_text.encode("utf-8")
    if has_bom and not out.startswith(b"\xef\xbb\xbf"):
        out = b"\xef\xbb\xbf" + out
    with open(profile_path, "wb") as f:
        f.write(out)

    ET.parse(profile_path)
    print(f"\nReordered {len(target_order)} actions. XML parses OK.")
    return 0


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("profile", help="Path to the JG R14 profile XML")
    p.add_argument("--dry-run", action="store_true", help="Report only; do not modify")
    args = p.parse_args()
    sys.exit(apply(args.profile, args.dry_run))


if __name__ == "__main__":
    main()
