"""
Third pass: fill in the last 4 missing chart-side descriptions found by the
three-way audit:

  1. L btn 7 Modifier (chart: L-A3.right [M] Shields Power Toggle)
  2. L btn 28 SCM Mode (chart: L-F2 — VTOL Cycle, virtual placeholder slot)
  3. L axis 3 SCM Mode — UPDATE generic axis label to L-T1 throttle reference
  4. R axis 3 SCM Mode — UPDATE generic axis label to R-T1 (unbound) reference

Uses text-based edit with LF preserved.
"""
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

JG_XML = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT\Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml"

LEFT_DEV = "7d12d5c0-43ea-11f0-800a-444553540000"
RIGHT_DEV = "ec8bbeb0-4009-11f0-8002-444553540000"

# (device, input-type, input-id, mode) -> description text to ADD
ADDS = [
    ((LEFT_DEV, "button", "7", "Modifier"),
     "L-A3.right [Modifier] — Shields Power Toggle"),
    ((LEFT_DEV, "button", "28", "SCM Mode"),
     "L-F2 — VTOL Cycle (virtual placeholder; actual VTOL fires via btn 125/128 macros)"),
]

# (device, input-type, input-id, mode) -> NEW description text (replaces existing)
UPDATES = [
    ((LEFT_DEV, "axis", "3", "SCM Mode"),
     "L-T1 throttle wheel — Mining Throttle / Salvage Beam Spacing (vjoy 1 Rz)"),
    ((RIGHT_DEV, "axis", "3", "SCM Mode"),
     "R-T1 throttle wheel — Axis Unbound (vjoy 2 Rz)"),
]


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_description_action_text(action_id, description_text, indent="        "):
    body_indent = indent + "    "
    inner_indent = body_indent + "    "
    esc = xml_escape(description_text)
    return (
        f'{indent}<action id="{action_id}" type="description">\n'
        f'{body_indent}<property type="string">\n'
        f'{inner_indent}<name>description</name>\n'
        f'{inner_indent}<value>{esc}</value>\n'
        f'{body_indent}</property>\n'
        f'{body_indent}<property type="string">\n'
        f'{inner_indent}<name>action-label</name>\n'
        f'{inner_indent}<value>Description</value>\n'
        f'{body_indent}</property>\n'
        f'{body_indent}<property type="activation-mode">\n'
        f'{inner_indent}<name>activation-mode</name>\n'
        f'{inner_indent}<value>disallowed</value>\n'
        f'{body_indent}</property>\n'
        f'{indent}</action>\n'
    )


def main():
    # Build input index via ET
    tree = ET.parse(JG_XML)
    root_el = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root_el.findall("./library/action")}

    input_root = {}  # (did, itype, iid, mode) -> root_action_id
    for inp in root_el.findall("./inputs/input"):
        key = (inp.findtext("device-id", ""),
               inp.findtext("input-type", ""),
               inp.findtext("input-id", ""),
               inp.findtext("mode", ""))
        for ac in inp.findall("action-configuration"):
            ra = ac.findtext("root-action", "")
            if ra:
                input_root[key] = ra

    # Read text for in-place edit
    with open(JG_XML, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    # ---------- ADDS ----------
    new_lib_blocks = []
    for key, desc in ADDS:
        ra = input_root.get(key)
        if not ra:
            print(f"ADD SKIP: input {key} not found")
            continue
        new_uuid = str(uuid.uuid4())
        root_pat = re.compile(
            r'(<action id="' + re.escape(ra) + r'" type="root">\s*<actions>)'
        )
        m = root_pat.search(text)
        if not m:
            print(f"ADD SKIP: root {ra[:8]} not found in text")
            continue
        text = text[:m.end()] + f"\n                <action-id>{new_uuid}</action-id>" + text[m.end():]
        new_lib_blocks.append(build_description_action_text(new_uuid, desc))
        print(f"ADD: {key} -> {desc}")

    # Append new library blocks before </library>
    lib_close = re.search(r"    </library>", text)
    text = text[:lib_close.start()] + "".join(new_lib_blocks) + text[lib_close.start():]

    # ---------- UPDATES ----------
    # Find each axis input's root, walk children to find the description action,
    # replace its <value>.
    for key, new_desc in UPDATES:
        ra = input_root.get(key)
        if not ra:
            print(f"UPDATE SKIP: input {key} not found")
            continue
        # Find the description action id this root references
        root_action = by_id.get(ra)
        if root_action is None:
            print(f"UPDATE SKIP: root {ra[:8]} not in library")
            continue
        desc_id = None
        for c in root_action.findall("actions/action-id"):
            if c.text and c.text in by_id and by_id[c.text].attrib.get("type") == "description":
                desc_id = c.text
                break
        if not desc_id:
            print(f"UPDATE SKIP: no description child on root {ra[:8]}")
            continue

        # Replace its <value>. Match: <action id="UUID" type="description">...<value>OLD</value>...</action>
        block_pat = re.compile(
            r'(<action id="' + re.escape(desc_id) + r'" type="description">'
            r'\s*<property type="string">\s*<name>description</name>\s*<value>)'
            r'([^<]+)'
            r'(</value>)',
            re.DOTALL,
        )
        m = block_pat.search(text)
        if not m:
            print(f"UPDATE SKIP: could not match description block for {desc_id[:8]}")
            continue
        text = text[:m.start(2)] + xml_escape(new_desc) + text[m.end(2):]
        print(f"UPDATE: {key} -> {new_desc}")

    # Validate
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        print(f"ERROR: XML parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    with open(JG_XML, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print("\nDone.")


if __name__ == "__main__":
    main()
