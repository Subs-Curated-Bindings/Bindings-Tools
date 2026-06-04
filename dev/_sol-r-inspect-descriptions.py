#!/usr/bin/env python3
"""SOL-R description inspector — dump per-input, per-mode description chains.

For each physical <input>, walk its root-action tree and list every
`description` action's value in hierarchy order with its depth, grouped by
device side (L/R) and physical input id. Flags 'jumbled' values (leading
space, orphaned ' — ', or a leading mode-tag with no etched-name).

Usage: py tools/_sol-r-inspect-descriptions.py [L|R] [--mode SCM]
"""
import sys, re
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
SIDE = {"141b1470-1081-11f0-8006-444553540000": "L",
        "6686f980-1082-11f0-8008-444553540000": "R"}

# child containers that hold <action-id> references
CONTAINERS = ("actions", "short-actions", "long-actions", "single-actions",
              "double-actions", "action-configuration")


def main():
    side_filter = next((a for a in sys.argv[1:] if a in ("L", "R")), None)
    mode_filter = None
    if "--mode" in sys.argv:
        mode_filter = sys.argv[sys.argv.index("--mode") + 1]

    text = JG.read_text(encoding="utf-8", newline="")
    root = ET.fromstring(text)
    by_id = {a.get("id"): a for a in root.iter("action")}

    def desc_value(a):
        for p in a.findall("property"):
            if (p.findtext("name") or "") == "description":
                v = p.find("value")
                return v.text if v is not None else ""
        return None

    def action_label(a):
        for p in a.findall("property"):
            if (p.findtext("name") or "") == "action-label":
                v = p.find("value")
                return v.text if v is not None else ""
        return None

    DEFAULT_LABELS = {"Map to vJoy", "Macro", "Change Mode", "Response Curve",
                      "Map to Mouse", "Tempo", "Description", None, ""}

    def walk(aid, depth, seen, out):
        if aid in seen:
            return
        seen.add(aid)
        a = by_id.get(aid)
        if a is None:
            return
        t = a.get("type")
        if t == "description":
            out.append((depth, "DESC", desc_value(a) or ""))
        else:
            lbl = action_label(a)
            mark = "lbl" if lbl not in DEFAULT_LABELS else "lbl(default)"
            out.append((depth, f"{t}:{mark}", lbl or ""))
        # recurse into nested action-id refs
        for sub in a.iter("action-id"):
            walk(sub.text, depth + 1, seen, out)

    # collect: (side, itype, iid) -> { mode: [(depth, value), ...] }
    data = {}
    for inp in root.iter("input"):
        dev = inp.findtext("device-id")
        side = SIDE.get(dev)
        if side is None or (side_filter and side != side_filter):
            continue
        mode = inp.findtext("mode")
        if mode_filter and mode != mode_filter:
            continue
        ac = inp.find("action-configuration")
        rootid = ac.findtext("root-action") if ac is not None else None
        if not rootid:
            continue
        out = []
        walk(rootid, 0, set(), out)
        if not out:
            continue
        itype = inp.findtext("input-type")
        iid = inp.findtext("input-id")
        data.setdefault((side, itype, iid), {})[mode] = out

    def jumble(v):
        flags = []
        if v != v.lstrip():
            flags.append("LEADING-WS")
        if v.lstrip().startswith("—") or v.lstrip().startswith("- "):
            flags.append("ORPHAN-DASH")
        if re.match(r"^\s*—", v) or re.match(r"^\s+—", v):
            flags.append("ORPHAN-DASH")
        if re.match(r"^\[[^\]]+\]\s*—", v):
            flags.append("MODE-TAG-NO-NAME")
        return ",".join(dict.fromkeys(flags))

    MODE_ORD = {"SCM Mode": 0, "Modifier": 1, "Nav Mode": 2, "Auxiliary Mode": 3}
    for key in sorted(data, key=lambda k: (k[0], k[1], int(k[2]) if k[2].isdigit() else 999)):
        side, itype, iid = key
        print(f"\n=== {side}  {itype} id={iid} ===")
        for mode in sorted(data[key], key=lambda m: MODE_ORD.get(m, 9)):
            print(f"  [{mode}]")
            for depth, kind, v in data[key][mode]:
                fl = jumble(v) if kind == "DESC" else ""
                tag = f"  <<{fl}>>" if fl else ""
                short = (v[:90] + "…") if len(v) > 91 else v
                print(f"     d{depth} {kind:18} {short}{tag}")


if __name__ == "__main__":
    main()
