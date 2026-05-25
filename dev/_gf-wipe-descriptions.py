"""
Wipe all <action type="description"> from the Gunfighter JG profile.

For each description action found in <library>:
  - Remove its <action> element from <library>
  - Remove all <action-id>UUID</action-id> references to it from any <actions> block

Preserves LF line endings (newline="" — see references/jg-description-actions.md).
Makes a single backup ".xml.BAK-pre-wipe" before overwriting (idempotent — doesn't
overwrite an existing backup).
"""
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

JG_PATH = Path(
    r"E:\06. Dev Projects\Subs-Curated-Bindings\[Enhanced] Dual VKB Gunfighter Binds"
    r"\Joystick Gremlin Profile [ENH][GF][4.8.0][LIVE][R14].xml"
)


def main():
    with open(JG_PATH, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    backup = JG_PATH.with_suffix(".xml.BAK-pre-wipe")
    if not backup.exists():
        shutil.copy2(JG_PATH, backup)
        print(f"Backup written: {backup.name}")
    else:
        print(f"Backup already present: {backup.name}")

    # Find every description-action block and capture its id.
    # Match the entire <action ...>...</action> block (non-greedy).
    desc_pat = re.compile(
        r'(\s*)<action id="([^"]+)" type="description">(?:.*?)</action>\s*',
        re.DOTALL,
    )

    desc_ids = []
    for m in desc_pat.finditer(text):
        desc_ids.append(m.group(2))
    print(f"Found {len(desc_ids)} description actions to remove.")

    # Strip the <action ...type="description">...</action> blocks (with their leading whitespace + trailing newline).
    text, n_blocks = desc_pat.subn("", text)
    print(f"Removed {n_blocks} description action blocks from <library>.")

    # Strip each <action-id>UUID</action-id> reference (with surrounding whitespace).
    n_refs = 0
    for desc_id in desc_ids:
        ref_pat = re.compile(
            r"[ \t]*<action-id>" + re.escape(desc_id) + r"</action-id>\s*\n",
        )
        text, count = ref_pat.subn("", text)
        n_refs += count
    print(f"Removed {n_refs} <action-id> references to wiped descriptions.")

    with open(JG_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"Wrote {JG_PATH.name}")


if __name__ == "__main__":
    main()
