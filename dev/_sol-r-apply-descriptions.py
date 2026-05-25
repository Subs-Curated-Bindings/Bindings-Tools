"""
Apply chart-cluster descriptions to the TM SOL-R 2 R14 JG profile.

Reads:
  - tools/_sol-r-cluster-assignment.json  (matcher output)
  - tools/_sol-r-cluster-overrides.json   (manual overrides)

Mutation strategy: text-based string surgery for predictable formatting.
  1. Inject N new <action type="description"> blocks just before </library>.
  2. For each input we're describing, splice a <action-id> line into the
     correct position inside the root-action's <actions> block.

Preserves CRLF line endings (the SOL-R 2 profile is CRLF, unlike the LF-only
NXT). The pattern works for both: detect line ending, then use it everywhere.
"""
import json
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

STICK_DIR = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual TM SOL-R"
TOOLS_DIR = r"E:\06. Dev Projects\Subs-Curated-Bindings\tools"
JG_PATH = STICK_DIR + r"\Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
ASSIGNMENT_JSON = TOOLS_DIR + r"\_sol-r-cluster-assignment.json"
OVERRIDES_JSON = TOOLS_DIR + r"\_sol-r-cluster-overrides.json"
CLUSTERS_JSON = TOOLS_DIR + r"\_sol-r-cluster-bodies.json"


def short_device(did):
    if did.startswith("141b1470"):
        return "L"
    if did.startswith("6686f980"):
        return "R"
    return did[:8]


def make_description_text(etched, mode_tag, body):
    parts = [etched]
    if mode_tag == "Modifier":
        parts.append("[Modifier]")
    head = " ".join(parts)
    if body:
        return f"{head} — {body}"
    return head


def xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    with open(ASSIGNMENT_JSON, encoding="utf-8") as f:
        assignments = json.load(f)
    with open(OVERRIDES_JSON, encoding="utf-8") as f:
        overrides = json.load(f)
    with open(CLUSTERS_JSON, encoding="utf-8") as f:
        clusters = json.load(f)

    # Index assignments by (side, itype, iid, mode)
    by_key = {}
    for a in assignments:
        key = (a["side"], a["itype"], a["iid"], a["mode"])
        by_key[key] = a

    # Apply overrides
    overridden = 0
    for k, v in overrides.items():
        if k.startswith("_"):
            continue
        side, itype, iid, mode = k.split("|")
        for (s, t, i, m), a in by_key.items():
            if s == side and t == itype and i == iid and (mode == "*" or mode == m):
                a["cluster"] = v["cluster"]
                a["body_override"] = v.get("body_override", "")
                a["status"] = "OVERRIDE"
                overridden += 1
    print(f"Applied {overridden} manual overrides")

    # Parse XML to discover root_id -> (input identity, has_response_curve)
    # and to identify response-curve action ids.
    tree = ET.parse(JG_PATH)
    root_el = tree.getroot()
    library_actions = {a.attrib["id"]: a for a in root_el.findall("./library/action")}
    response_curve_ids = {aid for aid, a in library_actions.items() if a.attrib.get("type") == "response-curve"}

    # Load layout XML's bound vjoy slots so we can skip JG inputs whose
    # vjoy emissions aren't bound in SC (those inputs are "dead" from SC's
    # perspective and shouldn't get a description — would fail audit Check 2).
    layout_tree = ET.parse(STICK_DIR + r"\layout_ENH_SOL-R2_480_LIVE_exported.xml")
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
                m = re.match(r"js(\d+)_(x|y|z|rotx|roty|rotz)$", inp)
                if m:
                    bound_axis_names.add((int(m.group(1)), m.group(2)))
    print(f"Layout has {len(bound_button_slots)} bound button slots, {len(bound_axis_names)} bound axes")
    VJOY_AXIS_NAMES = {1: "x", 2: "y", 3: "z", 4: "rotx", 5: "roty", 6: "rotz"}

    # For each <input>, gather (root_id, key, cluster, body_text, has_curve_first_child_id)
    work_items = []
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "")
        itype = inp.findtext("input-type", "")
        iid = inp.findtext("input-id", "")
        mode = inp.findtext("mode", "")
        side = short_device(did)
        key = (side, itype, iid, mode)
        a = by_key.get(key)
        if not a or not a.get("cluster"):
            continue
        ac = inp.find("action-configuration")
        if ac is None:
            continue
        rid = ac.findtext("root-action", "")
        if not rid or rid not in library_actions:
            continue
        # find the first response-curve action-id inside root_action's <actions>
        root_action = library_actions[rid]
        actions_el = root_action.find("actions")
        first_curve_aid = None
        for c in actions_el.findall("action-id"):
            if c.text in response_curve_ids:
                first_curve_aid = c.text
                break

        # Skip inputs whose vjoy emissions don't reach any layout rebind.
        # Exception: inputs with ZERO vjoy targets (e.g. change-mode pinky)
        # — those don't trigger audit check 2.
        vts = a.get("vjoy_targets", [])
        if vts:
            any_bound = False
            for vt in vts:
                dev, vinp, vtype = vt
                if vtype == "button" and (dev, vinp) in bound_button_slots:
                    any_bound = True; break
                if vtype == "axis":
                    ax_name = VJOY_AXIS_NAMES.get(vinp, "")
                    if ax_name and (dev, ax_name) in bound_axis_names:
                        any_bound = True; break
            if not any_bound:
                continue  # JG fires only-unbound slots — skip description
        mode_tag = "Modifier" if mode == "Modifier" else ""
        body = a.get("body_override", "")
        if not body:
            acts = a.get("actions", [])
            body = " | ".join(acts[:3]) if acts else ""
        desc_text = make_description_text(a["cluster"], mode_tag, body)
        work_items.append({
            "side": side, "itype": itype, "iid": iid, "mode": mode,
            "root_id": rid, "first_curve_aid": first_curve_aid,
            "desc_text": desc_text, "cluster": a["cluster"],
        })

    print(f"Will add {len(work_items)} descriptions")
    if not work_items:
        print("Nothing to do.")
        return

    # Now load the raw XML text for string mutation
    with open(JG_PATH, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    eol = "\r\n" if "\r\n" in raw[:4096] else "\n"

    # Generate UUIDs for each new description; build XML blocks (indented to match existing actions)
    indent = "        "  # 8 spaces for <action> inside <library>
    pi = "            "  # 12 spaces for <property>
    pi2 = "                "  # 16 spaces for <name>/<value>

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

    # Insert all new blocks just before </library>.
    # The match `\s*</library>` captures `\r\n    </library>`. We want to insert
    # AFTER the leading `\r\n` so the new blocks land between the previous
    # </action> and the `    </library>` indent — keeping the format consistent.
    lib_close_re = re.compile(r"\r?\n(\s*</library>)")
    m = lib_close_re.search(raw)
    if not m:
        print("ERROR: could not find </library>", file=sys.stderr)
        return 1
    # Insert right after the EOL that precedes `    </library>`
    insert_at = m.start() + len(eol)
    raw = raw[:insert_at] + "".join(new_blocks) + raw[insert_at:]

    # For each root action's <actions>, insert <action-id> for the new description.
    # The insertion must come AFTER a response-curve (if present), else as the first child.
    # Find each root_id's <action id="ROOT_ID" type="root"> block and locate its <actions>.

    # First, build a quick map of inserts per root_id, in case multiple inputs share a root.
    inserts_by_root = defaultdict(list)
    for w in work_items:
        inserts_by_root[w["root_id"]].append(w)

    # We'll walk through the raw text by ROOT id. Pattern: <action id="ROOT_ID" type="root">
    # then find the <actions> block within.
    miss = 0
    for rid, items in inserts_by_root.items():
        # Find the root action in raw text
        root_pat = re.compile(
            rf'(<action id="{re.escape(rid)}" type="root">)(.*?)(</action>)',
            re.DOTALL,
        )
        rm = root_pat.search(raw)
        if not rm:
            miss += 1
            continue
        root_open, root_body, root_close = rm.group(1), rm.group(2), rm.group(3)
        # Within root_body, find the <actions>...</actions>
        actions_pat = re.compile(r"(<actions>)(.*?)(</actions>)", re.DOTALL)
        am = actions_pat.search(root_body)
        if not am:
            miss += 1
            continue
        actions_open, actions_body, actions_close = am.group(1), am.group(2), am.group(3)

        # For each item to insert, splice into actions_body.
        # If we have first_curve_aid in the body, insert AFTER its line.
        for w in items:
            new_aid_line = f'                <action-id>{w["desc_id"]}</action-id>{eol}'
            if w["first_curve_aid"] and f'<action-id>{w["first_curve_aid"]}</action-id>' in actions_body:
                # insert immediately after the curve line
                marker = f'<action-id>{w["first_curve_aid"]}</action-id>'
                idx = actions_body.find(marker) + len(marker)
                # skip to end of current line
                eol_idx = actions_body.find(eol, idx)
                if eol_idx == -1:
                    eol_idx = idx
                else:
                    eol_idx += len(eol)
                actions_body = actions_body[:eol_idx] + new_aid_line + actions_body[eol_idx:]
            else:
                # Insert as first child. actions_body starts with leading newline+indent
                # (the whitespace before the first existing child). To insert before that
                # child, prepend `\r\n                <action-id>NEW</action-id>` so the
                # leading newline+indent of the original first child stays intact.
                actions_body = eol + "                " + f'<action-id>{w["desc_id"]}</action-id>' + actions_body

        new_actions = actions_open + actions_body + actions_close
        new_root_body = root_body[:am.start()] + new_actions + root_body[am.end():]
        new_root = root_open + new_root_body + root_close
        raw = raw[:rm.start()] + new_root + raw[rm.end():]

    if miss:
        print(f"WARN: {miss} root_ids not found via regex (skipped).")

    with open(JG_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(raw)

    # Verify file still parses
    try:
        ET.parse(JG_PATH)
        print(f"\nWrote {JG_PATH} — XML parses OK")
    except Exception as e:
        print(f"\nERROR: XML doesn't parse after mutation: {e}")
        return 1

    # Coverage check
    covered = {w["cluster"] for w in work_items}
    missing = set(clusters.keys()) - covered
    print(f"Clusters covered: {len(covered)} / {len(clusters)}")
    if missing:
        print(f"MISSING clusters: {sorted(missing)}")
    else:
        print("ALL chart clusters covered.")


if __name__ == "__main__":
    main()
