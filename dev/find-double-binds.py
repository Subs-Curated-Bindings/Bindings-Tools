#!/usr/bin/env python3
"""find-double-binds.py — find (and optionally clean up) SC "double binds".

A double bind is a single <action> carrying more than one *joystick* <rebind>.
Star Citizen does NOT support that: it keeps the LAST <rebind> and silently drops
the earlier one(s). But anything that reads the file at face value — the chart
generator, for instance — sees BOTH and can render/use the dead one.

Real example (NXT, tractor_beam):

    <action name="tractor_beam_decrease_distance">
      <rebind input="js1_button24"/>   <-- DEAD  (C1 hat, what the chart showed)
      <rebind input="js1_button38"/>   <-- ACTIVE (A4 hat, what the game uses)
    </action>

SAFETY / TRANSPARENCY
---------------------
This NEVER silently deletes. Default is a DRY RUN: it prints every double bind,
which joystick slot the game actually uses (KEEP) and which it ignores (REMOVE),
and changes nothing. Only `--apply` writes — and then it makes a `.bak` first and
prints every line it removed. If this is ever run on the server, the same report
is what the user must be shown ("you had N double binds; here's what we kept and
what we dropped").

KEEP rule: by default KEEP = the slot the game uses (the LAST joystick <rebind>;
observed, Sub 2026-05-30). Override per action with --keep to force a different
slot to survive (e.g. to make a bind symmetric on a specific control).

Usage
-----
  find-double-binds.py <file.xml> [<file2.xml> ...]            # detect (dry run)
  find-double-binds.py ... --control-map map.json             # annotate w/ control names
  find-double-binds.py ... --all-devices                      # also flag 2+ kb / 2+ mouse
  find-double-binds.py ... --keep ACTION=SLOT                  # force-keep a slot (repeatable)
  find-double-binds.py ... --only ACTION [--only ACTION ...]   # limit --apply to these actions
  find-double-binds.py ... --apply                             # WRITE the cleanup (.bak first)

Exit: 0 = nothing found (or all clean after apply), 1 = double binds remain / found.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import xml.etree.ElementTree as ET

ACTIVE_IS_LAST = True  # SC keeps the last joystick rebind (observed, Sub 2026-05-30)
_FAMILY_RE = re.compile(r"^([a-z]+)\d+_", re.I)
_ACTIONMAP_OPEN = re.compile(r'<actionmap\s+name="([^"]+)"')
_ACTION_OPEN = re.compile(r'<action\s+name="([^"]+)"')
_REBIND = re.compile(r'<rebind\s+input="([^"]*)"')


def device_family(inp: str) -> str | None:
    m = _FAMILY_RE.match(inp.strip())
    return m.group(1).lower() if m else None


def is_real_bind(inp: str) -> bool:
    s = (inp or "").strip()
    return "_" in s and s.split("_", 1)[1].strip() != ""


def load_control_map(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"!! could not read control map {path}: {e}", file=sys.stderr)
        return out
    for side in data.values():
        for it in side.get("inputs", []) or []:
            ctrl = it.get("control")
            if not ctrl:
                continue
            for v in it.get("vjoy", []) or []:
                out[f"js{v['device']}_{v['type']}{v['id']}"] = ctrl
    return out


def annotate(slot: str, cmap: dict[str, str]) -> str:
    n = cmap.get(slot)
    return f"{slot} ({n})" if n else slot


def scan(path: str, all_devices: bool):
    """Return [(actionmap, action, [js_inputs_in_order])] for doubly-bound actions."""
    try:
        root = ET.parse(path).getroot()
    except Exception as e:  # noqa: BLE001
        print(f"!! could not parse {path}: {e}", file=sys.stderr)
        return None
    out = []
    for am in root.iter("actionmap"):
        amn = am.get("name", "?")
        for ac in am.iter("action"):
            acn = ac.get("name", "?")
            binds = [b for b in (rb.get("input", "") for rb in ac.iter("rebind")) if is_real_bind(b)]
            by_fam: dict[str, list[str]] = {}
            for b in binds:
                by_fam.setdefault(device_family(b) or "?", []).append(b)
            for fam in (["js"] if not all_devices else list(by_fam)):
                group = by_fam.get(fam, [])
                if len(group) >= 2:
                    out.append((amn, acn, group))
    return out


def decide(group: list[str], action: str, actionmap: str, keeps: dict[str, str]):
    """Return (keep_slot, [remove_slots])."""
    override = keeps.get(f"{actionmap}/{action}") or keeps.get(action)
    keep = override if override and override in group else (group[-1] if ACTIVE_IS_LAST else group[0])
    return keep, [g for g in group if g != keep]


def apply_fixes(path: str, fixes: dict[tuple[str, str], list[str]]):
    """Line-based removal: drop <rebind input="SLOT"> lines for the given
    (actionmap, action) targets, preserving all other formatting. Writes a .bak.
    Returns list of (actionmap, action, removed_slot, raw_line)."""
    lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
    cur_am = cur_ac = None
    removed = []
    out = []
    for ln in lines:
        m = _ACTIONMAP_OPEN.search(ln)
        if m:
            cur_am = m.group(1)
        ma = _ACTION_OPEN.search(ln)
        if ma:
            cur_ac = ma.group(1)
        mr = _REBIND.search(ln)
        if mr and cur_am is not None and cur_ac is not None:
            slot = mr.group(1)
            if slot in fixes.get((cur_am, cur_ac), []):
                removed.append((cur_am, cur_ac, slot, ln.strip()))
                if "</action>" in ln:           # rare same-line close: keep the close
                    out.append(re.sub(r"<rebind\b[^>]*/>", "", ln))
                continue                          # drop this rebind line
        if "</action>" in ln:
            cur_ac = None
        if "</actionmap>" in ln:
            cur_am = None
        out.append(ln)
    open(path + ".bak", "w", encoding="utf-8").write("".join(lines))
    open(path, "w", encoding="utf-8").write("".join(out))
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description="Find/clean SC double binds (2+ joystick rebinds on one action).")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--control-map")
    ap.add_argument("--all-devices", action="store_true")
    ap.add_argument("--keep", action="append", default=[], metavar="ACTION=SLOT",
                    help="force-keep SLOT for ACTION (repeatable); ACTION may be 'actionmap/action'")
    ap.add_argument("--only", action="append", default=[], metavar="ACTION",
                    help="limit --apply to these action names (repeatable)")
    ap.add_argument("--apply", action="store_true", help="write the cleanup (.bak first)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cmap = load_control_map(args.control_map) if args.control_map else {}
    keeps: dict[str, str] = {}
    for kv in args.keep:
        if "=" in kv:
            k, v = kv.split("=", 1)
            keeps[k.strip()] = v.strip()
    only = set(args.only)

    paths: list[str] = []
    for f in args.files:
        hits = glob.glob(f, recursive=True)
        paths.extend(hits if hits else [f])

    total = 0
    mode = "APPLY" if args.apply else "DRY RUN (no changes — use --apply to write)"
    print(f"== mode: {mode} ==")
    for path in paths:
        doubles = scan(path, args.all_devices)
        if doubles is None:
            continue
        if not doubles:
            if not args.quiet:
                print(f"OK   {path} — no double binds")
            continue
        total += len(doubles)
        print(f"\n==== {path} — {len(doubles)} double bind(s) ====")
        fixes: dict[tuple[str, str], list[str]] = {}
        for amn, acn, group in doubles:
            keep, remove = decide(group, acn, amn, keeps)
            targeted = (not only) or (acn in only)
            tag = "" if targeted else "   [skipped: not in --only]"
            print(f"  [{amn}] {acn}{tag}")
            print(f"      KEEP   {annotate(keep, cmap)}")
            for r in remove:
                print(f"      REMOVE {annotate(r, cmap)}")
            if targeted:
                fixes[(amn, acn)] = remove
        if args.apply and fixes:
            removed = apply_fixes(path, fixes)
            print(f"  -> wrote {path}  (backup: {path}.bak)")
            for amn, acn, slot, raw in removed:
                print(f"     removed from [{amn}] {acn}: {raw}")
    print(f"\nTotal double binds {'found' if not args.apply else 'processed'}: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
