#!/usr/bin/env python3
"""Finish the moniker pass: left Nav + the entire right stick.

Source of truth = the LEFT SCM base moniker per physical input. Apply it to:
  - LEFT  Nav   (no swap)
  - RIGHT SCM / Modifier / Nav  (leading L -> R swap; side-less monikers like
    MAIN-TRIGGER / BTN.35 / BTN.39 stay identical and are reported)
Per emit: default label -> set moniker; quoted "..." -> prepend moniker (keeps
the right stick's own function text, e.g. Yaw/Pitch/Roll); already-ours -> skip.
Tempo position adds .tap/.hold. Hats are skipped (slot-sync labels them after).
button 29 (placeholder) has no base -> skipped.

Dry-run by default; --apply to write. Preserves line endings.
"""
import sys, re
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
LDEV = "141b1470-1081-11f0-8006-444553540000"
RDEV = "6686f980-1082-11f0-8008-444553540000"
DEFAULTS = {"Map to vJoy", "Macro", "Change Mode", "Response Curve", "Map to Mouse",
            "Tempo", "Description", "Map to Keyboard", "", None}
MONIKER = re.compile(r"^[A-Za-z][A-Za-z0-9]*([.\-][A-Za-z0-9]+)+")

text = JG.read_text(encoding="utf-8", newline="")
root = ET.fromstring(text)
by_id = {a.get("id"): a for a in root.iter("action")}


def lbl(a):
    for p in a.findall("property"):
        if (p.findtext("name") or "") == "action-label":
            v = p.find("value")
            return v.text if v is not None else None
    return None


def emits(aid, seen, path, out):
    if aid in seen:
        return
    seen.add(aid)
    a = by_id.get(aid)
    if a is None:
        return
    if a.get("type") in ("map-to-vjoy", "macro", "change-mode"):
        out.append((a.get("id"), path, lbl(a)))
    for cont in a:
        if cont.tag in ("short-actions", "long-actions", "single-actions",
                        "double-actions", "actions", "action-configuration"):
            np = "tap" if cont.tag == "short-actions" else ("hold" if cont.tag == "long-actions" else path)
            for sub in cont.iter("action-id"):
                emits(sub.text, seen, np, out)


def moniker(label):
    if not label or label in DEFAULTS or label.lstrip().startswith('"'):
        return None
    tok = label.split(" ", 1)[0]
    return tok if MONIKER.match(tok) else None


def collect(dev, mode):
    d = {}
    for inp in root.iter("input"):
        if inp.findtext("device-id") != dev or inp.findtext("mode") != mode:
            continue
        if inp.findtext("input-type") == "hat":
            continue
        key = (inp.findtext("input-type"), inp.findtext("input-id"))
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action")
            if rid:
                out = []
                emits(rid, set(), "single", out)
                d.setdefault(key, []).extend(out)
    return d


# LEFT SCM base moniker per input
BASE = {}
for key, es in collect(LDEV, "SCM Mode").items():
    bases = {re.sub(r"\.(tap|hold)$", "", m) for (_, _, lab) in es if (m := moniker(lab))}
    if len(bases) == 1:
        BASE[key] = bases.pop()


def swap(m, side):
    return ("R" + m[1:]) if (side == "R" and m and m[0] == "L") else m


TARGETS = [(LDEV, "L", "Nav Mode"), (RDEV, "R", "SCM Mode"),
           (RDEV, "R", "Modifier"), (RDEV, "R", "Nav Mode")]

edits, sideless = [], set()
for (dev, side, mode) in TARGETS:
    for key, es in sorted(collect(dev, mode).items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
        base0 = BASE.get(key)
        if base0 is None:
            continue
        base = swap(base0, side)
        if side == "R" and base == base0 and base0[0] != "R":
            sideless.add(base0)
        for (aid, path, cur) in es:
            target = base + (".tap" if path == "tap" else ".hold" if path == "hold" else "")
            if cur in DEFAULTS:
                new = target
            elif cur.lstrip().startswith('"'):
                new = f"{target} {cur}"
            elif (m := moniker(cur)) and m.startswith(base):
                continue
            else:
                continue
            edits.append((aid, new, cur, side, mode, key))

# summary
from collections import Counter
by_group = Counter((side, mode) for (_, _, _, side, mode, _) in edits)
for (side, mode), n in sorted(by_group.items()):
    print(f"  {side} [{mode}]: {n} labels")
print(f"  TOTAL: {len(edits)}")
if sideless:
    print(f"\n  ! side-less monikers kept identical on the right (no L to swap): {sorted(sideless)}")
print("\n  sample (right SCM):")
for (aid, new, cur, side, mode, key) in edits:
    if side == "R" and mode == "SCM Mode":
        print(f"    {key[0]} {key[1]:>2}: {cur[:24]!r} -> {new[:40]!r}")


def set_label(text, aid, new):
    start = text.index(f'<action id="{aid}"')
    npos = text.index("<name>action-label</name>", start)
    vs = text.index("<value>", npos) + len("<value>")
    ve = text.index("</value>", vs)
    return text[:vs] + new + text[ve:]


if "--apply" in sys.argv:
    for (aid, new, _, _, _, _) in edits:
        text = set_label(text, aid, new)
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"\nAPPLIED {len(edits)} labels.")
else:
    print("\n(dry-run — pass --apply to write)")
