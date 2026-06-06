# -*- coding: utf-8; -*-
"""One-off: make SOL-R button 36 a clean SCM<->NAV toggle.

Problem: button 36 (L-SCROLL.press) is a tap/hold "swap master mode" button.
SCM Mode wraps it in a tempo (good), but NAV Mode had a BARE change-mode with
no tempo -> it fired immediately on press, so arriving in NAV instantly bounced
back to SCM.

Fix:
  * Clone the SCM tempo (693167f5) into a new tempo for NAV, wiring NAV's own
    vjoy36 (1d6b23a3) as the tap and [NAV change-mode, vjoy128] as the hold.
  * Repoint the NAV root (36593e2f) at the new tempo.
  * Both change-modes -> Switch (deterministic SCM<->NAV) + activation release.

Preserves UTF-8 BOM + CRLF. Backs up. Run tools/fix-library-order.py after.
"""

from __future__ import annotations

import re
import shutil
import sys
import uuid

PROF = sys.argv[1]

SCM_TEMPO = "693167f5-15c5-4da2-968f-aaa6ac6db6af"
SCM_TAP = "399c5e2b-559b-4454-aadb-177297afa9d9"      # vjoy36 in SCM tempo short
SCM_CM = "f0daac22-07f3-427f-8998-3dbedcc28b38"       # SCM change-mode (Cycle->Nav)
SCM_VJOY127 = "0e6a1ac2-8d6e-4be3-a6ef-5bea1f82e19a"  # SCM tempo long vjoy127

NAV_ROOT = "36593e2f-7943-4e9f-a58f-32dc89091aaa"
NAV_TAP = "1d6b23a3-bdbc-43a7-ac80-9b67afc8f1cb"      # NAV vjoy36
NAV_CM = "31827787-0c9c-47e9-bba5-15fab77aac74"       # NAV change-mode (Cycle->SCM)
NAV_VJOY128 = "97aa6d5f-a186-429c-b2ca-40e6b55373a9"  # NAV vjoy128

NEW_TEMPO = str(uuid.uuid4())


def set_change_type(text: str, action_id: str, new_type: str) -> str:
    pat = re.compile(
        r'(<action id="' + re.escape(action_id)
        + r'" type="change-mode">.*?<name>change-type</name>\s*<value>)([A-Za-z]+)(</value>)',
        re.S,
    )
    out, n = pat.subn(rf"\g<1>{new_type}\g<3>", text)
    assert n == 1, f"change-type {action_id}: {n} matches"
    return out


def set_activation(text: str, action_id: str, mode: str) -> str:
    pat = re.compile(
        r'(<action id="' + re.escape(action_id)
        + r'" type="change-mode">.*?activation-mode</name>\s*<value>)([a-z]+)(</value>)',
        re.S,
    )
    out, n = pat.subn(rf"\g<1>{mode}\g<3>", text)
    assert n == 1, f"activation {action_id}: {n} matches"
    return out


def main() -> int:
    with open(PROF, "r", encoding="utf-8-sig", newline="") as fh:
        text = fh.read()
    eol = "\r\n" if "\r\n" in text else "\n"

    # 1. Extract the SCM tempo block (with leading indent) as the clone template.
    m = re.search(
        r'(        <action id="' + re.escape(SCM_TEMPO)
        + r'" type="tempo">.*?\r?\n        </action>)',
        text, re.S,
    )
    assert m, "SCM tempo block not found"
    block = m.group(1)

    # 2. Build the NAV tempo by swapping the wired action-ids.
    clone = (block
             .replace(SCM_TEMPO, NEW_TEMPO)
             .replace(SCM_TAP, NAV_TAP)
             .replace(SCM_CM, NAV_CM)
             .replace(SCM_VJOY127, NAV_VJOY128))

    # 3. Insert the clone right after the SCM tempo block.
    text = text.replace(block, block + eol + clone, 1)

    # 4. Repoint the NAV root's <actions> from the 3 bare ids to the new tempo.
    nav_actions_old = eol.join([
        "            <actions>",
        f"                <action-id>{NAV_TAP}</action-id>",
        f"                <action-id>{NAV_CM}</action-id>",
        f"                <action-id>{NAV_VJOY128}</action-id>",
        "            </actions>",
    ])
    nav_actions_new = eol.join([
        "            <actions>",
        f"                <action-id>{NEW_TEMPO}</action-id>",
        "            </actions>",
    ])
    assert nav_actions_old in text, "NAV root actions block not found verbatim"
    text = text.replace(nav_actions_old, nav_actions_new, 1)

    # 5. Both change-modes -> Switch + release.
    text = set_change_type(text, SCM_CM, "Switch")
    text = set_activation(text, SCM_CM, "release")
    text = set_change_type(text, NAV_CM, "Switch")
    text = set_activation(text, NAV_CM, "release")

    shutil.copy(PROF, PROF + ".bak-button36-toggle-fix")
    with open(PROF, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(text)
    print(f"OK. New NAV tempo = {NEW_TEMPO}")
    print("Now run: python tools/fix-library-order.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
