#!/usr/bin/env python3
"""
Port the SOL-R Bindings Toolkit (.ps1 + .bat) to the Gunfighter.

The SOL-R Toolkit was itself the genericized NXT port (no VKB-NXT non-EVO
flip; vendor-agnostic diagnostic), so the only stick-specific pieces are the
$StickName, the $Binds MFD table, the layout glob, and user-facing identity
strings. This swaps those and writes the GF Toolkit. Output is LF / no-BOM to
match the source. Idempotent-ish: overwrites the GF Toolkit each run.
"""
import re, sys

SRC_PS1 = "[Enhanced] Dual TM SOL-R/Tools/Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE].ps1"
SRC_BAT = "[Enhanced] Dual TM SOL-R/Tools/Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE].bat"
OUT_PS1 = "[Enhanced] Dual VKB Gunfighter Binds/Tools/Bindings Toolkit [ENH][GF][4.8.1][LIVE].ps1"
OUT_BAT = "[Enhanced] Dual VKB Gunfighter Binds/Tools/Bindings Toolkit [ENH][GF][4.8.1][LIVE].bat"

# GF MFD bind table (hat-based, from the GF's existing Fix MFD Binds script /
# the live layout's vehicle_mfd actionmap). The two soft-select casts are
# double-tap.
GF_BINDS = """$Binds = @(
    @{ name = 'v_mfd_interact_cycle_backwards_short'; input = 'js2_hat2_left' }
    @{ name = 'v_mfd_interact_cycle_forwards_short';  input = 'js2_hat2_right' }
    @{ name = 'v_mfd_movement_down_long';             input = 'js2_hat2_down' }
    @{ name = 'v_mfd_movement_left_long';             input = 'js2_hat2_left' }
    @{ name = 'v_mfd_movement_right_long';            input = 'js2_hat2_right' }
    @{ name = 'v_mfd_movement_up_long';               input = 'js2_hat2_up' }
    @{ name = 'v_mfd_soft_select_cast_left_short';    input = 'js2_hat2_left';  multiTap = '2' }
    @{ name = 'v_mfd_soft_select_cast_right_short';   input = 'js2_hat2_right'; multiTap = '2' }
)"""

# Identity replacements, most-specific first so none double-fire.
REPLS = [
    ("Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE]", "Bindings Toolkit [ENH][GF][4.8.1][LIVE]"),
    ("Joystick Gremlin Profile [ENH][SOL-R 2][4.8.1][LIVE][R14].xml",
     "Joystick Gremlin Profile [ENH][GF][4.8.1][LIVE][R14].xml"),
    ("Fix MFD Binds [ENH][SOL-R 2]", "Fix MFD Binds [ENH][GF]"),
    ("[Enhanced] Dual TM SOL-R", "[Enhanced] Dual VKB Gunfighter Binds"),
    ("layout_ENH_SOL-R2_", "layout_ENH_GF_"),
    ("TM SOL-R", "VKB Gunfighter"),
    ("SOL-R 2", "Gunfighter"),
    ("SOL-R", "Gunfighter"),
]


def port_ps1():
    with open(SRC_PS1, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    # Swap the MFD bind table.
    new, n = re.subn(r"\$Binds = @\(.*?\n\)", lambda _: GF_BINDS, text, count=1, flags=re.S)
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
    text = text.replace("[ENH][SOL-R 2]", "[ENH][GF]")
    if re.search(r"SOL-?R", text, flags=re.I):
        sys.exit("leftover SOL-R in .bat")
    with open(OUT_BAT, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"wrote {OUT_BAT}")


if __name__ == "__main__":
    port_ps1()
    port_bat()
