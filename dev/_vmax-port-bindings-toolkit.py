#!/usr/bin/env python3
"""
Port the SOL-R Bindings Toolkit (.ps1 + .bat) to the Virpil VMAX + Aeromax-R.

The SOL-R Toolkit is the genericized NXT port (no VKB-NXT non-EVO flip;
vendor-agnostic diagnostic), so the only stick-specific pieces are the
$StickName, the $Binds MFD table, the layout glob, and user-facing identity
strings. This swaps those and writes the VMAX Toolkit, replacing the old
single-purpose "Fix MFD Binds" script. Output preserves the source's
CRLF / no-BOM endings. Overwrites the VMAX Toolkit each run.

The VMAX MFD table was verified against the live
layout_ENH_VMAX_AERO_481_LIVE_exported.xml vehicle_mfd actionmap (2026-06-12):
7 binds on the Aeromax R-M1 mini-stick cluster + R-B6, no multi-tap / no
soft-select casts (VMAX uses quick-action repair-all where the NXT/GF use the
soft_select pair).
"""
import re, sys

SRC_PS1 = "[Enhanced] Dual TM SOL-R/Tools/Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE].ps1"
SRC_BAT = "[Enhanced] Dual TM SOL-R/Tools/Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE].bat"
OUT_PS1 = "[Enhanced] Virpil VMAX Throttle + Aeromax-R/Tools/Bindings Toolkit [ENH][VMAX+AERO][4.8.1][LIVE].ps1"
OUT_BAT = "[Enhanced] Virpil VMAX Throttle + Aeromax-R/Tools/Bindings Toolkit [ENH][VMAX+AERO][4.8.1][LIVE].bat"

# VMAX MFD bind table, verified against the live layout's vehicle_mfd block.
VMAX_BINDS = """$Binds = @(
    @{ name = 'v_mfd_interact_cycle_backwards_short'; input = 'js2_button30' }
    @{ name = 'v_mfd_interact_cycle_forwards_short';  input = 'js2_button28' }
    @{ name = 'v_mfd_movement_down_long';             input = 'js2_button29' }
    @{ name = 'v_mfd_movement_left_long';             input = 'js2_button30' }
    @{ name = 'v_mfd_movement_right_long';            input = 'js2_button28' }
    @{ name = 'v_mfd_movement_up_long';               input = 'js2_button27' }
    @{ name = 'v_mfd_quick_action_repair_all';        input = 'js2_button13' }
)"""

# Identity replacements, most-specific first so none double-fire.
REPLS = [
    ("Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE]", "Bindings Toolkit [ENH][VMAX+AERO][4.8.1][LIVE]"),
    ("Joystick Gremlin Profile [ENH][SOL-R 2][4.8.1][LIVE][R14].xml",
     "Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.1][LIVE][R14].xml"),
    ("Fix MFD Binds [ENH][SOL-R 2]", "Fix MFD Binds [ENH][VMAX+AERO]"),
    ("[Enhanced] Dual TM SOL-R", "[Enhanced] Virpil VMAX Throttle + Aeromax-R"),
    ("layout_ENH_SOL-R2_", "layout_ENH_VMAX_AERO_"),
    ("TM SOL-R", "Virpil VMAX+AERO"),
    ("SOL-R 2", "VMAX+AERO"),
    ("SOL-R", "VMAX+AERO"),
]


def port_ps1():
    with open(SRC_PS1, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    # Swap the MFD bind table.
    new, n = re.subn(r"\$Binds = @\(.*?\n\)", lambda _: VMAX_BINDS, text, count=1, flags=re.S)
    if n != 1:
        sys.exit("could not locate the $Binds block to swap")
    text = new
    # Swap identity strings.
    for old, rep in REPLS:
        text = text.replace(old, rep)
    # Verify no SOL-R identity leaked through.
    leaks = re.findall(r"SOL-?R", text, flags=re.I)
    if leaks:
        sys.exit(f"leftover SOL-R identity strings: {set(leaks)}")
    with open(OUT_PS1, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"wrote {OUT_PS1}")


def port_bat():
    with open(SRC_BAT, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    text = text.replace("[ENH][SOL-R 2]", "[ENH][VMAX+AERO]")
    if re.search(r"SOL-?R", text, flags=re.I):
        sys.exit("leftover SOL-R in .bat")
    with open(OUT_BAT, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"wrote {OUT_BAT}")


if __name__ == "__main__":
    port_ps1()
    port_bat()
