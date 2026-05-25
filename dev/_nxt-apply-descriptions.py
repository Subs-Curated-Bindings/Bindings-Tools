"""
One-off: insert JG R14 'description' library actions for high-confidence
NXT SCM-Mode button bindings, referenced as the first child of each input's
root-action <actions> list.

Approach: do the planning via ET (find UUIDs, build insertion list) but the
edit itself via string ops on the original text, so existing 4-space
indentation is preserved exactly. fix-library-order.py's line-based regex
expects that indentation.

Format Sub picked (em-dash):
    <etched-name>[.<dir>] — <chart description>

Only SCM Mode buttons in this pass. Modifier mode / hats / axes are left
for Sub to add via JG's UI.
"""
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

JG_XML = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT\Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml"

# device-id by side
LEFT_DEV = "7d12d5c0-43ea-11f0-800a-444553540000"
RIGHT_DEV = "ec8bbeb0-4009-11f0-8002-444553540000"
DEVICE = {"L": LEFT_DEV, "R": RIGHT_DEV}

# (side, button-index, etched-name, description) — SCM Mode only
HIGH_CONFIDENCE = [
    ("L", 1,  "MAIN-TRIG-L",         "After Burner Toggle"),
    ("L", 3,  "L-A2",                "[H] Master Mode Cycle Nav & SCM, Operator Mode Cycle"),
    ("L", 4,  "L-B1",                "Precision Aiming, [H] Precision Max Zoom"),
    ("L", 6,  "L-A3.up",             "Flight Ready"),
    ("L", 8,  "L-A3.down",           "Landing Gear, [H] Auto Land, Toggle Docking Mode"),
    ("L", 9,  "L-A3.left",           "Open Doors Toggle"),
    ("L", 10, "L-A3.press-in",       "Request Landing, Request Jumpgate"),
    ("L", 11, "L-A4.up",             "Camera Cycle View"),
    ("L", 12, "L-A4.right",          "Dynamic Zoom, [H] Missile Cinematic Camera"),
    ("L", 13, "L-A4.down",           "[H] Look Behind"),
    ("L", 14, "L-A4.left",           "Head Tracking On/Off"),
    ("L", 15, "L-A4.press-in",       "Freelook"),
    ("L", 16, "L-C1.up",             "Stagger Mode, Remote Turret 1"),
    ("L", 17, "L-C1.right",          "E.S.P. Toggle / Turret E.S.P, Remote Turret 3"),
    ("L", 18, "L-C1.down",           "Turret Gyro Mode, Start/Pause Stop Watch"),
    ("L", 19, "L-C1.left",           "Toggle Lead/Lag Pip / Turret VJoy, Remote Turret 2"),
    ("L", 20, "L-C1.press-in",       "Gimbal Cycle Fixed/Auto, [H] Recenter Turret, Salvage Gimbal Reset"),
    ("L", 21, "RAPID-TRIG-L",        "Trigger Up: Scan Ping, [H] Light Amplification"),
    ("L", 22, "RAPID-TRIG-L",        "Trigger Down: Space Brake"),
    ("L", 23, "L-EN1.up",            "Mining Laser PWR / Scanning Angle / Bomb Range / Tractor Distance (Inc)"),
    ("L", 24, "L-EN1.down",          "Mining Laser PWR / Scanning Angle / Bomb Range / Tractor Distance (Dec)"),
    ("L", 25, "L-SW1.up",            "Close Doors"),
    ("L", 26, "L-SW1.down",          "Open Doors"),
    ("L", 27, "L-F1",                "Request Cargo"),
    ("L", 29, "L-F3",                "Cycle Config / Turret Change Position"),
    ("R", 1,  "MAIN-TRIG-R.stage-1", "Stage 1: Fire Selected Weapon Group, Fire Weapon Group 2"),
    ("R", 2,  "MAIN-TRIG-R.stage-2", "Stage 2: Fire Weapon Group 3"),
    ("R", 3,  "R-A2",                "[H] Select Mining/Salvage Mode, Self Repair All Toggle"),
    ("R", 4,  "R-B1",                "Decoupled Toggle"),
    ("R", 5,  "R-D1",                "[H] VOIP PTT, [DT] Chat Window"),
    ("R", 6,  "R-A3.up",             "Inc. Mining Laser Power (Slow), Fire Fracture, Missile Count Up"),
    ("R", 7,  "R-A3.right",          "Missile Type Next, Fire Right Tool"),
    ("R", 8,  "R-A3.down",           "Missile Count Down, Fire Disintegrate"),
    ("R", 9,  "R-A3.left",           "Missile Type Previous, Fire Left Tool"),
    ("R", 10, "R-A3.press-in",       "Reset Missile Count, Cycle Fracture/Extraction, Beam Axis Toggle"),
    ("R", 11, "R-A4.down",           "[DT] Attackers Target Backward"),
    ("R", 12, "R-A4.right",          "Hostile Target Forward"),
    ("R", 13, "R-A4.up",             "Hostile Target Closest"),
    ("R", 14, "R-A4.left",           "Hostile Target Backward"),
    ("R", 15, "R-A4.press-in",       "EyeTracker Target / Target Under Reticle"),
    ("R", 16, "R-C1.up",             "Mining Module 1, Focus Fracture, Shields Forward"),
    ("R", 17, "R-C1.right",          "Shields Right, Mining Module 2, Focus Right Tool"),
    ("R", 18, "R-C1.down",           "Shields Aft, Focus Disintegration"),
    ("R", 19, "R-C1.left",           "Shields Left, Mining Module 3, Focus Left Tool"),
    ("R", 20, "R-C1.press-in",       "Shields Reset, Focus All Salvage Heads"),
    ("R", 21, "RAPID-TRIG-R",        "Trigger Up: Decoy, [H] Multi Decoy"),
    ("R", 22, "RAPID-TRIG-R",        "Trigger Down: Noise / Multi Decoy"),
    ("R", 23, "R-EN1.up",            "Salvage Beam Spacing Inc"),
    ("R", 24, "R-EN1.down",          "Salvage Beam Spacing Dec"),
    ("R", 25, "R-SW1.up",            "Decoy Burst Size Inc"),
    ("R", 26, "R-SW1.down",          "Decoy Burst Size Dec"),
    ("R", 27, "R-F1",                "Lights"),
    ("R", 28, "R-F2",                "Exit Seat / Turret, Quick Exit"),
    ("R", 29, "R-F3",                "Port Lock Toggle"),
]


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_description_action_text(action_id, description_text, indent="        "):
    """Build a properly-indented <action type='description'> block as text.
    Indent is 8 spaces (the JG library uses 4-space increments)."""
    body_indent = indent + "    "  # 12 spaces for <property>
    inner_indent = body_indent + "    "  # 16 spaces for <name>/<value>
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


def find_root_action_for_input(text, device_id, input_type, input_id, mode):
    """Locate the <input>...</input> matching the predicate and return its root-action UUID."""
    # Match the <input>...</input> block, then check fields inside
    pat = re.compile(
        r'<input>\s*'
        r'<device-id>([^<]+)</device-id>\s*'
        r'<input-type>([^<]+)</input-type>\s*'
        r'<mode>([^<]+)</mode>\s*'
        r'<input-id>([^<]+)</input-id>\s*'
        r'<action-configuration>\s*'
        r'<root-action>([^<]+)</root-action>',
        re.DOTALL,
    )
    for m in pat.finditer(text):
        did, itype, m_mode, iid, ra = m.groups()
        if did == device_id and itype == input_type and m_mode == mode and iid == str(input_id):
            return ra
    return None


def main():
    # newline="" preserves the file's existing line endings instead of letting
    # Windows text-mode translate LF -> CRLF on write. JG R14 profiles ship with
    # LF-only line endings; flipping to CRLF triggered a vjoy-acquisition error
    # at activation time (debugged 2026-05-21 with Sub).
    with open(JG_XML, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    applied = []
    skipped = []
    new_lib_blocks = []

    for side, btn, etched, desc in HIGH_CONFIDENCE:
        did = DEVICE[side]
        ra = find_root_action_for_input(text, did, "button", btn, "SCM Mode")
        if not ra:
            skipped.append((side, btn, etched, "no SCM Mode input found"))
            continue

        # Locate the root action block and its <actions> tag
        # Pattern: <action id="ra" type="root">...<actions>...</actions>
        # Insert <action-id>NEW_UUID</action-id> as first child of <actions>
        root_pat = re.compile(
            r'(<action id="' + re.escape(ra) + r'" type="root">\s*<actions>)',
        )
        m = root_pat.search(text)
        if not m:
            skipped.append((side, btn, etched, f"root-action {ra[:8]}.. not found as <action>"))
            continue

        new_uuid = str(uuid.uuid4())
        description_text = f"{etched} — {desc}"

        # Insert action-id reference at the start of <actions> children.
        # Match 12-space indentation (since <actions> is at 12 spaces in library).
        insert_text = f'\n                <action-id>{new_uuid}</action-id>'
        text = text[:m.end()] + insert_text + text[m.end():]

        # Queue the new description action for appending to library
        new_lib_blocks.append(build_description_action_text(new_uuid, description_text))

        applied.append((side, btn, etched, description_text, new_uuid[:8]))

    # Now append all new description actions at the end of <library>
    # Insert just before the closing tag, on its own line, preserving the
    # blank line / indent that precedes </library> in the original file.
    lib_close_match = re.search(r"    </library>", text)
    if not lib_close_match:
        print("ERROR: </library> not found", file=sys.stderr)
        sys.exit(1)
    insert_pos = lib_close_match.start()
    text = text[:insert_pos] + "".join(new_lib_blocks) + text[insert_pos:]

    # Validate that result is parseable
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        print(f"ERROR: result fails XML parse: {e}", file=sys.stderr)
        sys.exit(1)

    with open(JG_XML, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print(f"Applied: {len(applied)} description actions")
    print(f"Skipped: {len(skipped)}")
    print()
    for side, btn, etched, desc, uid in applied:
        print(f"  {side} btn {btn:>3} -> {desc}  (action-id {uid}..)")
    if skipped:
        print("\nSkipped:")
        for side, btn, etched, reason in skipped:
            print(f"  {side} btn {btn:>3} {etched}: {reason}")


if __name__ == "__main__":
    main()
