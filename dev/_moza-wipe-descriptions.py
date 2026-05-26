"""
Wipe all <action type="description"> from the MOZA MTQ+MHG JG profile.

Strip every description action block from <library> and every <action-id>UUID
reference to those ids from any <actions> block. Use when the apply script
accumulated duplicates or you want to start clean before changing overrides.

Preserves whatever line endings the file already has (newline="").
Writes a single backup `.xml.BAK-pre-wipe` (idempotent — doesn't overwrite).
"""
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

JG_PATH = Path(
    r"E:\06. Dev Projects\Subs-Curated-Bindings"
    r"\[Enhanced] MOZA MTQ + MHG"
    r"\Joystick Gremlin Profile [ENH][MTQ+MHG][4.8.0][LIVE][R14].xml"
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

    desc_pat = re.compile(
        r'(\s*)<action id="([^"]+)" type="description">(?:.*?)</action>\s*',
        re.DOTALL,
    )
    desc_ids = [m.group(2) for m in desc_pat.finditer(text)]
    print(f"Found {len(desc_ids)} description actions to remove.")

    text, n_blocks = desc_pat.subn("", text)
    print(f"Removed {n_blocks} description action blocks from <library>.")

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
