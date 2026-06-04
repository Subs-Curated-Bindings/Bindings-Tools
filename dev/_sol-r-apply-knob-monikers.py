#!/usr/bin/env python3
"""Apply C (match sibling): prepend the L-KNOB.N moniker to the change-mode leaf
on buttons 20/21/23 so it matches its vJoy sibling. Targeted by action id.
Preserves line endings. Dry-run unless --apply.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
# change-mode action id -> moniker to prepend
TARGETS = {
    "ee318112": "L-KNOB.20",   # button 20 NAV Mode
    "e2930cd1": "L-KNOB.21",   # button 21 SCM Mode
    "97376e21": "L-KNOB.23",   # button 23 Toggle M/S
}

text = JG.read_text(encoding="utf-8", newline="")
root = ET.fromstring(text)
by_id = {a.get("id"): a for a in root.iter("action")}

edits = []
for short, mon in TARGETS.items():
    a = next(a for aid, a in by_id.items() if aid.startswith(short))
    old = None
    for p in a.findall("property"):
        if (p.findtext("name") or "") == "action-label":
            v = p.find("value")
            old = v.text or ""
    assert old is not None, f"no action-label on {short}"
    if old.startswith(mon):
        print(f"  {short}: already prefixed, skip")
        continue
    new = f"{mon} {old}"
    needle = f"<value>{old}</value>"
    assert text.count(needle) == 1, f"label not unique for {short}: {text.count(needle)}x"
    edits.append((needle, f"<value>{new}</value>", old, new))

for _, _, old, new in edits:
    print(f"  - {old[:70]}")
    print(f"  + {new[:70]}\n")

if "--apply" in sys.argv:
    for needle, repl, _, _ in edits:
        text = text.replace(needle, repl)
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("APPLIED.")
else:
    print("(dry-run — pass --apply to write)")
