#!/usr/bin/env python3
"""Resolve every SOL-R axis input (JG profile) to its SC action(s) + category
so quoted friendly-labels can be authored to match the NXT axis convention.

For each axis input root: find the paired map-to-vjoy / map-to-mouse, read its
vjoy device + axis, map to the layout js-axis key (VJOY_AXIS_NAMES), then list
every <action name> in the layout XML that rebinds that js axis, with each
action's HumanLabel + Subs Categories from the canonical CSV.

One-off resolver; review output, hand-author the quoted labels, apply via
apply-action-labels.py. Lives in tools/ per the project convention.
"""
import sys, csv, xml.etree.ElementTree as ET
from pathlib import Path

STICK = Path("[Enhanced] Dual TM SOL-R")
JG = STICK / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
LAYOUT = STICK / "layout_ENH_SOL-R2_480_LIVE_exported.xml"
CSV = Path("../subliminal-gg/lib/sc-actions/data/sc_keybinds_reference.csv")

VJOY_AXIS_NAMES = {1: "x", 2: "y", 3: "z", 4: "rotx", 5: "roty", 6: "rotz", 7: "slider1", 8: "slider2"}

# ---- CSV: xmlname -> (HumanLabel, SubsCategories) ----
csv_lut = {}
with open(CSV, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        csv_lut[r["XMLActionName"]] = (r.get("HumanLabel", ""), r.get("Subs Categories", ""))

# ---- layout: js_key -> [action names] ----
ltext = LAYOUT.read_text(encoding="utf-8")
lroot = ET.fromstring(ltext)
layout_axis = {}  # js_key -> list of action names
for am in lroot.iter("actionmap"):
    for action in am.findall("action"):
        aname = action.get("name")
        for rb in action.iter("rebind"):
            inp = rb.get("input", "")
            if any(inp == f"js{d}_{ax}" for d in (1, 2) for ax in VJOY_AXIS_NAMES.values()):
                layout_axis.setdefault(inp, []).append(aname)

# ---- JG profile parse ----
jtext = JG.read_text(encoding="utf-8")
jroot = ET.fromstring(jtext)
by_id = {a.get("id"): a for a in jroot.iter("action")}

def props(a):
    d = {}
    for p in a.findall("property"):
        n = p.find("name")
        v = p.find("value")
        if n is not None:
            d[n.text] = v.text if v is not None else None
    return d

def find_emit(aid, seen=None):
    seen = seen or set()
    if aid in seen:
        return None
    seen.add(aid)
    a = by_id.get(aid)
    if a is None:
        return None
    if a.get("type") in ("map-to-vjoy", "map-to-mouse"):
        return a
    for sub in a.iter("action-id"):
        r = find_emit(sub.text, seen)
        if r:
            return r
    return None

# flat <profile><inputs><input> with device-id/input-type/mode/input-id and
# root-action under action-configuration.
results = []  # (devid, axisid, mode, jg_action_type, js_key, actions)
for inp in jroot.iter("input"):
    if (inp.findtext("input-type")) != "axis":
        continue
    devid = (inp.findtext("device-id") or "?")[:8]
    iid = inp.findtext("input-id")
    mname = inp.findtext("mode") or "?"
    ac = inp.find("action-configuration")
    rootid = ac.findtext("root-action") if ac is not None else None
    if not rootid:
        continue
    emit = find_emit(rootid)
    if emit is None:
        results.append((devid, iid, mname, "?", "?", []))
        continue
    if emit.get("type") == "map-to-mouse":
        results.append((devid, iid, mname, "map-to-mouse", "mouse", []))
        continue
    p = props(emit)
    vdev, vax = p.get("vjoy-device-id"), p.get("vjoy-input-id")
    try:
        jskey = f"js{int(vdev)}_{VJOY_AXIS_NAMES[int(vax)]}"
    except Exception:
        jskey = f"vjoy{vdev}_axis{vax}"
    results.append((devid, iid, mname, "map-to-vjoy", jskey, layout_axis.get(jskey, [])))

# Only SCM mode (the canonical view) for axes
for dlabel, iid, mode, jtype, jskey, acts in results:
    if mode != "SCM Mode":
        continue
    print(f"\n[{dlabel}] axis {iid}  ({jtype} -> {jskey})")
    if not acts:
        if jtype == "map-to-mouse":
            print("    mouse free-look axis (no SC vjoy action)")
        else:
            print("    *** no layout action bound to this js axis (SPARE/unbound) ***")
    for an in acts:
        hl, cat = csv_lut.get(an, ("?", "?"))
        print(f"    {an:42s} HumanLabel={hl!r:38s} cat={cat!r}")
