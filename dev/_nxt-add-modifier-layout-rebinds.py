"""
Add layout XML rebinds wiring js1_button36 and js1_button38 to the SC actions
that L-A4.up/L-A4.down should fire in Modifier mode.

Per Sub's chart intent: L-A4 [Modifier] is the FINE-control variant for
Scanning Angle / Bomb HUD Range / Tractor Distance (3 actions, NOT the
4th encoder action which is Mining Throttle / Mining Laser Power).

Adds:
  v_inc_scan_focus_level            <- js1_button36  (Inc Scanning Angle)
  v_weapon_bombing_hud_range_increase <- js1_button36  (Bombs - Increase HUD Range)
  tractor_beam_vehicle_increase_distance <- js1_button36 (Salvage Tractor inc dist)
  tractor_beam_increase_distance    <- js1_button36  (On-foot Tractor inc dist)

  v_dec_scan_focus_level            <- js1_button38  (Dec Scanning Angle)
  v_weapon_bombing_hud_range_decrease <- js1_button38
  tractor_beam_vehicle_decrease_distance <- js1_button38
  tractor_beam_decrease_distance    <- js1_button38

Preserves CRLF line endings, no BOM.
"""
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

LAYOUT_XML = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT\layout_ENH_NXT_480_LIVE_exported.xml"

ADDS = [
    # (action_name, new_input)
    ("v_inc_scan_focus_level",                  "js1_button36"),
    ("v_weapon_bombing_hud_range_increase",     "js1_button36"),
    ("tractor_beam_vehicle_increase_distance",  "js1_button36"),
    ("tractor_beam_increase_distance",          "js1_button36"),
    ("v_dec_scan_focus_level",                  "js1_button38"),
    ("v_weapon_bombing_hud_range_decrease",     "js1_button38"),
    ("tractor_beam_vehicle_decrease_distance",  "js1_button38"),
    ("tractor_beam_decrease_distance",          "js1_button38"),
]


def main():
    # Read with newline="" to preserve CRLF on round-trip
    with open(LAYOUT_XML, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    # Layout XML uses 3-space indent for <rebind> per the format inspection.
    rebind_indent = "   "

    applied = []
    for action_name, new_input in ADDS:
        # Pattern: locate the <action name="X"> ... <rebind ... /> ... and capture
        # the existing rebind line so we can insert a new sibling line immediately
        # after it (preserving CRLF and 3-space indent).
        action_pat = re.compile(
            r'(  <action name="' + re.escape(action_name) + r'">\r\n)'
            r'(   <rebind input="[^"]+"[^/>]*?/?>\r\n)',
        )
        m = action_pat.search(text)
        if not m:
            print(f"  SKIP {action_name}: pattern did not match")
            continue
        # Check whether the new input is already present in this action
        # (idempotent — re-run shouldn't double-add)
        # Find the </action> after our match start; scan that block.
        action_block_end = text.find("  </action>", m.end())
        block = text[m.end():action_block_end]
        if f'input="{new_input}"' in block:
            print(f"  SKIP {action_name}: already has rebind for {new_input}")
            continue
        new_rebind_line = f'{rebind_indent}<rebind input="{new_input}"/>\r\n'
        text = text[:m.end()] + new_rebind_line + text[m.end():]
        applied.append((action_name, new_input))
        print(f"  ADDED  {action_name}  <-  {new_input}")

    # Validate XML parses
    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        print(f"ERROR: XML parse failed: {e}", file=sys.stderr)
        sys.exit(1)

    with open(LAYOUT_XML, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    print(f"\nApplied {len(applied)} rebinds.")


if __name__ == "__main__":
    main()
