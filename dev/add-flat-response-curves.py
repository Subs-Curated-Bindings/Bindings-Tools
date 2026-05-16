"""
Add a flat (pass-through, identity-curve) response-curve action to every
axis input in a JG R14 profile that doesn't already have one.

The new response-curve action is:
  - 2 control points: (-1, -1) and (1, 1) — identity, no shaping
  - no deadzone (low=-1, center=0/0, high=1)
  - curve-type: PiecewiseLinear
  - action-label: "Response Curve" (matches JG's default)
  - activation-mode: disallowed

For each axis input that lacks a response curve at its root:
  1. Generate a fresh UUID for the new response-curve action
  2. Insert the action definition at the TOP of <library> (preserves the
     library dependency order — primitives before any root that uses them)
  3. Prepend the new action-id at the TOP of the root's <actions> list
     (preserves the response-curve-before-mapping order)

Detection rule: an axis "has" a response curve if its root's <actions> list
references any action whose type=response-curve. We only consider
<action-configuration> blocks whose <behavior>axis</behavior> (skips
axis-as-button entries).

Preserves UTF-8 BOM. Writes back as UTF-8 with BOM if the input had one.

Usage:
  python add-flat-response-curves.py "<profile.xml>"          # apply
  python add-flat-response-curves.py "<profile.xml>" --dry-run
"""
import argparse
import re
import sys
import uuid
import xml.etree.ElementTree as ET


RESPONSE_CURVE_TEMPLATE = """        <action id="{aid}" type="response-curve">
            <deadzone>
                <property type="float">
                    <name>low</name>
                    <value>-1.0</value>
                </property>
                <property type="float">
                    <name>center-low</name>
                    <value>0.0</value>
                </property>
                <property type="float">
                    <name>center-high</name>
                    <value>0.0</value>
                </property>
                <property type="float">
                    <name>high</name>
                    <value>1.0</value>
                </property>
            </deadzone>
            <control-points>
                <property type="point2d">
                    <name>point</name>
                    <value>-1.0,-1.0</value>
                </property>
                <property type="point2d">
                    <name>point</name>
                    <value>1.0,1.0</value>
                </property>
            </control-points>
            <property type="string">
                <name>curve-type</name>
                <value>PiecewiseLinear</value>
            </property>
            <property type="string">
                <name>action-label</name>
                <value>Response Curve</value>
            </property>
            <property type="activation-mode">
                <name>activation-mode</name>
                <value>disallowed</value>
            </property>
        </action>
"""


def find_axes_needing_curve(root_el):
    """Returns list of (root_action_id, axis_label) for axes that need a curve."""
    library = root_el.find("library")
    id_to_type = {a.get("id"): a.get("type") for a in library.findall("action")}
    id_to_action = {a.get("id"): a for a in library.findall("action")}

    needs = []
    for inp in root_el.findall("./inputs/input"):
        if inp.findtext("input-type") != "axis":
            continue
        device_id = inp.findtext("device-id") or "?"
        input_id = inp.findtext("input-id") or "?"
        mode = inp.findtext("mode") or "?"
        for ac in inp.findall("action-configuration"):
            if ac.findtext("behavior") != "axis":
                continue
            root_aid = ac.findtext("root-action")
            root_action = id_to_action.get(root_aid)
            if root_action is None:
                continue
            has_curve = any(
                id_to_type.get(aid.text) == "response-curve"
                for aid in root_action.findall("./actions/action-id")
            )
            if not has_curve:
                label = f"dev=...{device_id[-12:]}  axis {input_id}  mode={mode}"
                needs.append((root_aid, label))
    return needs


def apply(profile_path, dry_run=False):
    # Parse for structure
    tree = ET.parse(profile_path)
    root_el = tree.getroot()
    needs = find_axes_needing_curve(root_el)

    if not needs:
        print("All axes already have response curves. Nothing to do.")
        return 0

    print(f"Will add {len(needs)} flat response curve(s):")
    for _, label in needs:
        print(f"  {label}")

    if dry_run:
        print("(dry-run) No file changes.")
        return 0

    # Read preserving BOM
    with open(profile_path, "rb") as f:
        raw = f.read()
    has_bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")

    # Detect line-ending style; use it for all inserts so output matches input
    eol = "\r\n" if "\r\n" in text[:4096] else "\n"
    rc_template = RESPONSE_CURVE_TEMPLATE.replace("\n", eol)

    # Generate one new response-curve UUID per axis-root that needs it
    new_actions_xml = []  # block strings to insert at top of <library>
    pending_prepend = []  # (root_aid, new_action_id) pairs to prepend into root.actions

    for root_aid, _label in needs:
        new_aid = str(uuid.uuid4())
        new_actions_xml.append(rc_template.format(aid=new_aid))
        pending_prepend.append((root_aid, new_aid))

    # Insert all new response-curve actions at the top of <library>.
    # <library> indent is 4 spaces; action blocks inside are 8 spaces.
    lib_open_pat = re.compile(r"(    <library>\r?\n)")
    m = lib_open_pat.search(text)
    if not m:
        print("ERROR: could not locate <library> opening tag", file=sys.stderr)
        return 1
    insert_at = m.end()
    text = text[:insert_at] + "".join(new_actions_xml) + text[insert_at:]

    # Prepend each new action-id at the top of its target root's <actions>.
    # The root pattern looks like:
    #     <action id="<root_aid>" type="root">
    #         <actions>
    #             <action-id>...</action-id>
    #             ...
    #         </actions>
    # We find each root's <actions> opening tag and inject a new line right after.
    for root_aid, new_aid in pending_prepend:
        root_block_pat = re.compile(
            r'(<action id="' + re.escape(root_aid) + r'" type="root">\s*\r?\n\s*<actions>\r?\n)'
        )
        new_text, n = root_block_pat.subn(
            lambda mm: mm.group(1) + f"                <action-id>{new_aid}</action-id>{eol}",
            text,
            count=1,
        )
        if n == 0:
            print(f"ERROR: could not locate root action {root_aid} in text", file=sys.stderr)
            return 1
        text = new_text

    # Write back
    out = text.encode("utf-8")
    if has_bom and not out.startswith(b"\xef\xbb\xbf"):
        out = b"\xef\xbb\xbf" + out
    with open(profile_path, "wb") as f:
        f.write(out)

    # Verify parse
    ET.parse(profile_path)
    print(f"\nAdded {len(needs)} flat response curve(s). XML parses OK.")
    return 0


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("profile", help="Path to the JG R14 profile XML")
    p.add_argument("--dry-run", action="store_true", help="Report only; do not modify")
    args = p.parse_args()
    sys.exit(apply(args.profile, args.dry_run))


if __name__ == "__main__":
    main()
