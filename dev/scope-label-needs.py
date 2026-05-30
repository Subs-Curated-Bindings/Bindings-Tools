"""
Scope report: which JG inputs need a quoted friendly-label, across ALL modes.

Rule (Sub, 2026-05-30): a bind that is "just a single remap" needs no quoted
label — the generator resolves it from layout->CSV and (for a tempo short press)
leaves it unmarked. Anything that is NOT a single remap (change-mode, macro,
a long-press action, or a path stacking multiple actions) needs a quoted
friendly label on its meaningful (top) action, with NO marker in the quotes
(the generator auto-adds [H] for long press and [M]/[A]/[N] for the mode).

This walks every (device, input, mode) root, classifies each execution path
(short/long/direct), and reports the paths that need a manual label and whether
one is present yet.

Usage: py tools/scope-label-needs.py "<stick folder>"
"""
import os, re, sys
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
QUOTE_PAT = re.compile(r'"([^"]*)"')


def find_files(stick_dir):
    jg = next(f for f in os.listdir(stick_dir)
              if "Joystick Gremlin Profile" in f and "R14" in f and f.endswith(".xml") and "FROM-GIT-HEAD" not in f)
    layout = next(f for f in os.listdir(stick_dir)
                  if f.startswith("layout_") and f.endswith("_exported.xml") and "Clear_Bindings" not in f)
    return os.path.join(stick_dir, jg), os.path.join(stick_dir, layout)


def prop(action, name):
    for p in action.findall("property"):
        if p.findtext("name", "") == name:
            return p.findtext("value", "") or ""
    return ""


def label_of(a):
    return prop(a, "action-label")


def quoted(a):
    m = QUOTE_PAT.search(label_of(a))
    return m.group(1) if m else None


def parse_layout(layout_path):
    root = ET.parse(layout_path).getroot()
    bm = defaultdict(list)
    for am in root.findall("./actionmap"):
        for act in am.findall("action"):
            for r in act.findall("rebind"):
                m = re.match(r"js(\d+)_button(\d+)$", r.attrib.get("input", ""))
                if m:
                    bm[(int(m.group(1)), int(m.group(2)))].append(act.attrib.get("name", ""))
    return bm


def describe_leaf(a, by_id, button_map):
    t = a.attrib.get("type", "")
    if t == "map-to-vjoy":
        dev = int(prop(a, "vjoy-device-id") or 0)
        inp = int(prop(a, "vjoy-input-id") or 0)
        acts = button_map.get((dev, inp), [])
        names = acts[0] if acts else "UNBOUND"
        return "single-remap", f"vjoy{dev} btn{inp} -> {names}"
    if t == "change-mode":
        return "change-mode", "-> " + a.findtext("./target-mode/property/value", "")
    if t == "macro":
        return "macro", "keyboard/vjoy macro"
    if t == "double-tap":
        return "double-tap", ""
    if t == "tempo":
        return "tempo", ""
    return t, ""


def main():
    stick = sys.argv[1]
    jg_path, layout_path = find_files(stick)
    by_id_root = ET.parse(jg_path).getroot()
    by_id = {a.attrib["id"]: a for a in by_id_root.findall("./library/action")}
    button_map = parse_layout(layout_path)

    # device-id -> chart side, inferred from description etched-names (L-* vs R-*)
    side_votes = defaultdict(lambda: defaultdict(int))

    rows = []
    for inp in by_id_root.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        if itype == "axis":
            continue  # flight-axis passthroughs resolve via layout; no friendly label
        for ac in inp.findall("action-configuration"):
            rid = ac.findtext("root-action", "")
            if not rid or rid not in by_id:
                continue
            root = by_id[rid]
            ael = root.find("actions")
            child_ids = [c.text for c in ael.findall("action-id")] if ael is not None else []

            # description etched-name (chart cluster) if present
            etched = ""
            for cid in child_ids:
                c = by_id.get(cid)
                if c is not None and c.attrib.get("type") == "description":
                    d = prop(c, "description")
                    m = re.match(r"^([A-Za-z0-9.\-]+)", d)
                    etched = m.group(1) if m else ""
                    if etched.startswith("L-"):
                        side_votes[did]["L"] += 1
                    elif etched.startswith("R-"):
                        side_votes[did]["R"] += 1

            # classify paths
            paths = []  # (path_name, leaf_action)
            for cid in child_ids:
                c = by_id.get(cid)
                if c is None or c.attrib.get("type") == "description":
                    continue
                t = c.attrib.get("type", "")
                if t == "tempo":
                    for s in c.findall("./short-actions/action-id"):
                        if s.text in by_id:
                            paths.append(("short", by_id[s.text]))
                    for l in c.findall("./long-actions/action-id"):
                        if l.text in by_id:
                            paths.append(("long", by_id[l.text]))
                elif t == "double-tap":
                    for s in c.findall("./single-actions/action-id"):
                        if s.text in by_id:
                            paths.append(("single", by_id[s.text]))
                    for d in c.findall("./double-actions/action-id"):
                        if d.text in by_id:
                            paths.append(("double", by_id[d.text]))
                else:
                    paths.append(("direct", c))

            # which paths NEED a label: anything that's not a lone short single-remap
            needs = []
            # group leaves by path-name to detect stacked paths
            by_path = defaultdict(list)
            for pn, leaf in paths:
                by_path[pn].append(leaf)
            for pn, leaves in by_path.items():
                kinds = [describe_leaf(l, by_id, button_map)[0] for l in leaves]
                # short single remap alone -> auto, skip
                if pn == "short" and kinds == ["single-remap"]:
                    continue
                if pn == "direct" and kinds == ["single-remap"]:
                    continue  # bare single remap root: fully auto
                # A manual label is only needed where the generator can't resolve:
                # a change-mode or a macro leaf. A lone single-remap (short OR long)
                # is auto-resolved (+ auto-[H] on long), so it needs no manual label.
                meaningful = next((l for l in leaves if describe_leaf(l, by_id, button_map)[0] in ("change-mode", "macro")), None)
                if meaningful is None:
                    continue
                k, detail = describe_leaf(meaningful, by_id, button_map)
                q = quoted(meaningful)
                needs.append((pn, k, detail, q, len(leaves)))

            if needs:
                rows.append((did, itype, iid, mode, etched, needs))

    # resolve side labels
    side = {}
    for did, votes in side_votes.items():
        side[did] = "LEFT" if votes.get("L", 0) >= votes.get("R", 0) else "RIGHT"

    # report grouped by side + button
    rows.sort(key=lambda r: (side.get(r[0], "?"), int(r[2]) if r[2].isdigit() else 0, r[3]))
    print("=" * 90)
    print("LABEL-NEEDS SCOPE (paths that are NOT a lone single-remap)")
    print("  q=current quoted label | (none)=needs one written")
    print("=" * 90)
    cur_key = None
    total_needed = 0
    total_have = 0
    for did, itype, iid, mode, etched, needs in rows:
        key = (side.get(did, "?"), iid)
        if key != cur_key:
            print(f"\n[{side.get(did,'?')} stick] {itype} id={iid}   chart: {etched or '(no description)'}")
            cur_key = key
        for pn, kind, detail, q, n in needs:
            total_needed += 1
            if q:
                total_have += 1
            qd = f'"{q}"' if q else "(NONE — needs label)"
            stack = f" [+{n-1} stacked]" if n > 1 else ""
            print(f"    {mode:14s} {pn:6s} {kind:12s} {detail[:44]:44s} {qd}{stack}")

    print("\n" + "=" * 90)
    print(f"Paths needing a label: {total_needed}   already labeled: {total_have}   remaining: {total_needed - total_have}")
    print("=" * 90)


if __name__ == "__main__":
    main()
