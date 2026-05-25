"""
Add the final 5 layout XML rebinds resolving the right-side modifier-mode
silent-broken binds and L-F2 (VTOL Cycle).

Chart intent (per Sub):
  L-F2                     -> v_transform_cycle (VTOL Cycle, only)
  R-A3.right [Modifier]    -> v_salvage_cycle_modifiers_right (only,
                              not the missile/fire actions also on SCM Mode btn 7)
  R-A3.down [Modifier]     -> v_salvage_cycle_modifiers_structural
                              + v_decrease_mining_throttle  (Dec Mining Laser Power Slow)
  R-A3.left [Modifier]     -> v_salvage_cycle_modifiers_left (only)

Preserves CRLF line endings, 3-space rebind indent.
"""
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

LAYOUT_XML = r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gladiator NXT\layout_ENH_NXT_480_LIVE_exported.xml"

ADDS = [
    # L-F2 (button 28) — VTOL Cycle
    ("v_transform_cycle",                  "js1_button17"),
    # R-A3.right [Modifier] — Right Modifier Cycle only
    ("v_salvage_cycle_modifiers_right",    "js2_button42"),
    # R-A3.down [Modifier] — Structural Modes + Dec Mining Laser Power
    ("v_salvage_cycle_modifiers_structural", "js2_button43"),
    ("v_decrease_mining_throttle",         "js2_button43"),
    # R-A3.left [Modifier] — Left Modifier Cycle only
    ("v_salvage_cycle_modifiers_left",     "js2_button44"),
]


def main():
    with open(LAYOUT_XML, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    rebind_indent = "   "
    applied = []
    for action_name, new_input in ADDS:
        action_pat = re.compile(
            r'(  <action name="' + re.escape(action_name) + r'">\r\n)'
            r'(   <rebind input="[^"]+"[^/>]*?/?>\r\n)',
        )
        m = action_pat.search(text)
        if not m:
            print(f"  SKIP {action_name}: pattern did not match")
            continue
        # Idempotent check
        action_block_end = text.find("  </action>", m.end())
        block = text[m.end():action_block_end]
        if f'input="{new_input}"' in block:
            print(f"  SKIP {action_name}: already has rebind for {new_input}")
            continue
        new_line = f'{rebind_indent}<rebind input="{new_input}"/>\r\n'
        text = text[:m.end()] + new_line + text[m.end():]
        applied.append((action_name, new_input))
        print(f"  ADDED  {action_name}  <-  {new_input}")

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
