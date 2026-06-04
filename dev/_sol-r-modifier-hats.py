#!/usr/bin/env python3
"""Modifier-layer POV hats -> hat-buttons (the +50 slots).

LEFT  (input exists): replace the leftover map-to-vjoy on L hat 1 [Modifier]
      with a hat-buttons -> vjoy1 N=82/E=83/S=84/W=81.
RIGHT (no input yet): create a new R hat 1 [Modifier] input + root + hat-buttons
      -> vjoy2 N=82/E=83/S=84/W=81 (else it would inherit SCM's 31-34 in Modifier).

Clones the known-good left SCM hat-buttons (+children) as templates; fresh IDs.
Old left map-to-vjoy becomes an orphan (final cleanup prunes it).
Dry-run by default; --apply to write. Preserves line endings. Idempotent guard.
"""
import sys, re, uuid
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
TPL_HAT = "1b3a5733-ca77-40a9-8e51-7023d3e9f127"
TPL_KIDS = {"North": "41006a78-4685-4c7b-951d-7f1005462202",
            "East":  "4cd48623-b5fd-4fc2-b9f3-c95685883be7",
            "South": "a07a7a17-d4c1-4997-974b-aa7e1f550bd5",
            "West":  "a8b891c2-9ff0-4ace-b107-a5dffea09d98"}
MOD_BTN = {"North": 82, "East": 83, "South": 84, "West": 81}
LMOD_ROOT = "d548c76f-4944-442d-b301-44e682bc9df1"   # left Modifier hat root (exists)
RSCM_ROOT = "7988342f-b735-410a-a2ab-6d2b6b897e7b"   # right SCM hat root (clone for R Modifier root)

text = JG.read_text(encoding="utf-8", newline="")
root = ET.fromstring(text)
by_id = {a.get("id"): a for a in root.iter("action")}

# guards
lroot = by_id[LMOD_ROOT]
l_old_child = lroot.find("actions").findtext("action-id")
if by_id[l_old_child].get("type") == "hat-buttons":
    sys.exit("Left Modifier hat already converted.")
for inp in root.iter("input"):
    if (inp.findtext("device-id") == "6686f980-1082-11f0-8008-444553540000"
            and inp.findtext("input-type") == "hat" and inp.findtext("mode") == "Modifier"):
        sys.exit("Right Modifier hat already exists.")


def block(aid):
    i = text.index(f'<action id="{aid}"')
    return text[i:text.index("</action>", i) + len("</action>")]


def make_hat(vjoy_dev):
    nk = {d: str(uuid.uuid4()) for d in TPL_KIDS}
    blocks = []
    for d, old in TPL_KIDS.items():
        b = block(old).replace(f'<action id="{old}"', f'<action id="{nk[d]}"')
        b = re.sub(r"(<name>vjoy-device-id</name>\s*<value>)\d+(</value>)", rf"\g<1>{vjoy_dev}\g<2>", b)
        b = re.sub(r"(<name>vjoy-input-id</name>\s*<value>)\d+(</value>)", rf"\g<1>{MOD_BTN[d]}\g<2>", b)
        blocks.append(b)
    hid = str(uuid.uuid4())
    hb = block(TPL_HAT).replace(f'<action id="{TPL_HAT}"', f'<action id="{hid}"')
    for d, old in TPL_KIDS.items():
        hb = hb.replace(f"<action-id>{old}</action-id>", f"<action-id>{nk[d]}</action-id>")
    return blocks + [hb], hid


# LEFT: build hat, will repoint existing root
l_blocks, l_hat = make_hat(1)
# RIGHT: build hat + new root + new input
r_blocks, r_hat = make_hat(2)
r_root_id = str(uuid.uuid4())
r_scm_child = by_id[RSCM_ROOT].find("actions").findtext("action-id")
r_root = block(RSCM_ROOT).replace(f'<action id="{RSCM_ROOT}"', f'<action id="{r_root_id}"')
r_root = r_root.replace(f"<action-id>{r_scm_child}</action-id>", f"<action-id>{r_hat}</action-id>")
# new right Modifier input (clone right SCM hat input)
i = text.index("<root-action>" + RSCM_ROOT)
istart = text.rfind("<input>", 0, i)
iend = text.index("</input>", i) + len("</input>")
r_input = (text[istart:iend].replace("<mode>SCM Mode</mode>", "<mode>Modifier</mode>")
           .replace(f"<root-action>{RSCM_ROOT}</root-action>", f"<root-action>{r_root_id}</root-action>"))

print("=== LEFT Modifier hat: convert root %s ===" % LMOD_ROOT[:8])
print(f"   actions child {l_old_child[:8]} (old map-to-vjoy, -> orphan)  =>  new hat-buttons {l_hat[:8]}")
print("   -> vjoy1 N=82 E=83 S=84 W=81")
print("\n=== RIGHT Modifier hat: NEW input + root %s + hat-buttons %s ===" % (r_root_id[:8], r_hat[:8]))
print("   -> vjoy2 N=82 E=83 S=84 W=81")
print("   new <input>: device R, type hat, mode Modifier, id 1")

if "--apply" in sys.argv:
    # repoint left root
    lroot_block = block(LMOD_ROOT)
    new_lroot = lroot_block.replace(f"<action-id>{l_old_child}</action-id>",
                                    f"<action-id>{l_hat}</action-id>")
    text = text.replace(lroot_block, new_lroot, 1)
    # insert all new library actions before </library>
    new_lib = "".join("        " + b + "\n" for b in (l_blocks + r_blocks + [r_root]))
    lib_close = text.index("</library>")
    ins = text.rfind("\n", 0, lib_close) + 1
    text = text[:ins] + new_lib + text[ins:]
    # insert new right Modifier input right after the right SCM hat input
    iend2 = text.index("</input>", text.index("<root-action>" + RSCM_ROOT)) + len("</input>")
    text = text[:iend2] + "\n        " + r_input + text[iend2:]
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    ET.fromstring(text)
    print("\nAPPLIED. XML parses OK.")
else:
    print("\n(dry-run — pass --apply to write)")
