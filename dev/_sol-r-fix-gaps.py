#!/usr/bin/env python3
"""Fix the remaining left-stick SCM moniker gaps (Sub gave latitude):
  - button 11: move L-ENCODER.press from description -> action-label; desc -> bare
  - axis 7/8 : prepend L-Slider-1 / L-Slider-2 to the spare-axis label
  - button 36: label the base press emit (vjoy1 btn36) L-SCROLL.press
All targeted by action id (block-scoped). Preserves line endings. --apply to write.
"""
import sys, re
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
L = "141b1470-1081-11f0-8006-444553540000"
SEP = " — "  # space em-dash space

text = JG.read_text(encoding="utf-8", newline="")
root = ET.fromstring(text)
by_id = {a.get("id"): a for a in root.iter("action")}


def walk(aid, seen, out):
    if aid in seen:
        return
    seen.add(aid)
    a = by_id.get(aid)
    if a is None:
        return
    out.append(a)
    for s in a.iter("action-id"):
        walk(s.text, seen, out)


def input_actions(itype, iid, mode="SCM Mode"):
    for inp in root.iter("input"):
        if (inp.findtext("device-id") == L and inp.findtext("input-type") == itype
                and inp.findtext("input-id") == iid and inp.findtext("mode") == mode):
            out = []
            for ac in inp.findall("action-configuration"):
                walk(ac.findtext("root-action"), set(), out)
            return out
    return []


def pval(a, name):
    for p in a.findall("property"):
        if (p.findtext("name") or "") == name:
            v = p.find("value")
            return v.text if v is not None else None
    return None


# build edits: (action_id, property_name, new_value)
edits = []

# button 11 encoder press
for a in input_actions("button", "11"):
    if a.get("type") == "map-to-vjoy" and pval(a, "action-label") == "Map to vJoy":
        edits.append((a.get("id"), "action-label", "L-ENCODER.press"))
    if a.get("type") == "description":
        d = pval(a, "description") or ""
        if SEP in d:
            edits.append((a.get("id"), "description", d.split(SEP, 1)[1]))

# spare axes
for iid, mon in (("7", "L-Slider-1"), ("8", "L-Slider-2")):
    for a in input_actions("axis", iid):
        if a.get("type") == "map-to-vjoy":
            old = pval(a, "action-label") or ""
            if not old.startswith(mon):
                edits.append((a.get("id"), "action-label", f"{mon} {old}"))

# button 36 base press
for a in input_actions("button", "36"):
    if a.get("type") == "map-to-vjoy" and pval(a, "action-label") == "Map to vJoy":
        edits.append((a.get("id"), "action-label", "L-SCROLL.press"))


def set_prop(text, aid, prop, new):
    start = text.index(f'<action id="{aid}"')
    npos = text.index(f"<name>{prop}</name>", start)
    vstart = text.index("<value>", npos) + len("<value>")
    vend = text.index("</value>", vstart)
    old = text[vstart:vend]
    return text[:vstart] + new + text[vend:], old


for aid, prop, new in edits:
    text, old = set_prop(text, aid, prop, new)
    print(f"  {aid[:8]} {prop}:\n     - {old[:80]}\n     + {new[:80]}")

if "--apply" in sys.argv:
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"\nAPPLIED {len(edits)} edits.")
else:
    print(f"\n{len(edits)} edits (dry-run — pass --apply)")
