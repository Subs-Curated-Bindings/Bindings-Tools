"""Scan audit-passed JG profiles for duplicate description-action text.

Reports any description text used by more than one input root within a
single profile, and resolves each duplicate to the physical inputs that
host it (device-id, input-type, input-id, mode) by walking
<inputs>/<input>/<action-configuration>/<root-action>.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(r"E:/06. Dev Projects/Subs-Curated-Bindings")

PROFILES = [
    REPO / "[Enhanced] Dual VKB Gladiator NXT" / "Joystick Gremlin Profile [ENH][NXT][4.8.0][LIVE][R14].xml",
    REPO / "[Enhanced] Dual TM SOL-R" / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml",
    REPO / "[Enhanced] Dual VKB Gunfighter Binds" / "Joystick Gremlin Profile [ENH][GF][4.8.0][LIVE][R14].xml",
    REPO / "[Enhanced] Virpil VMAX Throttle + Aeromax-R" / "Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.0][LIVE][R14].xml",
]


def description_text(action: ET.Element) -> str | None:
    for prop in action.findall("property"):
        if prop.findtext("name", "") == "description":
            return (prop.findtext("value", "") or "").strip()
    return None


def scan(profile_path: Path):
    tree = ET.parse(profile_path)
    root_el = tree.getroot()

    # library: action-id -> action element
    library = {a.attrib["id"]: a for a in root_el.findall("./library/action")}

    # desc_id -> text
    desc_id_to_text = {}
    for aid, a in library.items():
        if a.attrib.get("type") != "description":
            continue
        text = description_text(a)
        if text is not None:
            desc_id_to_text[aid] = text

    # root-action-id -> list of (device, itype, iid, mode) input hosts
    root_to_hosts = defaultdict(list)
    for inp in root_el.findall("./inputs/input"):
        did = inp.findtext("device-id", "") or ""
        itype = inp.findtext("input-type", "") or ""
        iid = inp.findtext("input-id", "") or ""
        mode = inp.findtext("mode", "") or ""
        for ac in inp.findall("action-configuration"):
            root_id = ac.findtext("root-action", "") or ""
            if root_id:
                root_to_hosts[root_id].append((did, itype, iid, mode))

    # desc_id -> list of (root-action-id, host-list)
    desc_id_to_roots = defaultdict(list)
    for root_id, root_action in library.items():
        if root_action.attrib.get("type") != "root":
            continue
        actions_el = root_action.find("actions")
        if actions_el is None:
            continue
        for child in actions_el.findall("action-id"):
            cid = (child.text or "").strip()
            if cid in desc_id_to_text:
                desc_id_to_roots[cid].append(root_id)

    # Group by text
    text_to_entries = defaultdict(list)
    for desc_id, text in desc_id_to_text.items():
        roots = desc_id_to_roots.get(desc_id, [])
        text_to_entries[text].append((desc_id, roots))

    return text_to_entries, root_to_hosts


def short(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def device_short(guid: str) -> str:
    return guid[:8] if guid else "?"


def main() -> int:
    any_dupes = False
    for profile in PROFILES:
        if not profile.exists():
            print(f"!! MISSING: {profile}")
            continue
        stick_label = profile.parent.name
        print(f"\n=== {stick_label} ===")
        print(f"    {profile.name}")

        text_to_entries, root_to_hosts = scan(profile)
        total_actions = sum(len(v) for v in text_to_entries.values())
        unique_texts = len(text_to_entries)
        dupes = {t: e for t, e in text_to_entries.items() if len(e) > 1}
        print(f"    {total_actions} description actions, {unique_texts} unique texts, {len(dupes)} duplicated text(s)")
        if not dupes:
            print("    [OK] no duplicate description text")
            continue
        any_dupes = True

        for text, entries in sorted(dupes.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"\n    DUP x{len(entries)}: {short(text, 200)!r}")
            for desc_id, root_ids in entries:
                if not root_ids:
                    print(f"        - desc {desc_id[:8]}  (orphan: no root references it)")
                    continue
                for rid in root_ids:
                    hosts = root_to_hosts.get(rid, [])
                    if not hosts:
                        print(f"        - desc {desc_id[:8]} -> root {rid[:8]}  (root has no input hosts)")
                        continue
                    for did, itype, iid, mode in hosts:
                        print(f"        - desc {desc_id[:8]} -> root {rid[:8]}  dev:{device_short(did)} {itype}#{iid} mode={mode!r}")

    return 1 if any_dupes else 0


if __name__ == "__main__":
    sys.exit(main())
