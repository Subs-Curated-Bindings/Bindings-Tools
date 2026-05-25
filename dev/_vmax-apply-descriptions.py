"""
Apply chart-cluster descriptions to the VMAX+AERO R14 JG profile.

Reads:
  - tools/_vmax-cluster-assignment.json  (matcher output)
  - tools/_vmax-cluster-overrides.json   (manual corrections — optional)
  - tools/_vmax-cluster-bodies.json      (for body text)

Mutation strategy: text-based string surgery (same as SOL-R), preserving the
profile's line-ending convention. The VMAX profile is CRLF on Sub's machine —
`newline=""` preserves whatever line endings the file has.
"""
import json
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

REPO = r"E:\06. Dev Projects\Subs-Curated-Bindings"
STICK_DIR = REPO + r"\[Enhanced] Virpil VMAX Throttle + Aeromax-R"
TOOLS_DIR = REPO + r"\tools"
JG_PATH = STICK_DIR + r"\Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.0][LIVE][R14].xml"
LAYOUT_PATH = STICK_DIR + r"\layout_ENH_VMAX_AERO_480_LIVE_exported.xml"
ASSIGNMENT_JSON = TOOLS_DIR + r"\_vmax-cluster-assignment.json"
OVERRIDES_JSON = TOOLS_DIR + r"\_vmax-cluster-overrides.json"
CLUSTERS_JSON = TOOLS_DIR + r"\_vmax-cluster-bodies.json"


def xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def make_description_text(etched, mode_tag, body):
    parts = [etched]
    if mode_tag == "Modifier":
        parts.append("[Modifier]")
    head = " ".join(parts)
    if body:
        return f"{head} — {body}"
    return head


def main():
    with open(ASSIGNMENT_JSON, encoding="utf-8") as f:
        assignments = json.load(f)
    try:
        with open(OVERRIDES_JSON, encoding="utf-8") as f:
            overrides = json.load(f)
    except FileNotFoundError:
        overrides = {}
    with open(CLUSTERS_JSON, encoding="utf-8") as f:
        clusters = json.load(f)

    by_key = {}
    for a in assignments:
        key = (a["device_short"], a["itype"], a["iid"], a["mode"])
        by_key[key] = a

    # Apply overrides: key format "device|itype|iid|mode" (mode * for all)
    overridden = 0
    for k, v in overrides.items():
        if k.startswith("_"):
            continue
        try:
            dev, itype, iid, mode = k.split("|")
        except ValueError:
            continue
        for (d, t, i, m), a in by_key.items():
            if d == dev and t == itype and i == iid and (mode == "*" or mode == m):
                a["cluster"] = v["cluster"]
                a["body_override"] = v.get("body_override", "")
                a["status"] = "OVERRIDE"
                overridden += 1
    print(f"Applied {overridden} manual overrides")

    # Parse JG XML to find root_id -> input metadata + identify response-curve action ids
    tree = ET.parse(JG_PATH)
    root_el = tree.getroot()
    library_actions = {a.attrib["id"]: a for a in root_el.findall("./library/action")}
    response_curve_ids = {aid for aid, a in library_actions.items() if a.attrib.get("type") == "response-curve"}

    # Load layout-bound vjoy slots for skip-unbound logic
    layout_tree = ET.parse(LAYOUT_PATH)
    bound_button_slots = set()
    bound_axis_names = set()
    for am in layout_tree.getroot().findall("./actionmap"):
        for act in am.findall("action"):
            for r in act.findall("rebind"):
                inp = r.attrib.get("input", "")
                m = re.match(r"js(\d+)_button(\d+)$", inp)
                if m:
                    bound_button_slots.add((int(m.group(1)), int(m.group(2))))
                    continue
                m = re.match(r"js(\d+)_(x|y|z|rx|ry|rz|rotx|roty|rotz|throttle|slider1|slider2)$", inp)
                if m:
                    bound_axis_names.add((int(m.group(1)), m.group(2)))
    # vjoy axis-id 4/5/6 in SC layout XML is named rotx/roty/rotz, not rx/ry/rz
    VJOY_AXIS_NAMES = {1: "x", 2: "y", 3: "z", 4: "rotx", 5: "roty", 6: "rotz", 7: "slider1", 8: "slider2"}

    # Build work items: one per (input × first action-configuration). Each input may
    # have multiple action-configurations (axis with multiple button cfgs); for the
    # description action, we only attach to the FIRST root.
    work_items = []
    skipped_no_cluster = 0
    skipped_unbound = 0
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        key = (did[:8], itype, iid, mode)
        a = by_key.get(key)
        if not a or not a.get("cluster"):
            skipped_no_cluster += 1
            continue

        # Inputs with vjoy emissions but no layout-bound emission are skipped
        vts = a.get("vjoy_targets", [])
        if vts:
            any_bound = False
            for vt in vts:
                if isinstance(vt, list):
                    dev, vinp, vtype = vt
                else:
                    dev, vinp, vtype = vt
                if vtype == "button" and (dev, vinp) in bound_button_slots:
                    any_bound = True; break
                if vtype == "axis":
                    ax = VJOY_AXIS_NAMES.get(vinp, "")
                    if ax and (dev, ax) in bound_axis_names:
                        any_bound = True; break
            if not any_bound:
                skipped_unbound += 1
                continue

        ac = inp.find("action-configuration")
        if ac is None:
            continue
        rid = ac.findtext("root-action", "")
        if not rid or rid not in library_actions:
            continue
        root_action = library_actions[rid]
        actions_el = root_action.find("actions")
        first_curve_aid = None
        if actions_el is not None:
            for c in actions_el.findall("action-id"):
                if c.text in response_curve_ids:
                    first_curve_aid = c.text
                    break

        mode_tag = "Modifier" if "Modifier" in mode else ""
        body = a.get("body_override", "")
        if not body:
            # Prefer chart cluster body, fall back to action list
            cluster_body = clusters.get(a["cluster"], "")
            if cluster_body:
                # Trim noisy chart syntax for the description
                body = re.sub(r"\s+", " ", cluster_body).strip()
                # cap at 250 chars to avoid silly-long action-labels
                if len(body) > 250:
                    body = body[:247] + "..."
            else:
                acts = a.get("actions", [])
                body = " | ".join(acts[:3]) if acts else ""

        desc_text = make_description_text(a["cluster"], mode_tag, body)
        work_items.append({
            "device": did, "itype": itype, "iid": iid, "mode": mode,
            "root_id": rid, "first_curve_aid": first_curve_aid,
            "desc_text": desc_text, "cluster": a["cluster"],
        })

    print(f"Will add {len(work_items)} descriptions (skipped: {skipped_no_cluster} no-cluster, {skipped_unbound} unbound)")
    if not work_items:
        return

    # Mutate raw XML text
    with open(JG_PATH, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    eol = "\r\n" if "\r\n" in raw[:4096] else "\n"

    # Idempotency: wipe any existing description actions before adding new ones.
    # Without this, running apply twice doubles up every description because we
    # only ever APPEND to <actions> lists, never check for existing entries.
    desc_pat = re.compile(
        r'(\s*)<action id="([^"]+)" type="description">(?:.*?)</action>\s*',
        re.DOTALL,
    )
    existing_desc_ids = [m.group(2) for m in desc_pat.finditer(raw)]
    if existing_desc_ids:
        raw, n_blocks = desc_pat.subn("", raw)
        n_refs = 0
        for did in existing_desc_ids:
            ref_pat = re.compile(
                r"[ \t]*<action-id>" + re.escape(did) + r"</action-id>\s*\n",
            )
            raw, count = ref_pat.subn("", raw)
            n_refs += count
        print(f"Wiped {n_blocks} existing description actions ({n_refs} references) before re-applying")

    indent = "        "
    pi = "            "
    pi2 = "                "

    new_blocks = []
    for w in work_items:
        new_id = str(uuid.uuid4())
        w["desc_id"] = new_id
        block = (
            f'{indent}<action id="{new_id}" type="description">{eol}'
            f'{pi}<property type="string">{eol}'
            f'{pi2}<name>description</name>{eol}'
            f'{pi2}<value>{xml_escape(w["desc_text"])}</value>{eol}'
            f'{pi}</property>{eol}'
            f'{pi}<property type="string">{eol}'
            f'{pi2}<name>action-label</name>{eol}'
            f'{pi2}<value>Description</value>{eol}'
            f'{pi}</property>{eol}'
            f'{pi}<property type="activation-mode">{eol}'
            f'{pi2}<name>activation-mode</name>{eol}'
            f'{pi2}<value>disallowed</value>{eol}'
            f'{pi}</property>{eol}'
            f'{indent}</action>{eol}'
        )
        new_blocks.append(block)

    lib_close_re = re.compile(r"\r?\n(\s*</library>)")
    m = lib_close_re.search(raw)
    if not m:
        print("ERROR: could not find </library>", file=sys.stderr)
        return 1
    insert_at = m.start() + len(eol)
    raw = raw[:insert_at] + "".join(new_blocks) + raw[insert_at:]

    # For each root action's <actions>, splice in <action-id> for the new description
    inserts_by_root = defaultdict(list)
    for w in work_items:
        inserts_by_root[w["root_id"]].append(w)

    miss = 0
    for rid, items in inserts_by_root.items():
        root_pat = re.compile(
            rf'(<action id="{re.escape(rid)}" type="root">)(.*?)(</action>)',
            re.DOTALL,
        )
        rm = root_pat.search(raw)
        if not rm:
            miss += 1
            continue
        root_open, root_body, root_close = rm.group(1), rm.group(2), rm.group(3)
        actions_pat = re.compile(r"(<actions>)(.*?)(</actions>)", re.DOTALL)
        am = actions_pat.search(root_body)
        if not am:
            miss += 1
            continue
        actions_open, actions_body, actions_close = am.group(1), am.group(2), am.group(3)

        for w in items:
            new_aid_line = f'                <action-id>{w["desc_id"]}</action-id>{eol}'
            if w["first_curve_aid"] and f'<action-id>{w["first_curve_aid"]}</action-id>' in actions_body:
                marker = f'<action-id>{w["first_curve_aid"]}</action-id>'
                idx = actions_body.find(marker) + len(marker)
                eol_idx = actions_body.find(eol, idx)
                if eol_idx == -1:
                    eol_idx = idx
                else:
                    eol_idx += len(eol)
                actions_body = actions_body[:eol_idx] + new_aid_line + actions_body[eol_idx:]
            else:
                actions_body = eol + "                " + f'<action-id>{w["desc_id"]}</action-id>' + actions_body

        new_actions = actions_open + actions_body + actions_close
        new_root_body = root_body[:am.start()] + new_actions + root_body[am.end():]
        new_root = root_open + new_root_body + root_close
        raw = raw[:rm.start()] + new_root + raw[rm.end():]

    if miss:
        print(f"WARN: {miss} root_ids not found via regex")

    with open(JG_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(raw)

    try:
        ET.parse(JG_PATH)
        print(f"\nWrote {JG_PATH} — XML parses OK")
    except Exception as e:
        print(f"\nERROR: XML doesn't parse: {e}")
        return 1

    covered = {w["cluster"] for w in work_items}
    missing = set(clusters.keys()) - covered
    print(f"Clusters covered by descriptions: {len(covered)} / {len(clusters)}")
    if missing:
        print(f"MISSING clusters (no description action references them):")
        for c in sorted(missing):
            print(f"  {c}")


if __name__ == "__main__":
    main()
