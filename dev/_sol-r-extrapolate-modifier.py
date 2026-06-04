#!/usr/bin/env python3
"""Extrapolate left-stick SCM monikers onto the Modifier layer.

The moniker is physical identity, so each Modifier emit of physical button N
gets button N's SCM moniker (mini-stick already L-ANALOG; +50 vjoy target is
irrelevant to the label). Rules per Modifier emit:
  - default label ('Map to vJoy' etc.)  -> set to the physical moniker
  - quoted "..." label                  -> prepend 'moniker ' (keep the quoted)
  - already a moniker (e.g. L-ANALOG)    -> leave (flag)
Tempo position adds .tap/.hold to the base. Inputs with no SCM moniker
(button 29 placeholder) are skipped.

Dry-run by default; --apply to write. Preserves line endings.
"""
import sys, re
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
L = "141b1470-1081-11f0-8006-444553540000"
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


def collect(mode):
    d = {}
    for inp in root.iter("input"):
        if inp.findtext("device-id") != L or inp.findtext("mode") != mode:
            continue
        key = (inp.findtext("input-type"), inp.findtext("input-id"))
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action")
            if rid:
                out = []
                emits(rid, set(), "single", out)
                d.setdefault(key, []).extend(out)
    return d


def moniker_of(label):
    if not label or label in DEFAULTS or label.lstrip().startswith('"'):
        return None
    tok = label.split(" ", 1)[0]
    return tok if MONIKER.match(tok) else None


# SCM physical base moniker per input
scm = collect("SCM Mode")
BASE = {}
for key, es in scm.items():
    bases = {re.sub(r"\.(tap|hold)$", "", m) for (_, _, lab) in es if (m := moniker_of(lab))}
    if len(bases) == 1:
        BASE[key] = bases.pop()
    elif len(bases) > 1:
        print(f"  ! {key} has multiple SCM bases {bases} — skipping")

# propose Modifier edits
mod = collect("Modifier")
edits, skips = [], []
for key, es in sorted(mod.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
    base = BASE.get(key)
    if base is None:
        continue
    for (aid, path, cur) in es:
        target = base + (".tap" if path == "tap" else ".hold" if path == "hold" else "")
        if cur in DEFAULTS:
            new = target
        elif cur.lstrip().startswith('"'):
            new = f"{target} {cur}"
        elif (m := moniker_of(cur)) and m.startswith(base):
            continue  # already ours
        else:
            skips.append((key, aid, cur))
            continue
        edits.append((aid, new, cur))

print(f"\n=== {len(edits)} Modifier emits to label ===")
for (aid, new, cur) in edits:
    print(f"  {aid[:8]}  {cur!r:34} -> {new[:48]!r}")
if skips:
    print(f"\n=== {len(skips)} left as-is (non-default, not ours — review) ===")
    for (key, aid, cur) in skips:
        print(f"  {key[0]} {key[1]} {aid[:8]}  {cur[:60]!r}")


def set_label(text, aid, new):
    start = text.index(f'<action id="{aid}"')
    npos = text.index("<name>action-label</name>", start)
    vstart = text.index("<value>", npos) + len("<value>")
    vend = text.index("</value>", vstart)
    return text[:vstart] + new + text[vend:]


if "--apply" in sys.argv:
    for (aid, new, _) in edits:
        text = set_label(text, aid, new)
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"\nAPPLIED {len(edits)} labels.")
else:
    print("\n(dry-run — pass --apply to write)")
