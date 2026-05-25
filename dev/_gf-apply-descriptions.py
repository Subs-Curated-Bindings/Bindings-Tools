"""
Apply confident JG description-action assignments to the Gunfighter profile XML.

Reads tools/_gf-descriptions.json (output of _gf-derive-descriptions.py).
For each (device, type, id, mode) entry:
  - Generate a description action in <library>
  - Wire it into the input's root <actions> as the FIRST child for button roots,
    AFTER the response-curve for axis roots (axis roots are skipped in this pass —
    axes need different handling).

Idempotent: skips inputs that already have a description action.

After running this script, run tools/fix-library-order.py to resolve forward references.

CAUTION: writes JG profile XML in-place. Backup made before write.
"""
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gunfighter Binds")
JG_PATH = STICK_DIR / "Joystick Gremlin Profile [ENH][GF][4.8.0][LIVE][R14].xml"
ASSIGNMENTS_JSON = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings\tools\_gf-descriptions.json")


def clean_body(text):
    """Tidy chart-derived text into a single-line body for the description action."""
    # Collapse multiple spaces, drop stray whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Convert | separators to neat ' | '
    text = re.sub(r"\s*\|\s*", " | ", text)
    return text


def build_description_text(etched, mode_tag, body, parenthetical=""):
    """Construct the canonical '<etched> [(par)] [[Modifier]] — <body>' string.

    Format: etched + optional parenthetical + optional mode-tag + em-dash + body.
    Parser at audit-chart-vs-profile.py strips both '(...)' and '[Modifier]' segments
    before matching etched-name to chart cluster.
    """
    parts = [etched]
    if parenthetical:
        parts.append(f"({parenthetical})")
    if mode_tag and mode_tag != "SCM Mode":
        if mode_tag in ("Modifier",):
            parts.append("[Modifier]")
    return " ".join(parts) + " — " + clean_body(body)


DESCRIPTION_ACTION_TPL = """    <action id="{action_id}" type="description">
        <property type="string">
            <name>description</name>
            <value>{description_text}</value>
        </property>
        <property type="string">
            <name>action-label</name>
            <value>Description</value>
        </property>
        <property type="activation-mode">
            <name>activation-mode</name>
            <value>disallowed</value>
        </property>
    </action>
"""


def main():
    assignments = json.loads(ASSIGNMENTS_JSON.read_text(encoding="utf-8"))

    # Read JG profile preserving line endings
    with open(JG_PATH, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    # Backup
    backup = JG_PATH.with_suffix(".xml.BAK-pre-descriptions")
    if not backup.exists():
        shutil.copy2(JG_PATH, backup)
        print(f"Backup written: {backup.name}")
    else:
        print(f"Backup already exists: {backup.name}")

    # Quick scan: find existing description actions to avoid duplicating
    existing_descs = re.findall(r'<action id="([^"]+)" type="description">', text)
    print(f"Existing description actions in profile: {len(existing_descs)}")

    added = 0
    skipped = 0
    new_actions_xml = []  # to be inserted into <library>
    new_action_id_refs = []  # tuples of (input_key, new_action_id, root_id)

    for input_key, info in assignments.items():
        device_id, input_type, input_id, mode = input_key.split("|", 3)
        if input_type == "axis":
            skipped += 1
            continue  # skip axes — different ordering rules

        etched = info["etched"]
        mode_tag = info["mode_tag"]
        body = info["body"]
        parenthetical = info.get("parenthetical", "")
        desc_text = build_description_text(etched, mode_tag, body, parenthetical)

        # Find the input block + its root-action id
        # Use regex with greedy=False over <input>...</input>
        input_pat = re.compile(
            r'<input>\s*'
            r'<device-id>' + re.escape(device_id) + r'</device-id>\s*'
            r'<input-type>' + re.escape(input_type) + r'</input-type>\s*'
            r'<mode>' + re.escape(mode) + r'</mode>\s*'
            r'<input-id>' + re.escape(input_id) + r'</input-id>\s*'
            r'<action-configuration>\s*'
            r'<root-action>([^<]+)</root-action>'
        )
        m = input_pat.search(text)
        if not m:
            print(f"  SKIP (input not found): {input_key}")
            skipped += 1
            continue
        root_id = m.group(1)
        # Find the <actions>...</actions> block inside the root action.
        # We search for <action id="ROOT" ...>, then locate the FIRST <actions>...</actions>
        # block following it.
        action_open_pat = re.compile(r'<action id="' + re.escape(root_id) + r'"[^>]*>')
        am = action_open_pat.search(text)
        if not am:
            print(f"  SKIP (root action <action> tag not found): {input_key} root={root_id}")
            skipped += 1
            continue
        # Find <actions> after the opening tag
        actions_open_idx = text.find("<actions>", am.end())
        actions_self_close_idx = text.find("<actions/>", am.end())
        # Also bound: don't go past the next sibling </action>
        next_action_close = text.find("</action>", am.end())
        if actions_open_idx == -1 or (actions_self_close_idx != -1 and actions_self_close_idx < actions_open_idx):
            # Handle self-closing <actions/>
            if actions_self_close_idx != -1 and actions_self_close_idx < next_action_close:
                text = text[:actions_self_close_idx] + "<actions>\n            </actions>" + text[actions_self_close_idx + len("<actions/>"):]
                actions_open_idx = text.find("<actions>", am.end())
            else:
                print(f"  SKIP (root has no <actions> block): {input_key}")
                skipped += 1
                continue
        actions_close_idx = text.find("</actions>", actions_open_idx)
        if actions_close_idx == -1 or actions_close_idx > text.find("</action>", actions_open_idx):
            print(f"  SKIP (malformed <actions> in root): {input_key}")
            skipped += 1
            continue
        # Now we have the slice: text[actions_open_idx : actions_close_idx + len('</actions>')]
        actions_inner_start = actions_open_idx + len("<actions>")
        actions_inner = text[actions_inner_start:actions_close_idx]

        # Check if any existing child action is already a description (idempotency)
        existing_children = re.findall(r'<action-id>([^<]+)</action-id>', actions_inner)
        already_has_desc = False
        for child_id in existing_children:
            child_action_pat = re.compile(
                r'<action id="' + re.escape(child_id) + r'" type="description"',
            )
            if child_action_pat.search(text):
                already_has_desc = True
                break
        if already_has_desc:
            print(f"  EXISTS (already has description): {input_key} -> {etched}")
            skipped += 1
            continue

        # Generate new action id and prepare insert
        new_id = str(uuid.uuid4())
        # Escape special XML chars in description text
        desc_text_esc = (desc_text
                         .replace("&", "&amp;")
                         .replace("<", "&lt;")
                         .replace(">", "&gt;"))
        new_action_xml = DESCRIPTION_ACTION_TPL.format(action_id=new_id, description_text=desc_text_esc)
        new_actions_xml.append(new_action_xml)

        # Insert <action-id> at FIRST position in root's <actions> (button root convention)
        # Build new inner: detect indentation from existing children
        match_indent = re.search(r'\n([ \t]+)<action-id>', actions_inner)
        child_indent = match_indent.group(1) if match_indent else "                "
        new_child_line = "\n" + child_indent + f"<action-id>{new_id}</action-id>"
        new_inner = new_child_line + actions_inner
        text = text[:actions_inner_start] + new_inner + text[actions_close_idx:]
        added += 1

    # Insert all new actions at the END of <library> (forward refs to be fixed by fix-library-order.py)
    if new_actions_xml:
        lib_close = "</library>"
        idx = text.find(lib_close)
        if idx == -1:
            print("ERROR: <library> end tag not found")
            sys.exit(1)
        # Insert before </library>
        insert_text = "".join(new_actions_xml)
        text = text[:idx] + insert_text + text[idx:]

    # Write back, preserving line endings
    with open(JG_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print()
    print(f"Added:   {added} description actions")
    print(f"Skipped: {skipped}")
    print()
    print("NEXT: run `py tools/fix-library-order.py [...]Gunfighter Binds/Joystick Gremlin Profile[...]xml`")
    print("      (or whatever the script's invocation pattern is)")


if __name__ == "__main__":
    main()
