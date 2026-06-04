#!/usr/bin/env python3
"""Make hat-buttons direction children carry the SAME moniker as the physical
button that hits the same vjoy slot, so the chart can't tell hat-mode from
button-mode. Builds a (vjoy-device, vjoy-button) -> moniker map from every
physical BUTTON emit (all modes), then labels each hat-buttons child whose slot
has a match. Works per device, so it only labels children with a real source
(right-stick children stay until the right buttons get monikers).

Dry-run by default; --apply to write. Preserves line endings.
"""
import sys, re
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
DEFAULTS = {"Map to vJoy", "Macro", "Change Mode", "Response Curve", "Map to Mouse",
            "Tempo", "Description", "Map to Keyboard", "", None}
MONIKER = re.compile(r"^[A-Za-z][A-Za-z0-9]*([.\-][A-Za-z0-9]+)+")

text = JG.read_text(encoding="utf-8", newline="")
root = ET.fromstring(text)
by_id = {a.get("id"): a for a in root.iter("action")}


def prop(a, n):
    for p in a.findall("property"):
        if (p.findtext("name") or "") == n:
            v = p.find("value")
            return v.text if v is not None else None
    return None


def moniker(label):
    if not label or label in DEFAULTS or label.lstrip().startswith('"'):
        return None
    tok = label.split(" ", 1)[0]
    return tok if MONIKER.match(tok) else None


# slot (vjoy-dev, vjoy-btn) -> moniker, from physical button emits
slot2mon = {}
for inp in root.iter("input"):
    if inp.findtext("input-type") != "button":
        continue
    for a in by_id.values():
        pass
    # walk this input's tree for map-to-vjoy emits with a moniker label
    seen = []
    def walk(aid, s):
        if aid in s:
            return
        s.add(aid)
        a = by_id.get(aid)
        if a is None:
            return
        if a.get("type") == "map-to-vjoy":
            m = moniker(prop(a, "action-label"))
            if m:
                slot2mon[(prop(a, "vjoy-device-id"), prop(a, "vjoy-input-id"))] = m
        for sub in a.iter("action-id"):
            walk(sub.text, s)
    for ac in inp.findall("action-configuration"):
        rid = ac.findtext("root-action")
        if rid:
            walk(rid, set())

# label hat-buttons children
edits = []
for hb in by_id.values():
    if hb.get("type") != "hat-buttons":
        continue
    for tag in ("North", "East", "South", "West", "Center"):
        el = hb.find(tag)
        if el is None or el.findtext("action-id") is None:
            continue
        child = by_id.get(el.findtext("action-id"))
        if child is None or child.get("type") != "map-to-vjoy":
            continue
        slot = (prop(child, "vjoy-device-id"), prop(child, "vjoy-input-id"))
        mon = slot2mon.get(slot)
        cur = prop(child, "action-label")
        if mon and cur != mon:
            edits.append((child.get("id"), cur, mon, slot, tag))

for (aid, cur, mon, slot, tag) in edits:
    print(f"  {aid[:8]} {tag:6} vjoy{slot[0]}/btn{slot[1]}:  {cur!r} -> {mon!r}")
print(f"\n{len(edits)} hat child label(s) to sync")


def set_label(text, aid, new):
    start = text.index(f'<action id="{aid}"')
    npos = text.index("<name>action-label</name>", start)
    vs = text.index("<value>", npos) + len("<value>")
    ve = text.index("</value>", vs)
    return text[:vs] + new + text[ve:]


if "--apply" in sys.argv:
    for (aid, _, mon, _, _) in edits:
        text = set_label(text, aid, mon)
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("APPLIED.")
else:
    print("(dry-run — pass --apply to write)")
