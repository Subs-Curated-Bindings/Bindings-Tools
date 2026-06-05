#!/usr/bin/env python3
"""SOL-R cluster-head restoration — repair the chart description bridge.

The 2026-06-04 moniker pass (commit 9b8c927) OVERWROTE the left-grip
description bridges with bare bottom-tier action-label monikers, dropping the
etched physical-cluster name the chart anchors on. e.g. left button 1 (SCM):

    "4WAY-HAT-L-40 — v_retract_landing_system"   (bridge: head = cluster)
    -> "v_retract_landing_system"                 (clobbered: cluster lost)

This restores the cluster head onto every clobbered input while PRESERVING the
new SC-action moniker as the post-em-dash text:

    "v_retract_landing_system" -> "4WAY-HAT-L-40 — v_retract_landing_system"

Target cluster for each physical input comes from the authoritative deployed
control map (subliminal-gg `physical-control-maps/tm-sol-r-2-dual.json`), which
is verified 1:1 against the chart template's bind.X groups. Only inputs whose
current description head-base differs from that target are touched, so already-
correct bridges (the whole right grip) are left alone.

Edits the description <value> in-place by action id, preserving line endings.

Usage:
  py tools/_sol-r-restore-cluster-heads.py [--apply] [--map <control-map.json>]
"""
import re, json, argparse
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
DEFAULT_MAP = Path.home() / "projects/subliminal-gg/lib/sc-charts/physical-control-maps/tm-sol-r-2-dual.json"
CHILD = ("actions", "short-actions", "long-actions", "single-actions", "double-actions")
MODE_TAG = {"Modifier": " [Modifier]", "Nav Mode": " [Nav]"}  # SCM = no tag


def base(c):
    return c.split(".")[0] if c else c


def load_targets(map_path):
    m = json.load(open(map_path))
    out = {}
    for blk in m.values():
        for e in blk["inputs"]:
            if e.get("control"):
                out[(blk["device_guid"], e["type"], str(e["index"]))] = e["control"]
    return out


def prop(a, name):
    for p in a.findall("property"):
        n, v = p.find("name"), p.find("value")
        if n is not None and n.text == name:
            return v.text if v is not None else None
    return None


def first_desc(aid, lib, seen):
    """(action_id, value) of the first description reachable, in tree order."""
    if aid in seen or aid not in lib:
        return None
    seen.add(aid)
    act = lib[aid]
    if act.get("type") == "description":
        v = prop(act, "description")
        if v:
            return (aid, v)
    for cont in CHILD:
        c = act.find(cont)
        if c is not None:
            for x in c.findall("action-id"):
                r = first_desc(x.text, lib, seen)
                if r:
                    return r
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--map", default=str(DEFAULT_MAP))
    args = ap.parse_args()

    targets = load_targets(args.map)
    with open(JG, encoding="utf-8", newline="") as fh:
        text = fh.read()
    root = ET.fromstring(text)
    lib = {a.get("id"): a for a in root.iter("action") if a.get("id")}

    edits = []  # (aid, old_value, new_value, mode, target)
    for inp in root.iter("input"):
        dev, it, iid, mode = (inp.findtext("device-id"), inp.findtext("input-type"),
                              inp.findtext("input-id"), inp.findtext("mode"))
        if dev is None or iid is None:
            continue
        cfg = inp.find("action-configuration")
        if cfg is None or not cfg.findtext("root-action"):
            continue
        target = targets.get((dev, it, iid))
        if not target:
            continue
        d = first_desc(cfg.findtext("root-action"), lib, set())
        if not d:
            continue
        aid, val = d
        head = val.split("—", 1)[0].strip()
        head = re.sub(r"\s*\[[^\]]*\]\s*$", "", head)
        if base(head) == base(target):
            continue  # already a correct bridge — leave it (incl. .xx/.dir)
        tag = MODE_TAG.get(mode, "")
        post = val.split("—", 1)[1].strip() if "—" in val else val
        new = f"{target}{tag} — {post}"
        edits.append((aid, val, new, mode, target))

    print(f"{len(edits)} clobbered description(s) to restore:")
    for aid, old, new, mode, target in edits:
        print(f"  [{mode}] {old!r}\n        -> {new!r}")

    if not args.apply:
        print("\n(dry-run — pass --apply to write)")
        return

    # span-scoped replacement: edit each description <value> within its own
    # <action id="AID">…</action> block so identical bare monikers on different
    # buttons don't cross-contaminate.
    for aid, old, new, _, _ in edits:
        m = re.search(r'<action\b[^>]*\bid="' + re.escape(aid) + r'"[^>]*>.*?</action>',
                      text, re.DOTALL)
        assert m, f"action block {aid} not found"
        block = m.group(0)
        needle = f"<value>{old}</value>"
        assert block.count(needle) == 1, f"{block.count(needle)}× {needle!r} in {aid}"
        text = text[:m.start()] + block.replace(needle, f"<value>{new}</value>", 1) + text[m.end():]

    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"\nAPPLIED {len(edits)} restoration(s).")


if __name__ == "__main__":
    main()
