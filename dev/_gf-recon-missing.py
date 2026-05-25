"""
Gunfighter — recon: for each JG input that has no description action,
report (device, type, id, mode) + vjoy targets + SC actions those vjoys fire.

Used to hand-curate _gf-descriptions-pass2.json.
"""
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = Path(r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gunfighter Binds")
JG_PATH = STICK_DIR / "Joystick Gremlin Profile [ENH][GF][4.8.0][LIVE][R14].xml"
LAYOUT_PATH = STICK_DIR / "layout_ENH_GF_480_LIVE_exported.xml"


def parse_layout():
    tree = ET.parse(LAYOUT_PATH)
    root = tree.getroot()
    bm = defaultdict(list)
    axis_m = defaultdict(list)
    hat_m = defaultdict(list)
    for am in root.findall("./actionmap"):
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    bm[(int(m.group(1)), int(m.group(2)))].append(aname)
                    continue
                m = re.match(r"js(\d+)_(x|y|z|rx|ry|rz|throttle|slider1|slider2)$", inp)
                if m:
                    axis_m[(int(m.group(1)), m.group(2))].append(aname)
                    continue
                m = re.match(r"js(\d+)_hat(\d+)_(up|down|left|right)$", inp)
                if m:
                    hat_m[(int(m.group(1)), int(m.group(2)), m.group(3))].append(aname)
    return bm, axis_m, hat_m


def main():
    bm, axis_m, hat_m = parse_layout()

    tree = ET.parse(JG_PATH)
    root = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root.findall("./library/action")}

    # Map root-action-id -> True if any descendant action is a description
    def has_description(action, visited=None):
        if visited is None:
            visited = set()
        aid = action.attrib.get("id")
        if aid in visited:
            return False
        visited.add(aid)
        # Check direct children action-ids
        for actions_el in action.findall("actions"):
            for child in actions_el.findall("action-id"):
                cid = child.text
                if cid and cid in by_id:
                    if by_id[cid].attrib.get("type") == "description":
                        return True
                    if has_description(by_id[cid], visited):
                        return True
        return False

    def collect_vjoy(action, visited=None):
        if visited is None:
            visited = set()
        aid = action.attrib.get("id")
        if aid in visited:
            return []
        visited.add(aid)
        out = []
        if action.attrib.get("type") == "map-to-vjoy":
            props = {p.findtext("name", ""): p.findtext("value", "") for p in action.findall("property")}
            try:
                out.append(
                    (
                        int(props.get("vjoy-device-id", "0")),
                        props.get("vjoy-input-type", ""),
                        int(props.get("vjoy-input-id", "0")),
                    )
                )
            except ValueError:
                pass
        for el in action.iter():
            if el.tag == "action-id" and el.text and el.text in by_id and el.text != aid:
                out.extend(collect_vjoy(by_id[el.text], visited))
        return out

    # Walk every <input>, report ones without a description.
    print(f"{'device':<13} {'mode':<16} {'type':<6} {'id':<4} vjoy_targets -> SC actions")
    print("-" * 110)
    missing = []
    for inp in root.findall("./inputs/input"):
        did = inp.findtext("device-id")
        itype = inp.findtext("input-type")
        iid = inp.findtext("input-id")
        mode = inp.findtext("mode")
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action")
            if rid not in by_id:
                continue
            if has_description(by_id[rid]):
                continue
            vjoy = collect_vjoy(by_id[rid])
            sc_actions = []
            for v in vjoy:
                dev, vt, vid = v
                if vt == "button":
                    sc_actions.extend(bm.get((dev, vid), []))
                elif vt == "axis":
                    pass  # axis vjoy slot ids don't map directly
                elif vt == "hat":
                    for d in ("up", "down", "left", "right"):
                        sc_actions.extend(hat_m.get((dev, vid, d), []))
            # Trim device id for readability
            short = (did or "")[:8]
            vjoy_str = ", ".join(f"vj{d}/{vt}{vid}" for (d, vt, vid) in vjoy)
            sc_str = " | ".join(sc_actions) if sc_actions else "(no layout binding)"
            print(f"{short:<13} {mode:<16} {itype:<6} {iid:<4} {vjoy_str:<32} {sc_str}")
            missing.append((did, itype, iid, mode, vjoy, sc_actions))

    print()
    print(f"Total missing-description inputs: {len(missing)}")


if __name__ == "__main__":
    main()
