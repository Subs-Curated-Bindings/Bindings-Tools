"""
One-off: in axis roots that have description as the FIRST child, move the
description to position 1 (after the response-curve). This satisfies both
the audit heuristic and the skill's response-curve-precedes-map-to-vjoy rule.

Reads/writes the JG profile in place, preserving LF line endings.
"""
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

JG_XML = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT\Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml"


def main():
    tree = ET.parse(JG_XML)
    root_el = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root_el.findall("./library/action")}

    # Find axis roots with [description, response-curve, ...] order — collect
    # (root_id, desc_id) pairs that need swapping.
    swaps = []
    for a in root_el.findall("./library/action"):
        if a.attrib.get("type") != "root":
            continue
        actions_el = a.find("actions")
        if actions_el is None:
            continue
        children = [c.text for c in actions_el.findall("action-id") if c.text]
        if len(children) < 2:
            continue
        first_type = by_id.get(children[0], {}).attrib.get("type") if children[0] in by_id else None
        second_type = by_id.get(children[1], {}).attrib.get("type") if children[1] in by_id else None
        if first_type == "description" and second_type == "response-curve":
            swaps.append((a.attrib["id"], children[0]))

    print(f"Found {len(swaps)} axis roots to fix")

    # Read raw text for in-place edit
    with open(JG_XML, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    for root_id, desc_id in swaps:
        # Match the root's <actions> block and swap the first two <action-id> lines
        # Pattern locates the root, then captures the first two action-id refs.
        block_pat = re.compile(
            r'(<action id="' + re.escape(root_id) + r'" type="root">\s*<actions>)'
            r'(\s*<action-id>' + re.escape(desc_id) + r'</action-id>)'
            r'(\s*<action-id>[^<]+</action-id>)',
            re.DOTALL,
        )
        m = block_pat.search(text)
        if not m:
            print(f"  ! could not locate swap target for root {root_id[:8]}..")
            continue
        # Swap groups 2 and 3
        text = text[:m.start()] + m.group(1) + m.group(3) + m.group(2) + text[m.end():]
        print(f"  swapped root {root_id[:8]}.. desc {desc_id[:8]}..")

    # Validate
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        print(f"ERROR: XML parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    with open(JG_XML, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print(f"\nDone. {len(swaps)} axis roots fixed.")


if __name__ == "__main__":
    main()
