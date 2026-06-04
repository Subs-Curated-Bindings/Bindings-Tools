#!/usr/bin/env python3
"""SOL-R moniker-coverage audit. For a side (default L), list every bottom-tier
emitting action (map-to-vjoy / macro / change-mode) per input per mode and flag
which ones lack a moniker on their action-label. Axes count too (Sub wants a
moniker on every leaf even if the chart never shows it).

A 'moniker' = a leading bare token shaped like L-SW-1.up / L30.press / BTN.35 /
MAIN-TRIGGER.stage1 (has a '.' or '-'). A pure quoted "..." friendly-label or a
default label ('Map to vJoy', 'NAV Mode', etc.) counts as MISSING.

Usage: py tools/_sol-r-audit-monikers.py [L|R] [--mode SCM]
"""
import sys, re
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
SIDE = {"141b1470-1081-11f0-8006-444553540000": "L", "6686f980-1082-11f0-8008-444553540000": "R"}
DEFAULTS = {"Map to vJoy", "Macro", "Change Mode", "Response Curve", "Map to Mouse",
            "Tempo", "Description", "", None}
MONIKER = re.compile(r"^[A-Za-z][A-Za-z0-9]*([.\-][A-Za-z0-9]+)+")


def has_moniker(label):
    if not label or label in DEFAULTS:
        return False
    s = label.strip()
    if s.startswith('"'):
        return False
    return bool(MONIKER.match(s.split(" ", 1)[0]))


def main():
    side = next((a for a in sys.argv[1:] if a in ("L", "R")), "L")
    mode_only = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else None

    root = ET.fromstring(JG.read_text(encoding="utf-8", newline=""))
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
            out.append((path, a.get("type"), lbl(a)))
        for cont in a:
            if cont.tag in ("short-actions", "long-actions", "single-actions",
                            "double-actions", "actions", "action-configuration"):
                np = "tap" if cont.tag == "short-actions" else ("hold" if cont.tag == "long-actions" else path)
                for sub in cont.iter("action-id"):
                    emits(sub.text, seen, np, out)

    # mode -> list of (itype, iid, path, atype, label, ok)
    data = {}
    for inp in root.iter("input"):
        if SIDE.get(inp.findtext("device-id")) != side:
            continue
        mode = inp.findtext("mode")
        if mode_only and mode != mode_only:
            continue
        itype, iid = inp.findtext("input-type"), inp.findtext("input-id")
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action")
            if not rid:
                continue
            out = []
            emits(rid, set(), "single", out)
            for (path, atype, label) in out:
                data.setdefault(mode, []).append((itype, int(iid), path, atype, label, has_moniker(label)))

    MORD = {"SCM Mode": 0, "Modifier": 1, "Nav Mode": 2, "Auxiliary Mode": 3}
    for mode in sorted(data, key=lambda m: MORD.get(m, 9)):
        rows = data[mode]
        ok = sum(1 for r in rows if r[5])
        miss = [r for r in rows if not r[5]]
        print(f"\n##### {side}  [{mode}]  — {ok}/{len(rows)} leaf actions have a moniker; {len(miss)} MISSING")
        for (itype, iid, path, atype, label, _) in sorted(miss, key=lambda r: (r[0], r[1])):
            short = (label[:60] + "…") if label and len(label) > 61 else label
            print(f"   MISSING  {itype} {iid:>2} [{path:6}] {atype:12} label={short!r}")


if __name__ == "__main__":
    main()
