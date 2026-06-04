#!/usr/bin/env python3
"""Replicate the left stick's `hat-buttons` conversion onto the right stick's
POV hat (R hat 1, SCM). Clones the left hat-buttons action + its 4 direction
children (known-good XML), assigns fresh IDs, swaps vjoy device 1->2 in the
children (button numbers 31-34 stay), rewires, inserts into the library, and
repoints the right hat root from its old single map-to-vjoy to the new
hat-buttons. The old map-to-vjoy becomes an orphan (pruned in the final pass).

Dry-run by default; --apply to write. Preserves line endings. Idempotent guard.
"""
import sys, uuid, re
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
LHAT = "1b3a5733-ca77-40a9-8e51-7023d3e9f127"           # left hat-buttons action
LKIDS = {"North": "41006a78-4685-4c7b-951d-7f1005462202",
         "East":  "4cd48623-b5fd-4fc2-b9f3-c95685883be7",
         "South": "a07a7a17-d4c1-4997-974b-aa7e1f550bd5",
         "West":  "a8b891c2-9ff0-4ace-b107-a5dffea09d98"}
ROLD = "7bfa0fd3-e9b9-472d-a604-a20a31c61278"           # right hat's old map-to-vjoy (to replace)

text = JG.read_text(encoding="utf-8", newline="")
root = ET.fromstring(text)
by_id = {a.get("id"): a for a in root.iter("action")}

# idempotency guard: is the right hat already a hat-buttons?
RDEV = "6686f980-1082-11f0-8008-444553540000"
for inp in root.iter("input"):
    if inp.findtext("device-id") == RDEV and inp.findtext("input-type") == "hat":
        rid = inp.find("action-configuration").findtext("root-action")
        child = by_id[rid].find("actions").findtext("action-id")
        if by_id.get(child, ET.Element("x")).get("type") == "hat-buttons":
            sys.exit("Right hat already converted — nothing to do.")
        R_ROOT_CHILD = child  # current actions child id (== ROLD)


def block(aid):
    """Extract the raw <action id=aid ...>...</action> block (leaf — first </action>)."""
    i = text.index(f'<action id="{aid}"')
    j = text.index("</action>", i) + len("</action>")
    return text[i:j]


# fresh ids
new_kids = {d: str(uuid.uuid4()) for d in LKIDS}
new_hat = str(uuid.uuid4())

# clone children: new id + vjoy device 1->2
child_blocks = []
for d, old in LKIDS.items():
    b = block(old)
    b = b.replace(f'<action id="{old}"', f'<action id="{new_kids[d]}"')
    b = re.sub(r"(<name>vjoy-device-id</name>\s*<value>)1(</value>)", r"\g<1>2\g<2>", b)
    child_blocks.append(b)

# clone hat-buttons: new id + rewire direction child refs
hb = block(LHAT)
hb = hb.replace(f'<action id="{LHAT}"', f'<action id="{new_hat}"')
for d, old in LKIDS.items():
    hb = hb.replace(f"<action-id>{old}</action-id>", f"<action-id>{new_kids[d]}</action-id>")

print("=== NEW right hat-buttons (id %s) ===" % new_hat[:8])
print(hb)
print("=== NEW children (vjoy2) ===")
for d, b in zip(LKIDS, child_blocks):
    tgt = re.search(r"vjoy-input-id</name>\s*<value>(\d+)", b).group(1)
    print(f"  {d}: id={new_kids[d][:8]} -> vjoy2/btn{tgt}")
print(f"\n=== repoint right hat root: actions child {ROLD[:8]} -> {new_hat[:8]} ===")

if "--apply" in sys.argv:
    # insert new blocks (children, then hat-buttons) before </library>,
    # each with the standard 8-space action indent on its first line.
    new_text = "".join("        " + b + "\n" for b in (child_blocks + [hb]))
    lib_close = text.index("</library>")
    ins = text.rfind("\n", 0, lib_close) + 1
    text = text[:ins] + new_text + text[ins:]
    # repoint right hat root's actions child
    text = text.replace(f"<action-id>{ROLD}</action-id>",
                        f"<action-id>{new_hat}</action-id>", 1)
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    # validate
    ET.fromstring(text)
    print("\nAPPLIED. XML parses OK.")
else:
    print("\n(dry-run — pass --apply to write)")
