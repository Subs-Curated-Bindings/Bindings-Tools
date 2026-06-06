# -*- coding: utf-8; -*-
"""Set the activation-mode on a specific change-mode action by id, in place.

One-off-ish maintenance helper: targets a single <action id=... type="change-mode">
block and rewrites only its activation-mode value. Preserves the profile's
UTF-8 BOM + CRLF (SOL-R profiles are CRLF) via utf-8-sig + newline="".

Usage: python tools/_solr-set-changemode-activation.py <profile.xml> <action-id> <press|release|both>
"""

from __future__ import annotations

import re
import shutil
import sys


def main() -> int:
    path, action_id, new_mode = sys.argv[1], sys.argv[2], sys.argv[3]
    assert new_mode in ("press", "release", "both"), new_mode

    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        text = fh.read()

    pat = re.compile(
        r'(<action id="' + re.escape(action_id)
        + r'" type="change-mode">.*?activation-mode</name>\s*<value>)([a-z]+)(</value>)',
        re.S,
    )
    m = pat.search(text)
    if not m:
        print(f"ERROR: change-mode action {action_id} not found")
        return 1
    old_mode = m.group(2)
    new_text, n = pat.subn(rf"\g<1>{new_mode}\g<3>", text)
    if n != 1:
        print(f"ERROR: expected exactly 1 replacement, got {n}")
        return 1

    shutil.copy(path, path + ".bak-changemode-activation")
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(new_text)
    print(f"OK: {action_id} activation {old_mode} -> {new_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
