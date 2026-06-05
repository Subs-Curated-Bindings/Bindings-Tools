#!/usr/bin/env python3
"""Regenerate SOL-R chart description-bridge heads from the physical monikers.

The monikers (action-label leading token: L-SW-1.up, LL-BTN.7, L30.up, ...) are
Sub's authoritative, complete, directioned physical labeling. The chart's
description bridge (`<CLUSTER>[ [Mode]] — text`) had drifted off them (an earlier
rebuild trusted a stale control map). This rewrites each input's description HEAD
to the chart cluster its moniker maps to, carrying hat directions through, and
keeping scroll / loose base buttons as their own moniker-named binds (Sub: "follow
the JG file, don't force a cluster").

Mapping confirmed by Sub 2026-06-04. Dry-run by default; --apply writes.
Preserves line endings (newline="").
"""
import re, argparse
import xml.etree.ElementTree as ET
from pathlib import Path

JG = Path("[Enhanced] Dual TM SOL-R") / "Joystick Gremlin Profile [ENH][SOL-R 2][4.8.0][LIVE][R14].xml"
LEFT_GUID = "141b1470-1081-11f0-8006-444553540000"
CHILD = ("actions", "short-actions", "long-actions", "single-actions", "double-actions")
DIRS = ("up", "down", "left", "right", "press")


def prop(a, n):
    for p in a.findall("property"):
        nn, v = p.find("name"), p.find("value")
        if nn is not None and nn.text == n:
            return v.text if v is not None else None
    return None


def moniker_to_anchor(mon, side):
    """moniker string -> chart anchor head (or None to leave/skip).
    Returns the description-head token; hat directions ride along as `.dir`,
    scroll/loose buttons keep their full moniker (separate binds)."""
    parts = mon.split(".")
    base = parts[0]
    suf = parts[1] if len(parts) > 1 else None
    # 4-way hats: L30/L40/R30/R40 -> 4WAY-HAT-<side>-<num>.<dir>
    m = re.match(r"^([LR])(30|40)$", base)
    if m:
        d = suf if suf in DIRS else None
        head = f"4WAY-HAT-{m.group(1)}-{m.group(2)}"
        return f"{head}.{d}" if d else head
    # switches: L-SW-1/2 -> LL-SWITCH, L-SW-3/4 -> LR-SWITCH (R: RL/RR)
    m = re.match(r"^[LR]-SW-([1-4])$", base)
    if m:
        n = int(m.group(1))
        return f"{side}{'L' if n <= 2 else 'R'}-SWITCH"
    # base button rows: LL-BTN/LR-BTN/RL-BTN/RR-BTN -> *-BTNS
    m = re.match(r"^([LR][LR])-BTN$", base)
    if m:
        return f"{m.group(1)}-BTNS"
    if re.match(r"^[LR]-ENCODER$", base):
        return f"{side}-ENCODER"
    if re.match(r"^[LR]-KNOB$", base):
        return f"{side}-KNOB"
    if base == "MAIN-TRIGGER":
        return f"MAIN-TRIG-{side}"
    if re.match(r"^[LR]-RF$", base):
        return f"RAPID-TRIG-{side}"
    if re.match(r"^[LR]-PINKY$", base):
        return f"PINKY-{side}"
    # throttle is the LEFT stick's Z-axis only (no R-THROTTLE box on the chart)
    if base == "L-Z-Axis":
        return "L-THROTTLE"
    # mini-stick: X/Y rotation axes (SCM) + the L/R-ANALOG axis-as-button (Modifier)
    # both land in the grouped ANALOG-HAT box (not split, no direction suffix)
    if base in ("ANALOG-HAT-L", "ANALOG-HAT-R"):
        return base
    if re.match(r"^[LR]-ANALOG$", base) or re.match(r"^[LR]-(X|Y)-Rotation$", base):
        return f"ANALOG-HAT-{side}"
    # scroll + loose side-less base buttons: keep the moniker as its own bind
    if re.match(r"^[LR]-SCROLL$", base):
        return mon  # e.g. L-SCROLL.up  (separate bind, no cluster)
    if re.match(r"^BTN$", base):
        return mon  # BTN.35 / BTN.39
    # main flight axes + spare sliders: leave to the chart's hidden-axis handling
    # (Z-rotation, X/Y/Z translation, sliders, and the right flight stick `R-stick`)
    if (re.match(r"^[LR]-(X|Y|Z)-Axis$|^[LR]-Z-Rotation$|^[LR]-Slider-[12]$", base)
            or base == "R-stick"):
        return "__AXIS__"  # sentinel: don't bridge (hidden / not charted)
    return None  # unmapped -> report, don't touch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(JG, encoding="utf-8", newline="") as fh:
        text = fh.read()
    root = ET.fromstring(text)
    lib = {a.get("id"): a for a in root.iter("action") if a.get("id")}
    MON = re.compile(r"^([A-Za-z][A-Za-z0-9]*(?:[.\-][A-Za-z0-9]+)+)")

    def walk(aid, seen, descs, mons):
        if aid in seen or aid not in lib:
            return
        seen.add(aid)
        act = lib[aid]
        if act.get("type") == "description":
            v = prop(act, "description")
            if v:
                descs.append((act.get("id"), v))
        al = prop(act, "action-label")
        if al and not al.lstrip().startswith('"'):
            mm = MON.match(al.strip())
            if mm:
                mons.append(mm.group(1))
        for c in CHILD:
            cc = act.find(c)
            if cc is not None:
                for x in cc.findall("action-id"):
                    walk(x.text, seen, descs, mons)

    edits, skips, unmapped = [], [], []
    for inp in root.iter("input"):
        dev, it, iid, mode = (inp.findtext("device-id"), inp.findtext("input-type"),
                              inp.findtext("input-id"), inp.findtext("mode"))
        cfg = inp.find("action-configuration")
        if cfg is None or not cfg.findtext("root-action"):
            continue
        descs, mons = [], []
        walk(cfg.findtext("root-action"), set(), descs, mons)
        if not descs:
            continue
        did, dval = descs[0]
        side = "L" if dev == LEFT_GUID else "R"
        mon = mons[0] if mons else None
        if not mon:
            skips.append((side, it, iid, mode, "no moniker (R13 placeholder)"))
            continue
        anchor = moniker_to_anchor(mon, side)
        if anchor is None:
            unmapped.append((side, it, iid, mode, mon))
            continue
        if anchor == "__AXIS__":
            # Hidden main flight axis: if it carries a stale chart bridge (em-dash),
            # blank the description value so it extracts to null -> hidden axis.N.
            if "—" in dval:
                edits.append((descs[0][0], dval, "", side, it, iid, mode, mon,
                              "(stale bridge)", "(hidden)"))
            else:
                skips.append((side, it, iid, mode, mon))
            continue
        cur_head = dval.split("—", 1)[0].strip()
        cur_head = re.sub(r"\s*\[[^\]]*\]\s*$", "", cur_head).strip()
        tag = "" if mode == "SCM Mode" else f" [{ 'Modifier' if mode=='Modifier' else mode }]"
        post = dval.split("—", 1)[1].strip() if "—" in dval else dval
        new_val = f"{anchor}{tag} — {post}"
        if cur_head != anchor:
            edits.append((did, dval, new_val, side, it, iid, mode, mon, cur_head, anchor))

    print(f"=== {len(edits)} description heads to rewrite ===")
    for _, _, _, side, it, iid, mode, mon, cur, anc in sorted(edits, key=lambda e: (e[3], e[5] != 'button', int(e[5]) if e[5].isdigit() else 999, e[6])):
        print(f"  {side} {it[:3]} {iid:>3} {mode:9} {mon:22} {cur:20} -> {anc}")
    if unmapped:
        print(f"\n=== {len(unmapped)} UNMAPPED monikers (left untouched — review!) ===")
        for s, it, iid, mode, mon in unmapped:
            print(f"  {s} {it} {iid} {mode}: {mon}")
    print(f"\n({len(skips)} skipped: axes / R13 placeholders)")

    if not args.apply:
        print("\n(dry-run — pass --apply to write)")
        return
    for did, old, new, *_ in edits:
        m = re.search(r'<action\b[^>]*\bid="' + re.escape(did) + r'"[^>]*>.*?</action>', text, re.DOTALL)
        assert m, f"action {did} not found"
        block = m.group(0)
        needle = f"<value>{old}</value>"
        assert block.count(needle) == 1, f"{block.count(needle)}x {needle!r} in {did}"
        text = text[:m.start()] + block.replace(needle, f"<value>{new}</value>", 1) + text[m.end():]
    with open(JG, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"\nAPPLIED {len(edits)} rewrites.")


if __name__ == "__main__":
    main()
