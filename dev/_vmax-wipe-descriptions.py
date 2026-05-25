"""
Wipe all <action type="description"> from the VMAX+AERO JG profile.

Same pattern as _gf-wipe-descriptions.py: strip every description action block
from <library> and every <action-id>UUID</action-id> reference to those ids
from any <actions> block. Use this when the apply script ran multiple times
and accumulated duplicate descriptions per input root.

Preserves whatever line endings the file already has (newline="").
Single backup ".xml.BAK-pre-wipe" before overwriting (idempotent — doesn't
overwrite an existing backup).
"""
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

JG_PATH = Path(
    r"E:\06. Dev Projects\Subs-Curated-Bindings"
    r"\[Enhanced] Virpil VMAX Throttle + Aeromax-R"
    r"\Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.0][LIVE][R14].xml"
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

    desc_ids = []
    for m in desc_pat.finditer(text):
        desc_ids.append(m.group(2))
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
