"""
Second pass: extend description-action coverage on the NXT JG profile to cover
Modifier mode + hats + axes. SCM-Mode buttons were labeled in pass 1.

For each chart bind cluster (id="bind.<etched-name>[.<dir>]" in the SVG), the
text content is split into SCM-mode segments (unprefixed / [H] / [DT]) and
Modifier-mode segments ([M] / [M][H] / [M][DT]). Then for each JG input that
maps to that etched-name, a description action is inserted into its root's
<actions> list.

Coverage targets (this pass):
  - Modifier-mode inputs corresponding to the ~54 SCM-Mode buttons labeled in
    pass 1 (where a Modifier-mode <input> exists for the same hardware button).
  - 8-way hat inputs L-A1 and R-A1 in both SCM Mode and Modifier mode.
  - 12 axis inputs (6 per device in SCM Mode). For axes mapped to a known chart
    cluster (L-T1, R-T1 throttles), use the cluster text. Otherwise, use a
    generic passthrough label derived from the vJoy axis output.

Skips: Auxiliary Mode (2 inputs) and Nav Mode (3 inputs) — per scope with Sub.
Skips: any root that already has a description action as its first child
       (to avoid double-labeling).
"""
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

JG_XML = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT\Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml"
SVG_PATH = r"C:\Users\subli\OneDrive\Desktop\nxt-chart-machine-readable.svg"

LEFT_DEV = "7d12d5c0-43ea-11f0-800a-444553540000"
RIGHT_DEV = "ec8bbeb0-4009-11f0-8002-444553540000"

# Etched-name table from pass 1 (the high-confidence SCM-Mode button mapping).
# (side, button-index, etched-name) -> we use this to know which Modifier-mode
# button corresponds to which chart cluster.
BUTTON_TO_ETCHED = [
    ("L", 1,  "MAIN-TRIG-L"),
    ("L", 3,  "L-A2"),
    ("L", 4,  "L-B1"),
    ("L", 6,  "L-A3.up"),
    ("L", 8,  "L-A3.down"),
    ("L", 9,  "L-A3.left"),
    ("L", 10, "L-A3.press-in"),
    ("L", 11, "L-A4.up"),
    ("L", 12, "L-A4.right"),
    ("L", 13, "L-A4.down"),
    ("L", 14, "L-A4.left"),
    ("L", 15, "L-A4.press-in"),
    ("L", 16, "L-C1.up"),
    ("L", 17, "L-C1.right"),
    ("L", 18, "L-C1.down"),
    ("L", 19, "L-C1.left"),
    ("L", 20, "L-C1.press-in"),
    ("L", 21, "RAPID-TRIG-L"),     # Trigger Up
    ("L", 22, "RAPID-TRIG-L"),     # Trigger Down — same cluster, different sub-text
    ("L", 23, "L-EN1.up"),
    ("L", 24, "L-EN1.down"),
    ("L", 25, "L-SW1.up"),
    ("L", 26, "L-SW1.down"),
    ("L", 27, "L-F1"),
    ("L", 29, "L-F3"),
    ("R", 1,  "MAIN-TRIG-R.stage-1"),
    ("R", 2,  "MAIN-TRIG-R.stage-2"),
    ("R", 3,  "R-A2"),
    ("R", 4,  "R-B1"),
    ("R", 5,  "R-D1"),
    ("R", 6,  "R-A3.up"),
    ("R", 7,  "R-A3.right"),
    ("R", 8,  "R-A3.down"),
    ("R", 9,  "R-A3.left"),
    ("R", 10, "R-A3.press-in"),
    ("R", 11, "R-A4.down"),
    ("R", 12, "R-A4.right"),
    ("R", 13, "R-A4.up"),
    ("R", 14, "R-A4.left"),
    ("R", 15, "R-A4.press-in"),
    ("R", 16, "R-C1.up"),
    ("R", 17, "R-C1.right"),
    ("R", 18, "R-C1.down"),
    ("R", 19, "R-C1.left"),
    ("R", 20, "R-C1.press-in"),
    ("R", 21, "RAPID-TRIG-R"),     # Trigger Up
    ("R", 22, "RAPID-TRIG-R"),     # Trigger Down
    ("R", 23, "R-EN1.up"),
    ("R", 24, "R-EN1.down"),
    ("R", 25, "R-SW1.up"),
    ("R", 26, "R-SW1.down"),
    ("R", 27, "R-F1"),
    ("R", 28, "R-F2"),
    ("R", 29, "R-F3"),
]

DEVICE = {"L": LEFT_DEV, "R": RIGHT_DEV}


def parse_svg_clusters(svg_path):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    clusters = {}
    for elem in root.iter():
        eid = elem.attrib.get("id", "")
        if not (eid.startswith("bind.") or eid.startswith("label.")):
            continue
        parts = []
        for t in elem.iter():
            tag = t.tag.split("}", 1)[-1]
            if tag in ("text", "tspan") and t.text:
                parts.append(t.text)
        clusters[eid] = " ".join(" ".join(parts).split())
    return clusters


def split_chart_text(text):
    """Given a chart cluster's text, return (scm_segments, modifier_segments).
    Segments are separated by [M], [H], [DT], [M][H], [M][DT] markers.
    SCM = anything that DOESN'T start with [M]
    Modifier = anything that starts with [M] (including [M][H], [M][DT])
    """
    # Find all marker positions; segments are between markers.
    # Markers: [M], [H], [DT], optionally chained like [M][H], [M][DT]
    marker_pat = re.compile(r"(\[[A-Z]+\](?:\[[A-Z]+\])*)")
    parts = marker_pat.split(text)
    # parts: [pre_text, marker1, text1, marker2, text2, ...]
    segments = []
    # First segment is unprefixed
    if parts[0].strip():
        segments.append(("", parts[0].strip()))
    for i in range(1, len(parts), 2):
        marker = parts[i]
        seg_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        segments.append((marker, seg_text))

    scm_segs = [f"{m}{(' ' + t) if t else ''}".strip() for m, t in segments if "[M]" not in m]
    mod_segs = [f"{m}{(' ' + t) if t else ''}".strip().replace("[M]", "").strip()
                for m, t in segments if "[M]" in m]
    # Clean up: strip empty
    scm_segs = [s for s in scm_segs if s]
    mod_segs = [s for s in mod_segs if s]
    return scm_segs, mod_segs


def hat_combined_description(clusters, side):
    """For the 8-way hat input, produce one combined description by joining
    each of its 5 direction clusters' chart text."""
    prefix = f"L-A1" if side == "L" else "R-A1"
    parts = []
    for dir_ in ("up", "down", "left", "right", "press-in"):
        cid = f"bind.{prefix}.{dir_}"
        if cid in clusters:
            parts.append(f"{dir_}={clusters[cid]}")
    return " | ".join(parts)


def axis_description(clusters, side, axis_id, vjoy_target):
    """Build a description for an axis input. If the axis maps to a known T1
    chart cluster, use that; otherwise use a generic passthrough label."""
    # Try to identify which physical axis this is. Without a hardware spec,
    # we can only label by passthrough.
    # The chart's T1 cluster: bind.L-T1.up / bind.L-T1.down (or R-T1)
    # We don't know which axis-id the T1 throttle maps to in JG without
    # more info, so we label all axes generically and let Sub correct in JG UI.
    side_name = "Left stick" if side == "L" else "Right stick"
    vjoy_label = (
        f"passthrough to vjoy {vjoy_target['vjoy_device']} axis {vjoy_target['vjoy_input']}"
        if vjoy_target else "no vJoy mapping"
    )
    return f"{side_name} axis {axis_id} ({vjoy_label})"


def collect_root_vjoy_targets(root_action_id, by_id):
    """Walk a root's chain and return the first map-to-vjoy target found."""
    visited = set()
    stack = [root_action_id]
    while stack:
        aid = stack.pop(0)
        if aid in visited:
            continue
        visited.add(aid)
        if aid not in by_id:
            continue
        a = by_id[aid]
        if a.attrib.get("type") == "map-to-vjoy":
            props = {p.findtext("name", ""): p.findtext("value", "") for p in a.findall("property")}
            try:
                return {
                    "vjoy_device": int(props.get("vjoy-device-id", "0")),
                    "vjoy_input": int(props.get("vjoy-input-id", "0")),
                    "vjoy_input_type": props.get("vjoy-input-type", ""),
                }
            except ValueError:
                pass
        for el in a.iter():
            if el.tag == "action-id" and el.text:
                stack.append(el.text)
    return None


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_description_action_text(action_id, description_text, indent="        "):
    body_indent = indent + "    "
    inner_indent = body_indent + "    "
    esc = xml_escape(description_text)
    return (
        f'{indent}<action id="{action_id}" type="description">\n'
        f'{body_indent}<property type="string">\n'
        f'{inner_indent}<name>description</name>\n'
        f'{inner_indent}<value>{esc}</value>\n'
        f'{body_indent}</property>\n'
        f'{body_indent}<property type="string">\n'
        f'{inner_indent}<name>action-label</name>\n'
        f'{inner_indent}<value>Description</value>\n'
        f'{body_indent}</property>\n'
        f'{body_indent}<property type="activation-mode">\n'
        f'{inner_indent}<name>activation-mode</name>\n'
        f'{inner_indent}<value>disallowed</value>\n'
        f'{body_indent}</property>\n'
        f'{indent}</action>\n'
    )


def root_action_has_description_first(root_action, by_id):
    """Return True if the root already has a description as its FIRST child."""
    actions_el = root_action.find("actions")
    if actions_el is None:
        return False
    children = actions_el.findall("action-id")
    if not children or not children[0].text:
        return False
    first_id = children[0].text
    first = by_id.get(first_id)
    return first is not None and first.attrib.get("type") == "description"


def main():
    # Parse JG
    tree = ET.parse(JG_XML)
    root_el = tree.getroot()
    by_id = {a.attrib["id"]: a for a in root_el.findall("./library/action")}

    # Build input index: (device, input-type, input-id, mode) -> root-action-id
    input_index = {}
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid_raw = inp.findtext("input-id", "0")
        try:
            iid = int(iid_raw)
        except ValueError:
            iid = iid_raw  # for non-numeric, unlikely
        mode = inp.findtext("mode", "")
        for ac in inp.findall("action-configuration"):
            ra = ac.findtext("root-action", "")
            input_index[(did, itype, iid, mode)] = ra

    # Parse chart clusters
    clusters = parse_svg_clusters(SVG_PATH)

    # Plan the labels we want to add
    plan = []  # list of (root_action_id, description_text, key_label)

    # ------------------------- Modifier mode buttons -------------------------
    for side, btn, etched in BUTTON_TO_ETCHED:
        did = DEVICE[side]
        key = (did, "button", btn, "Modifier")
        ra = input_index.get(key)
        if not ra:
            continue  # no Modifier-mode binding for this hardware button
        # Look up chart text for this etched name
        if etched.startswith(("MAIN-TRIG", "RAPID-TRIG")):
            chart_id = f"bind.{etched}"
        else:
            chart_id = f"bind.{etched}"
        text = clusters.get(chart_id, "")
        if not text:
            continue
        _, mod_segs = split_chart_text(text)
        if not mod_segs:
            continue
        desc_body = " | ".join(mod_segs)
        # Trigger Up vs Trigger Down for RAPID-TRIG (btn 21=Up, btn 22=Down)
        suffix_hint = ""
        if etched == "RAPID-TRIG-L" and btn == 22:
            suffix_hint = " (Trigger Down)"
        elif etched == "RAPID-TRIG-L" and btn == 21:
            suffix_hint = " (Trigger Up)"
        elif etched == "RAPID-TRIG-R" and btn == 22:
            suffix_hint = " (Trigger Down)"
        elif etched == "RAPID-TRIG-R" and btn == 21:
            suffix_hint = " (Trigger Up)"
        desc_text = f"{etched}{suffix_hint} [Modifier] — {desc_body}"
        plan.append((ra, desc_text, f"{side} btn {btn} Modifier"))

    # ------------------------- Hats -------------------------
    for side in ("L", "R"):
        did = DEVICE[side]
        for mode in ("SCM Mode", "Modifier"):
            ra = input_index.get((did, "hat", 1, mode))
            if not ra:
                continue
            etched = f"{side}-A1"
            combined = hat_combined_description(clusters, side)
            mode_tag = " [Modifier]" if mode == "Modifier" else ""
            # For Modifier hat, prefer just the Modifier-mode segments per direction
            if mode == "Modifier":
                parts = []
                for dir_ in ("up", "down", "left", "right", "press-in"):
                    cid = f"bind.{etched}.{dir_}"
                    if cid not in clusters:
                        continue
                    _, mod_segs = split_chart_text(clusters[cid])
                    if mod_segs:
                        parts.append(f"{dir_}={'/'.join(mod_segs)}")
                if parts:
                    desc_text = f"{etched}{mode_tag} (8-way hat) — {' | '.join(parts)}"
                else:
                    continue
            else:
                # SCM Mode hat: use the non-Modifier portion per direction
                parts = []
                for dir_ in ("up", "down", "left", "right", "press-in"):
                    cid = f"bind.{etched}.{dir_}"
                    if cid not in clusters:
                        continue
                    scm_segs, _ = split_chart_text(clusters[cid])
                    if scm_segs:
                        parts.append(f"{dir_}={'/'.join(scm_segs)}")
                if parts:
                    desc_text = f"{etched} (8-way hat) — {' | '.join(parts)}"
                else:
                    continue
            plan.append((ra, desc_text, f"{side} hat 1 {mode}"))

    # ------------------------- Axes -------------------------
    for side in ("L", "R"):
        did = DEVICE[side]
        for axis_id in range(1, 7):  # axes 1..6
            ra = input_index.get((did, "axis", axis_id, "SCM Mode"))
            if not ra:
                continue
            # Identify the vJoy target this axis maps to
            target = collect_root_vjoy_targets(ra, by_id)
            desc_text = axis_description(clusters, side, axis_id, target)
            plan.append((ra, desc_text, f"{side} axis {axis_id} SCM Mode"))

    # Filter out roots that already have a description first child
    filtered = []
    for ra, desc_text, key_label in plan:
        root_action = by_id.get(ra)
        if root_action is None:
            print(f"  SKIP {key_label}: root-action {ra[:8]}.. not in library")
            continue
        if root_action_has_description_first(root_action, by_id):
            print(f"  SKIP {key_label}: already has description as first child")
            continue
        filtered.append((ra, desc_text, key_label))

    print(f"\nPlanned: {len(filtered)} new description actions\n")
    for ra, desc_text, key_label in filtered:
        print(f"  [{key_label}]  {desc_text[:100]}")

    if not filtered:
        print("Nothing to apply.")
        return

    # ------------------------- Apply: text-based edit -------------------------
    with open(JG_XML, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    new_lib_blocks = []
    for ra, desc_text, _ in filtered:
        new_uuid = str(uuid.uuid4())
        # Insert action-id reference as first child of the root's <actions>
        root_pat = re.compile(
            r'(<action id="' + re.escape(ra) + r'" type="root">\s*<actions>)'
        )
        m = root_pat.search(text)
        if not m:
            print(f"  ! failed to find root {ra[:8]} in text")
            continue
        insert_text = f"\n                <action-id>{new_uuid}</action-id>"
        text = text[: m.end()] + insert_text + text[m.end():]
        new_lib_blocks.append(build_description_action_text(new_uuid, desc_text))

    # Insert all new library blocks before </library>
    lib_close = re.search(r"    </library>", text)
    insert_pos = lib_close.start()
    text = text[:insert_pos] + "".join(new_lib_blocks) + text[insert_pos:]

    # Validate
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        print(f"ERROR: result fails XML parse: {e}", file=sys.stderr)
        sys.exit(1)

    with open(JG_XML, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print(f"\nApplied: {len(filtered)} description actions.")


if __name__ == "__main__":
    main()
