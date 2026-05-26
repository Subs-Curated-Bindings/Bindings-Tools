"""Generate per-stick chart-slot → SC-action sidecars.

For each stick, walks the JG profile to find every input that carries a
`<action type="description">` in the `<etched-name>[ [Modifier]] (...) — body`
convention, collects that input's vjoy emissions, and cross-references the
layout XML to identify the SC action.

Output (per stick): a JSON keyed by chart bind ID (the etched-name part of the
description), giving the SCM-mode SC action and the vjoy slot info needed for
user-actionmaps overlay rendering.

This replaces the fuzzy chart-text matcher in subliminal-gg's extract_slots.py.

Usage:
  python tools/build-chart-slot-actions.py <stick-folder>
  python tools/build-chart-slot-actions.py --all       # all 5 sticks
  python tools/build-chart-slot-actions.py --all --out <dir>   # write sidecars to <dir>
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[1]

# Slug map — same as the joystick-bound-actions sidecar in subliminal-gg
SLUGS = {
    "[Enhanced] Dual VKB Gladiator NXT":           "vkb-gladiator-dual",
    "[Enhanced] Dual VKB Gunfighter Binds":        "vkb-gunfighter-dual",
    "[Enhanced] Dual TM SOL-R":                    "tm-sol-r-2-dual",
    "[Enhanced] Virpil VMAX Throttle + Aeromax-R": "virpil-vmax-aeromax-r",
    "[Enhanced] MOZA MTQ + MHG":                   "moza-ab6-mhg-mtq",
}

# Mode names to prefer when picking the "default" action for the showcase view.
# Listed in priority order — first match wins. Different sticks name SCM mode
# differently (VMAX uses "NAV Mode" for its "default flying" mode), so we try
# the common ones.
PREFERRED_MODES = ["SCM Mode", "NAV Mode", "Nav Mode", "default", ""]

# ---------- description-text parser (lifted from audit-chart-vs-profile.py) ----

ETCHED_PAT = re.compile(
    r"^(?P<etched>"
    r"(?:[A-Z0-9]+(?:-[A-Z0-9]+){1,4}(?:\.[a-z0-9-]+)*)"
    r"|(?:[LR]-[A-Z0-9]+(?:\.[a-z0-9-]+)*)"
    r")"
)


def parse_description_text(desc):
    """Return (etched_name, mode_tag, body) or None."""
    m = ETCHED_PAT.match(desc)
    if not m:
        return None
    etched = m.group("etched")
    rest = desc[m.end():].strip()
    mode_tag = ""
    if "[Modifier]" in rest:
        mode_tag = "Modifier"
        rest = rest.replace("[Modifier]", "").strip()
    rest = re.sub(r"^\([^)]*\)\s*", "", rest).strip()
    body = rest[1:].strip() if rest.startswith("—") else (
        rest.split("—", 1)[1].strip() if "—" in rest else ""
    )
    return etched, mode_tag, body


# ---------- JG profile parsing ----------

def collect_vjoy_targets(action, by_id, visited=None, path="always"):
    """Walk an action subtree, collect (vjoy_dev, vjoy_input, type, path)."""
    if visited is None:
        visited = set()
    aid = action.attrib.get("id")
    if aid in visited:
        return []
    visited.add(aid)
    out = []
    atype = action.attrib.get("type", "")
    if atype == "map-to-vjoy":
        props = {p.findtext("name", ""): p.findtext("value", "") for p in action.findall("property")}
        try:
            out.append((
                int(props.get("vjoy-device-id", "0")),
                int(props.get("vjoy-input-id", "0")),
                props.get("vjoy-input-type", ""),
                path,
            ))
        except ValueError:
            pass
    if atype == "macro":
        for ma in action.findall("macro-action"):
            if ma.attrib.get("type") != "vjoy":
                continue
            props = {p.findtext("name", ""): p.findtext("value", "") for p in ma.findall("property")}
            try:
                t = (
                    int(props.get("vjoy-id", "0")),
                    int(props.get("input-id", "0")),
                    props.get("input-type", ""),
                    path,
                )
                if t not in out:
                    out.append(t)
            except ValueError:
                pass
    if atype == "tempo":
        for s in action.findall("./short-actions/action-id"):
            if s.text and s.text in by_id and s.text != aid:
                out.extend(collect_vjoy_targets(by_id[s.text], by_id, set(visited), "tap"))
        for l in action.findall("./long-actions/action-id"):
            if l.text and l.text in by_id and l.text != aid:
                out.extend(collect_vjoy_targets(by_id[l.text], by_id, set(visited), "hold"))
        return out
    if atype == "double-tap":
        for s in action.findall("./single-actions/action-id"):
            if s.text and s.text in by_id and s.text != aid:
                out.extend(collect_vjoy_targets(by_id[s.text], by_id, set(visited), path))
        for d in action.findall("./double-actions/action-id"):
            if d.text and d.text in by_id and d.text != aid:
                out.extend(collect_vjoy_targets(by_id[d.text], by_id, set(visited), path))
        return out
    actions_el = action.find("actions")
    if actions_el is not None:
        for ch in actions_el.findall("action-id"):
            if ch.text and ch.text in by_id and ch.text != aid:
                out.extend(collect_vjoy_targets(by_id[ch.text], by_id, visited, path))
    return out


def parse_jg(jg_path):
    """Return list of input records with etched_name + mode + vjoy targets."""
    tree = ET.parse(jg_path)
    root_el = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root_el.findall("./library/action")}

    records = []
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        for ac in inp.findall("action-configuration"):
            root_id = ac.findtext("root-action", "")
            if not root_id or root_id not in by_id:
                continue
            root_action = by_id[root_id]

            # Find the description action
            etched, mode_tag, body, raw = None, "", "", None
            actions_el = root_action.find("actions")
            if actions_el is not None:
                for c in actions_el.findall("action-id"):
                    if not c.text or c.text not in by_id:
                        continue
                    child = by_id[c.text]
                    if child.attrib.get("type") != "description":
                        continue
                    raw_value = ""
                    for p in child.findall("property"):
                        if p.findtext("name", "") == "description":
                            raw_value = p.findtext("value", "") or ""
                            break
                    raw = raw_value
                    parsed = parse_description_text(raw_value)
                    if parsed:
                        etched, mode_tag, body = parsed
                    break

            if not etched:
                continue  # no description = not a chart-bridged input

            vjoy_targets = collect_vjoy_targets(root_action, by_id)
            records.append({
                "etched": etched,
                "mode": mode,
                "mode_tag": mode_tag,
                "body": body,
                "phys_device": did,
                "phys_type": itype,
                "phys_id": iid,
                "vjoy_targets": vjoy_targets,
            })
    return records


# ---------- Layout XML parsing ----------

VJOY_AXIS_NAMES = {1: "x", 2: "y", 3: "z", 4: "rotx", 5: "roty", 6: "rotz", 7: "slider1", 8: "slider2"}


def parse_layout(layout_path):
    """Return {(jsN, slot_name): [(actionmap, action_name), ...]}.

    slot_name is the layout's spelling: `button1`, `x`, `hat1_up`, etc.
    """
    root = ET.parse(layout_path).getroot()
    bind_map = defaultdict(list)
    for am in root.findall("./actionmap"):
        amname = am.attrib.get("name", "")
        for act in am.findall("action"):
            aname = act.attrib.get("name", "")
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_(.+)$", inp)
                if m:
                    bind_map[(int(m.group(1)), m.group(2))].append((amname, aname))
    return bind_map


def vjoy_to_layout_key(dev, inp, vtype):
    """Translate a JG vjoy emission tuple to the layout XML's (jsN, slot_name)."""
    if vtype == "button":
        return (dev, f"button{inp}")
    if vtype == "axis":
        return (dev, VJOY_AXIS_NAMES.get(inp, f"axis{inp}"))
    if vtype == "hat":
        # JG emits the hat by id; layout XML splits per direction. For audit
        # purposes we don't usually go through hats this way (JG profiles wrap
        # hat directions as separate inputs feeding buttons), but support it.
        return (dev, f"hat{inp}")
    return None


# ---------- Sidecar builder ----------

def build_sidecar(stick_dir):
    """Return the sidecar dict for a stick folder."""
    folder = Path(stick_dir).name
    if folder not in SLUGS:
        sys.exit(f"Unknown stick folder: {folder}")
    slug = SLUGS[folder]

    # Locate files
    sd = Path(stick_dir)
    jgs = [p for p in sd.iterdir()
           if "Joystick Gremlin Profile" in p.name and "R14" in p.name
           and p.name.endswith(".xml") and "FROM-GIT-HEAD" not in p.name]
    layouts = [p for p in sd.iterdir()
               if p.name.startswith("layout_") and p.name.endswith("_exported.xml")
               and "Clear_Bindings" not in p.name]
    if not jgs:
        sys.exit(f"No R14 JG profile in {stick_dir}")
    if not layouts:
        sys.exit(f"No stick-specific layout in {stick_dir}")
    jg_path, layout_path = jgs[0], layouts[0]

    print(f"=== {slug} ===")
    print(f"  JG:     {jg_path.name}")
    print(f"  Layout: {layout_path.name}")

    jg_records = parse_jg(jg_path)
    layout_bind = parse_layout(layout_path)
    print(f"  JG inputs with descriptions: {len(jg_records)}")
    print(f"  Layout rebind keys:          {len(layout_bind)}")

    # Build per-(etched, mode, path) → action mapping. For each JG record:
    #   - mode comes from JG's mode field (SCM Mode, Modifier, etc.)
    #   - path comes from collect_vjoy_targets (always/tap/hold)
    # The renderer in subliminal-gg uses this to pick an action per chart slot
    # based on the slot's mode marker ([M] → Modifier, [H] → hold path, etc.).

    def emission_action(vt):
        """Look up a vjoy emission's first SC action via the layout XML."""
        dev, inp, vtype, _ = vt
        key = vjoy_to_layout_key(dev, inp, vtype)
        if key is None:
            return None, None
        actions = layout_bind.get(key, [])
        if not actions:
            return None, f"js{dev}_{key[1]}"
        return actions[0][1], f"js{dev}_{key[1]}"  # first action, layout key

    by_etched = defaultdict(list)
    for r in jg_records:
        by_etched[r["etched"]].append(r)

    binds = {}
    stats = {"resolved": 0, "no_action": 0}
    for etched, recs in by_etched.items():
        modes_dict = {}
        for r in recs:
            mode_label = r["mode"] or "default"
            # Map each vjoy_target's path to its action
            per_path = {}  # path → action
            per_path_layout = {}  # path → layout key (for debug)
            for vt in r["vjoy_targets"]:
                _dev, _inp, _vtype, path = vt
                action, layout_key = emission_action(vt)
                if action and path not in per_path:
                    per_path[path] = action
                    per_path_layout[path] = layout_key
            if per_path:
                modes_dict[mode_label] = {
                    "actions": per_path,
                    "layout_keys": per_path_layout,
                    "body": r["body"],
                }

        # Pick the showcase action: highest-priority mode, prefer always > tap > hold
        showcase_action = None
        for mode_pref in PREFERRED_MODES + sorted(modes_dict.keys()):
            if mode_pref not in modes_dict:
                continue
            for p in ("always", "tap", "hold"):
                if p in modes_dict[mode_pref]["actions"]:
                    showcase_action = modes_dict[mode_pref]["actions"][p]
                    break
            if showcase_action:
                break

        binds[etched] = {
            "phys_device": recs[0]["phys_device"],
            "phys_type": recs[0]["phys_type"],
            "phys_id": recs[0]["phys_id"],
            "modes": modes_dict,
            "showcase_action": showcase_action,
        }

        if showcase_action:
            stats["resolved"] += 1
        else:
            stats["no_action"] += 1

    print(f"  Sidecar binds: {len(binds)}  ({stats['resolved']} with showcase action, "
          f"{stats['no_action']} unresolved)")

    return {
        "stick_slug": slug,
        "stick_folder": folder,
        "jg_profile": jg_path.name,
        "layout_xml": layout_path.name,
        "preferred_modes": PREFERRED_MODES,
        "stats": stats,
        "binds": binds,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stick_dir", nargs="?", help="Stick folder")
    p.add_argument("--all", action="store_true", help="Process all 5 sticks")
    p.add_argument("--out", help="Output directory for sidecars (default: ./out/chart-slot-actions)")
    args = p.parse_args()

    if args.all:
        sticks = sorted(REPO / k for k in SLUGS.keys())
    elif args.stick_dir:
        sticks = [Path(args.stick_dir)]
    else:
        p.error("Specify a stick folder or --all")

    out_dir = Path(args.out) if args.out else REPO / "tools" / "_chart-slot-actions"
    out_dir.mkdir(parents=True, exist_ok=True)

    for stick in sticks:
        if not stick.exists():
            print(f"skip {stick} — not present locally", file=sys.stderr)
            continue
        sidecar = build_sidecar(stick)
        out_file = out_dir / f"{sidecar['stick_slug']}.json"
        out_file.write_text(json.dumps(sidecar, indent=2))
        print(f"  Wrote {out_file}\n")


if __name__ == "__main__":
    main()
