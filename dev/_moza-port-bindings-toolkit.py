#!/usr/bin/env python3
"""
Port the SOL-R Bindings Toolkit (.ps1 + .bat) to the MOZA MTQ + MHG.

The SOL-R Toolkit is the genericized NXT port (no VKB-NXT non-EVO flip;
vendor-agnostic diagnostic), so the only stick-specific pieces are the
$StickName, the $Binds MFD table, the layout glob, and user-facing identity
strings. This swaps those and writes the MOZA Toolkit, replacing the old
single-purpose "Fix MFD Binds" script. Output preserves the source's
line endings (newline="").

NOTE on the $Binds table: the MOZA MFD button numbers were RE-NUMBERED in the
2026-06 moniker/layout work, so the old "Fix MFD Binds" script AND the unified
toolkit's MOZA registry both carry STALE numbers (cycle 64/68, select-views
31-38, casts 61/62). This script therefore builds $Binds straight from the LIVE
layout's vehicle_mfd actionmap (ground truth) so it can never drift. Re-run it
whenever the layout changes.
"""
import os, re, sys

HOME = os.path.expanduser("~")
SRC_DIR = f"{HOME}/projects/Subs-Curated-Bindings/[Enhanced] Dual TM SOL-R/Tools"
SRC_PS1 = f"{SRC_DIR}/Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE].ps1"
SRC_BAT = f"{SRC_DIR}/Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE].bat"

MOZA = f"{HOME}/projects/MOZA-MTQ-MHG"
OUT_PS1 = f"{MOZA}/Tools/Bindings Toolkit [ENH][MTQ+MHG][4.8.1][LIVE].ps1"
OUT_BAT = f"{MOZA}/Tools/Bindings Toolkit [ENH][MTQ+MHG][4.8.1][LIVE].bat"
LAYOUT = f"{MOZA}/layout_ENH_MTQ_MHG_480_LIVE_exported.xml"  # pre-rebadge name

# Identity replacements, most-specific first so none double-fire (mirrors the
# VMAX port's ordering).
REPLS = [
    ("Bindings Toolkit [ENH][SOL-R 2][4.8.1][LIVE]", "Bindings Toolkit [ENH][MTQ+MHG][4.8.1][LIVE]"),
    ("Joystick Gremlin Profile [ENH][SOL-R 2][4.8.1][LIVE][R14].xml",
     "Joystick Gremlin Profile [ENH][MTQ+MHG][4.8.1][LIVE][R14].xml"),
    ("Fix MFD Binds [ENH][SOL-R 2]", "Fix MFD Binds [ENH][MTQ+MHG]"),
    ("[Enhanced] Dual TM SOL-R", "[Enhanced] MOZA MTQ + MHG"),
    ("layout_ENH_SOL-R2_", "layout_ENH_MTQ_MHG_"),
    ("TM SOL-R", "MOZA MTQ + MHG"),
    ("SOL-R 2", "MTQ+MHG"),
    ("SOL-R", "MOZA"),
]


def build_binds():
    """Build the $Binds block from the live layout's vehicle_mfd (bound only)."""
    xml = open(LAYOUT, encoding="utf-8").read()
    m = re.search(r'(?s)<actionmap name="vehicle_mfd">(.*?)</actionmap>', xml)
    if not m:
        sys.exit("no vehicle_mfd actionmap in layout")
    pairs = re.findall(r'<action name="([^"]+)">\s*<rebind input="([^"]+)"', m.group(1))
    # keep only actually-bound rows (input has a button number, not bare "js2_")
    bound = [(n, i) for n, i in pairs if re.search(r"_button\d+$", i)]
    if not bound:
        sys.exit("no bound vehicle_mfd entries found")
    w = max(len(n) for n, _ in bound)
    lines = ["$Binds = @("]
    for n, i in bound:
        lines.append(f"    @{{ name = '{n}';{' ' * (w - len(n))}  input = '{i}' }}")
    lines.append(")")
    return "\n".join(lines), len(bound)


def port_ps1():
    binds, n = build_binds()
    with open(SRC_PS1, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    new, c = re.subn(r"\$Binds = @\(.*?\n\)", lambda _: binds, text, count=1, flags=re.S)
    if c != 1:
        sys.exit("could not locate the $Binds block to swap")
    text = new
    for old, rep in REPLS:
        text = text.replace(old, rep)
    leaks = re.findall(r"SOL-?R", text, flags=re.I)
    if leaks:
        sys.exit(f"leftover SOL-R identity strings: {set(leaks)}")
    with open(OUT_PS1, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"wrote {OUT_PS1}  ({n} MFD binds from live layout)")


def port_bat():
    with open(SRC_BAT, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    text = text.replace("[ENH][SOL-R 2]", "[ENH][MTQ+MHG]")
    if re.search(r"SOL-?R", text, flags=re.I):
        sys.exit("leftover SOL-R in .bat")
    with open(OUT_BAT, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"wrote {OUT_BAT}")


if __name__ == "__main__":
    port_ps1()
    port_bat()
