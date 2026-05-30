"""
Inspect quoted friendly-labels Sub embeds in JG action-label values.

Sub's convention (NXT 4.8.0, 2026-05-30): the generator can't auto-resolve a
friendly label for compound/non-vjoy actions (change-mode, keyboard-only macros)
or for some tempo leaves. So he prefixes the action-label `<value>` with the
friendly label in double-quotes, e.g.:

    "[T] Operator Cycle"
    "[H] Master Mode Cycle" Cycle into Nav mode.

This tool finds every leaf action (map-to-vjoy / change-mode / macro) whose
action-label contains a quoted substring, and resolves its FULL context:
  - containing tempo / double-tap and the path (tap / hold / single / double)
  - the root action that references that tempo
  - which physical input(s) + JG mode(s) reference that root
  - the vjoy slot it emits (if any) and the SC action that slot is bound to
    in the layout XML

It also lists, per (input, mode), every leaf emission so you can see which
leaves got a quoted label and which didn't (completeness check).

Usage:
  py tools/inspect-quoted-labels.py "<stick folder>"
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

QUOTE_PAT = re.compile(r'"([^"]*)"')
VJOY_AXIS_NAMES = {1: "x", 2: "y", 3: "z", 4: "rotx", 5: "roty", 6: "rotz", 7: "slider1", 8: "slider2"}


def find_files(stick_dir):
    jgs = [f for f in os.listdir(stick_dir)
           if "Joystick Gremlin Profile" in f and "R14" in f and f.endswith(".xml")
           and "FROM-GIT-HEAD" not in f]
    layouts = [f for f in os.listdir(stick_dir)
               if f.startswith("layout_") and f.endswith("_exported.xml")
               and "Clear_Bindings" not in f]
    return os.path.join(stick_dir, jgs[0]), os.path.join(stick_dir, layouts[0])


def label_of(action):
    for p in action.findall("property"):
        if p.findtext("name", "") == "action-label":
            return p.findtext("value", "") or ""
    return ""


def amode_of(action):
    for p in action.findall("property"):
        if p.attrib.get("type") == "activation-mode":
            return p.findtext("value", "") or ""
    return ""


def vjoy_slot(action):
    """Return (dev, input-id, type) for a map-to-vjoy, else None."""
    if action.attrib.get("type") != "map-to-vjoy":
        return None
    props = {p.findtext("name", ""): p.findtext("value", "") for p in action.findall("property")}
    try:
        return (int(props.get("vjoy-device-id", "0")),
                int(props.get("vjoy-input-id", "0")),
                props.get("vjoy-input-type", ""))
    except ValueError:
        return None


def macro_vjoy_slots(action):
    out = []
    if action.attrib.get("type") != "macro":
        return out
    for ma in action.findall("macro-action"):
        if ma.attrib.get("type") != "vjoy":
            continue
        props = {p.findtext("name", ""): p.findtext("value", "") for p in ma.findall("property")}
        try:
            out.append((int(props.get("vjoy-id", "0")),
                        int(props.get("input-id", "0")),
                        props.get("input-type", "")))
        except ValueError:
            pass
    return out


def parse_layout(layout_path):
    root = ET.parse(layout_path).getroot()
    button_map = defaultdict(list)
    axis_map = defaultdict(list)
    for am in root.findall("./actionmap"):
        amname = am.attrib.get("name", "")
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    button_map[(int(m.group(1)), int(m.group(2)))].append((amname, aname))
                    continue
                m = re.match(r"js(\d+)_(x|y|z|rotx|roty|rotz|rx|ry|rz|throttle|slider1|slider2)$", inp)
                if m:
                    axis_map[(int(m.group(1)), m.group(2))].append((amname, aname))
    return button_map, axis_map


def main():
    stick = sys.argv[1]
    jg_path, layout_path = find_files(stick)
    print(f"JG     : {os.path.basename(jg_path)}")
    print(f"Layout : {os.path.basename(layout_path)}\n")

    tree = ET.parse(jg_path)
    root_el = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root_el.findall("./library/action")}
    button_map, axis_map = parse_layout(layout_path)

    # Build reverse maps: action-id -> (parent tempo/double-tap id, path)
    parent_of = {}          # child_id -> (parent_id, path)
    for a in by_id.values():
        atype = a.attrib.get("type", "")
        if atype == "tempo":
            for s in a.findall("./short-actions/action-id"):
                if s.text:
                    parent_of[s.text] = (a.attrib["id"], "tap")
            for l in a.findall("./long-actions/action-id"):
                if l.text:
                    parent_of[l.text] = (a.attrib["id"], "hold")
        elif atype == "double-tap":
            for s in a.findall("./single-actions/action-id"):
                if s.text:
                    parent_of[s.text] = (a.attrib["id"], "single")
            for d in a.findall("./double-actions/action-id"):
                if d.text:
                    parent_of[d.text] = (a.attrib["id"], "double")
        else:
            actions_el = a.find("actions")
            if actions_el is not None:
                for c in actions_el.findall("action-id"):
                    if c.text:
                        parent_of.setdefault(c.text, (a.attrib["id"], "direct"))

    # root-id -> list of (device, itype, iid, mode)
    root_inputs = defaultdict(list)
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action", "")
            if rid:
                root_inputs[rid].append((did, itype, iid, mode))

    def find_root_chain(aid):
        """Climb parent_of until we hit a root action; return (root_id, [path segments])."""
        path = []
        seen = set()
        cur = aid
        while cur in parent_of and cur not in seen:
            seen.add(cur)
            parent, p = parent_of[cur]
            path.append(p)
            cur = parent
        # cur is now the top action (tempo/root). If it's a root, done; else find root referencing it.
        return cur, list(reversed(path))

    # Map every action up to the input/mode that drives it
    def context_for(aid):
        top, path = find_root_chain(aid)
        # top might be a tempo whose root references it
        root_id = top
        if top in by_id and by_id[top].attrib.get("type") != "root":
            # find a root that references top
            for rid, a in by_id.items():
                if a.attrib.get("type") == "root":
                    ael = a.find("actions")
                    if ael is not None and any(c.text == top for c in ael.findall("action-id")):
                        root_id = rid
                        break
        inputs = root_inputs.get(root_id, [])
        return root_id, path, inputs

    def slot_binding(slot):
        if slot is None:
            return None
        dev, inp, vtype = slot
        if vtype == "button":
            acts = button_map.get((dev, inp), [])
            return f"vjoy{dev} btn{inp} -> " + (", ".join(f"{an} [{am}]" for am, an in acts) if acts else "UNBOUND in layout")
        return f"vjoy{dev} {vtype}{inp}"

    # ---- Find quoted-label actions ----
    print("=" * 78)
    print("QUOTED-LABEL ACTIONS")
    print("=" * 78)
    quoted = []
    for aid, a in by_id.items():
        lbl = label_of(a)
        m = QUOTE_PAT.search(lbl)
        if not m:
            continue
        quoted.append((aid, a, lbl, m.group(1)))

    # Sort by appearance order in library
    order = {a.attrib["id"]: i for i, a in enumerate(root_el.findall("./library/action"))}
    quoted.sort(key=lambda t: order.get(t[0], 0))

    for aid, a, lbl, qtext in quoted:
        atype = a.attrib.get("type", "")
        root_id, path, inputs = context_for(aid)
        path_str = ">".join(path) if path else "(root-direct)"
        print(f"\n● quoted label : \"{qtext}\"")
        print(f"  action       : {atype}  id={aid[:8]}  activation={amode_of(a)}")
        print(f"  full label   : {lbl}")
        print(f"  tempo path   : {path_str}")
        # emission
        if atype == "map-to-vjoy":
            print(f"  emits        : {slot_binding(vjoy_slot(a))}")
        elif atype == "change-mode":
            tm = a.findtext("./target-mode/property/value", "")
            ct = ""
            for p in a.findall("property"):
                if p.findtext("name", "") == "change-type":
                    ct = p.findtext("value", "")
            print(f"  emits        : change-mode {ct} -> '{tm}' (no SC action; JG-internal)")
        elif atype == "macro":
            slots = macro_vjoy_slots(a)
            keys = [ma for ma in a.findall("macro-action") if ma.attrib.get("type") == "key"]
            if slots:
                print(f"  emits (vjoy) : " + "; ".join(slot_binding(s) for s in slots))
            if keys:
                print(f"  emits (keys) : {len(keys)} key macro-actions (keyboard chord; no SC action lookup)")
        if not inputs:
            print(f"  driven by    : (no input references root {root_id[:8]})")
        else:
            for (did, itype, iid, mode) in inputs:
                print(f"  driven by    : {itype} id={iid} | mode={mode}")

    # ---- Completeness: per tempo, show both leaves + which are labeled ----
    print("\n" + "=" * 78)
    print("TEMPOS — leaf labeling (tap=short / hold=long)")
    print("=" * 78)
    for aid, a in by_id.items():
        if a.attrib.get("type") != "tempo":
            continue
        root_id, path, inputs = context_for(aid)
        inp_str = "; ".join(f"{i[1]}#{i[2]}/{i[3]}" for i in inputs) or "(unreferenced)"
        shorts = [s.text for s in a.findall("./short-actions/action-id") if s.text]
        longs = [l.text for l in a.findall("./long-actions/action-id") if l.text]
        print(f"\n  tempo id={aid[:8]}  driven by: {inp_str}")
        for tag, ids in (("tap ", shorts), ("hold", longs)):
            for cid in ids:
                c = by_id.get(cid)
                if c is None:
                    continue
                lbl = label_of(c)
                q = QUOTE_PAT.search(lbl)
                mark = f'LABELED "{q.group(1)}"' if q else "-- no quoted label --"
                ct = c.attrib.get("type", "")
                extra = ""
                if ct == "map-to-vjoy":
                    extra = slot_binding(vjoy_slot(c))
                elif ct == "change-mode":
                    extra = "change-mode -> " + c.findtext("./target-mode/property/value", "")
                elif ct == "macro":
                    extra = "macro"
                print(f"    {tag} [{ct:12s}] {mark}")
                if extra:
                    print(f"          {extra}")


if __name__ == "__main__":
    main()
