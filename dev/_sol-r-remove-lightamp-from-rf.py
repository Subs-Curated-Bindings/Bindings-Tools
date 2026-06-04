#!/usr/bin/env python3
"""Remove the shared Light Amp Toggle macro from button 27's (L-RF rapid-fire)
tempo hold. The macro (8b4f1c2e) is shared with button 19's hold, which keeps
it. We only un-reference it from button 27's tempo (7d9a4e6f), located via its
unique short-action id (3bef66e4 = L-RF.up.tap). Preserves line endings.
"""
import sys
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
RF_TAP = "<action-id>3bef66e4-ab7f-4dce-8030-14757bbf4f73</action-id>"   # button 27 tempo short-action
MACRO = "<action-id>8b4f1c2e-0d35-4f87-a1c3-2e9b6a3f7d12</action-id>"     # Light Amp Toggle macro ref

text = JG.read_text(encoding="utf-8", newline="")

i = text.index(RF_TAP)                 # locate button 27's tempo
j = text.index(MACRO, i)               # its long-actions macro ref (first after the tap)
between = text[i:j]
assert "<long-actions>" in between and "</short-actions>" in between, "macro ref not in button 27 long-actions"
assert text.count(MACRO) == 2, f"expected 2 macro refs (btn19 + btn27), found {text.count(MACRO)}"

line_start = text.rfind("\n", 0, j) + 1
line_end = text.index("\n", j) + 1     # include trailing newline

print("--- button 27 tempo block BEFORE ---")
print(text[i:line_end + 30])

new = text[:line_start] + text[line_end:]

if "--apply" in sys.argv:
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    print("\nAPPLIED. Macro refs remaining (should be 1, button 19):", new.count(MACRO))
else:
    print("\n--- button 27 tempo block AFTER (preview) ---")
    k = new.index(RF_TAP)
    print(new[k:k + 220])
    print("\n(dry-run — pass --apply to write)")
