#!/usr/bin/env python3
"""VMAX+AERO moniker pass -- migrate the Virpil VMAX Throttle + Aeromax-R JG
profile to the settled physical-moniker convention (SOL-R 2026-06-05,
NXT/GF 2026-06-11).

The Virpils have no etching, so monikers use the chart's T-/R- cluster names
(T-H1..T-H3, T-B1..T-B4, T-E1/T-E2, T-M1, T-T1; R-H1..R-H3, R-B1/B4/B5/B6,
R-M1, MAIN-TRIG-R, FLIP-TRIG-R). Axes use the JG HID names (T-X-Axis ..
T-Dial, R-X-Axis .. R-Dial) per the SOL-R precedent; the chart-side mapping
resolves e.g. T-Z-Rotation -> T-T1.

Ground-truthed against layout_ENH_VMAX_AERO_480_LIVE_exported.xml (chart
direction text -> SC actions -> jsN slots -> physical ids), NOT the old
matcher bridges (the NXT R-A4 lesson):
  - Throttle hats are press-first: T-H1 16-20, T-H2 10-14 (press,right,down,
    left,up); T-H3 4-8 enumerates press,down,right,up,left (triple-checked
    via the Modifier layer: AdvHUD=46/GForce=47/LeadLag=48).
  - Aeromax hats are press,up,right,down,left: R-H3 7-11, R-H2 20-24,
    R-H1 14-18 (press 14 + up 15 unbound -- chart paints up=Unbound).
  - Modifier layer = phys N -> vjoy N+40 on BOTH devices.
  - The PHYSICAL MODIFIER (R-B3, hardware shift -- no JG presence) gives the
    mini-stick a shifted block 26-30 (press,up,right,down,left), monikered
    R-M1.<dir>.pm. That makes phys 26 (Capacitor Reset) the PM+press of the
    mini-stick, NOT R-H1's press as the old chart painted it.
  - AERO 25 / 31-36 are unidentified (likely phantom HID slots or the unbound
    R-B2): left unmonikered.

What it does in one idempotent pass:
  1. Moniker on every bottom-tier emitting action across all modes; tempo
     leaves carry the full `<moniker>.tap/.hold`.
  2. Authors load-bearing quoted labels: T-B4 Modifier change-modes (x3),
     2 mouse-camera emits (Modifier-mode mini-stick), the Reset Freelook
     keyboard macro.
  3. Change-modes inside tempo holds -> the `None` sentinel.
  4. Removes all 90 em-dash chart-bridge description actions + their refs.
  5. Adds short-root + fuller descriptions on non-basic controls: 12 plain
     axes, the mini-stick holder (SCM cfg0 x2), the brake lever, 2 mouse
     axes, 4 SCM tempo routes, the flip trigger, T-B4.

Balanced block scanner at text level; preserves BOM + CRLF (newline="").
"""
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

PROFILE = Path(__file__).resolve().parent.parent / (
    "[Enhanced] Virpil VMAX Throttle + Aeromax-R/"
    "Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.0][LIVE][R14].xml"
)

R_DEV = "40440b60-c93b-11f0-8002-444553540000"  # RIGHT VPC CDT-AEROMAX -> vjoy 2
T_DEV = "63b4c490-c93b-11f0-8004-444553540000"  # VPC CDT-VMAX Throttle -> vjoy 1

AXIS_NAMES = {1: "X-Axis", 2: "Y-Axis", 3: "Z-Axis", 4: "X-Rotation",
              5: "Y-Rotation", 6: "Z-Rotation", 7: "Slider", 8: "Dial"}

def hat(name, base, order):
    return {base + i: f"{name}.{d}" for i, d in enumerate(order)}

PURDL = ("press-in", "up", "right", "down", "left")      # Aeromax hats
T_MONIKERS = {
    1: "T-E1.press-in", 2: "T-B3", 3: "T-B4",
    9: "T-E2.press-in", 15: "T-M1.press-in",
    21: "T-B2", 22: "T-B1",
}
T_MONIKERS.update(hat("T-H3", 4, ("press-in", "down", "right", "up", "left")))
T_MONIKERS.update(hat("T-H2", 10, ("press-in", "right", "down", "left", "up")))
T_MONIKERS.update(hat("T-H1", 16, ("press-in", "right", "down", "left", "up")))

R_MONIKERS = {
    1: "MAIN-TRIG-R.stage-1", 2: "MAIN-TRIG-R.stage-2",
    3: "FLIP-TRIG-R.flip", 4: "FLIP-TRIG-R.pull",
    5: "R-B4", 6: "R-M1.press-in", 12: "R-B1", 13: "R-B6", 19: "R-B5",
}
R_MONIKERS.update(hat("R-H3", 7, PURDL))
R_MONIKERS.update(hat("R-H1", 14, PURDL))
R_MONIKERS.update(hat("R-H2", 20, PURDL))
# Physical-Modifier (R-B3 hardware shift) block: mini-stick press + 4 dirs
R_MONIKERS.update({26 + i: f"R-M1.{d}.pm" for i, d in enumerate(PURDL)})
# 25 and 31-36 unidentified (phantom HID slots / unbound R-B2) -> no moniker

BUTTON_MONIKERS = {T_DEV: T_MONIKERS, R_DEV: R_MONIKERS}

# axis-as-button threshold emits, keyed by (device, axis-id, vjoy-slot)
THRESHOLD_MONIKERS = {
    (R_DEV, 4, 38): "R-M1.right", (R_DEV, 4, 40): "R-M1.left",
    (R_DEV, 5, 37): "R-M1.up",    (R_DEV, 5, 39): "R-M1.down",
    (R_DEV, 6, 81): "R-BRAKE",
}

AXIS_DESC = ("A flat 1:1 response curve sits on this axis only so you can "
             "reverse its direction with Joystick Gremlin's Invert Curve "
             "button if your hardware reads it backwards. No other effect.")
MOUSE_DESC = {
    "90": ("Routed to mouse Y so you can free-look up and down in 3rd-person "
           "flight. The flat center curve suppresses idle stick drift so the "
           "camera holds still."),
    "0": ("Routed to mouse X so you can free-look left and right in "
          "3rd-person flight. The flat center curve suppresses idle stick "
          "drift so the camera holds still."),
}
MOUSE_LABELS = {  # keyed by map-to-mouse `direction` property
    "90": '"Camera Tilt (Mouse Y) | Camera" Routed to mouse Y so you can free-look up/down while flying in 3rd person.',
    "0": '"Camera Pan (Mouse X) | Camera" Routed to mouse X so you can free-look left/right while flying in 3rd person.',
}
MINISTICK_SHORT = "Mini-stick - Targeting / MFDs"
MINISTICK_DESC = ("The mini-stick reads as four buttons - push it past "
                  "halfway to cycle targets: hostiles by default, everything "
                  "on a double-tap. With the physical modifier held the same "
                  "pushes drive the MFDs instead. Click it in to lock the "
                  "target under your reticle.")
BRAKE_SHORT = "Brake Lever - Space Brake"
BRAKE_DESC = ("Pulling the Aeromax brake lever nearly all the way (past 95%) "
              "presses and holds the space brake. Release to let go.")
MODIFIER_DESC = ("Hold the Modifier button (T-B4) to switch on the Modifier "
                 "layer, a temporary shift that gives most buttons a second "
                 "function while held. Release to return. Nothing is sent to "
                 "the game; it only changes Joystick Gremlin's layer.")
MODIFIER_LABELS = {
    "Temporary": 'T-B4 "Modifier | Modifier" Hold-only Modifier mode (chord layer). Reverts on release.',
    "Previous": 'T-B4 "Modifier | Modifier" Pop mode stack -- return to the prior active mode.',
}
FREELOOK_QUOTE = '"Reset Freelook | Camera" Holds F4 + the freelook button 0.5s to recenter.'
LIGHTAMP_NOTE = "Clean 100ms tap on the light-amp slot. Activation-mode must stay release (not both)."

# (device, input-id) -> (short root label, fuller description), SCM route only
SPECIAL_ROOTS = {
    (T_DEV, 2): ("Tempo (Tap/Hold) Scan Ping / Light Amp",
                 "Tap fires a radar ping. Hold about half a second to toggle "
                 "Light Amplification (night vision); it runs through a "
                 "macro because Star Citizen only accepts a quick tap on "
                 "that bind."),
    (T_DEV, 16): ("Tempo (Tap/Hold) Reset View / Reset Freelook",
                  "Tap resets the current view. Hold about half a second to "
                  "recenter the camera: a macro holds F4 plus the freelook "
                  "button for half a second, since Star Citizen won't let "
                  "you bind the recenter directly."),
    (T_DEV, 21): ("Tempo (Tap/Hold) Operator / Master Mode",
                  "Tap cycles your operator mode. Hold about half a second "
                  "to swap master modes between SCM and NAV; Joystick "
                  "Gremlin's active layer follows along."),
    (T_DEV, 22): ("Tempo (Tap/Hold) Auxiliary Mode Cycle",
                  "Hold about half a second to cycle the Auxiliary layer "
                  "for mining and salvage - Star Citizen's operator mode "
                  "and Joystick Gremlin's layer switch together. From "
                  "Auxiliary, the hold returns to SCM."),
    (T_DEV, 3): ("Modifier", MODIFIER_DESC),
    (R_DEV, 3): ("Flip Trigger - Missile Op Mode",
                 "Flipping the trigger guard down toggles missile operator "
                 "mode. Flipping it back up exits to guns - a release macro "
                 "taps the guns-mode toggle. Pull the exposed trigger to "
                 "fire missiles."),
}


def get_prop(a, name):
    for pr in a.findall("property"):
        if pr.findtext("name") == name:
            return pr.findtext("value") or ""
    return ""


def main(apply=False):
    raw = PROFILE.read_text(encoding="utf-8", newline="")
    root = ET.fromstring(raw.lstrip("﻿"))
    lib = {a.get("id"): a for a in root.find("library")}

    label_edits = {}       # action-id -> new label
    desc_removals = set()  # description action-ids to drop (block + refs)
    desc_additions = []    # (root_id, ref_index, text)
    report = []

    def set_label(aid, new):
        a = lib[aid]
        old = get_prop(a, "action-label")
        if aid in label_edits:
            assert label_edits[aid] == new, \
                f"conflicting labels for {aid}: {label_edits[aid]!r} vs {new!r}"
            return
        if old != new:
            label_edits[aid] = new
            report.append(f"  [{a.get('type')}] {old!r} -> {new!r}")

    def macro_has_keys(a):
        return any(ma.get("type") == "key" for ma in a.iter("macro-action"))

    def vjoy_slot(a):
        return int(get_prop(a, "vjoy-input-id") or 0)

    for inp in root.find("inputs"):
        dev = inp.findtext("device-id")
        itype = inp.findtext("input-type")
        iid = int(inp.findtext("input-id"))
        mode = inp.findtext("mode")
        is_scm = mode == "SCM Mode"
        side_mons = BUTTON_MONIKERS[dev]

        if itype == "axis":
            axis_mon = ("T-" if dev == T_DEV else "R-") + AXIS_NAMES[iid]
        else:
            axis_mon = None

        for cfg in inp.findall("action-configuration"):
            rid = cfg.findtext("root-action")
            beh = cfg.findtext("behavior")
            ra = lib[rid]
            kids = [r.text for r in ra.find("actions").findall("action-id")]
            kid_types = [lib[k].get("type") for k in kids]
            has_mouse = "map-to-mouse" in kid_types
            has_tempo = "tempo" in kid_types

            if itype == "axis" and beh == "button":
                # threshold cfg: emits carry the cluster moniker, root stays bare
                set_label(rid, "Root")
                for k, kt in zip(kids, kid_types):
                    if kt == "description":
                        desc_removals.add(k)
                        continue
                    assert kt == "map-to-vjoy", f"unexpected threshold child {kt}"
                    mon = THRESHOLD_MONIKERS[(dev, iid, vjoy_slot(lib[k]))]
                    set_label(k, mon)
                continue

            mon = axis_mon if itype == "axis" else side_mons.get(iid)

            for k, kt in zip(kids, kid_types):
                a = lib[k]
                if kt == "description":
                    desc_removals.add(k)
                    continue
                if mon is None:
                    continue  # unidentified AERO 25 / 31-36 keep their labels
                if kt == "map-to-vjoy":
                    set_label(k, mon)
                elif kt == "response-curve":
                    pass  # keep existing curve labels
                elif kt == "map-to-mouse":
                    set_label(k, MOUSE_LABELS[get_prop(a, "direction")])
                elif kt == "change-mode":
                    # standalone T-B4 modifier: moniker + authored quote
                    set_label(k, MODIFIER_LABELS[get_prop(a, "change-type")])
                elif kt == "macro":
                    # FLIP-TRIG-R release macro: parallel emit, shares moniker
                    assert not macro_has_keys(a), "unexpected key macro at root"
                    set_label(k, mon)
                elif kt == "tempo":
                    set_label(k, mon)
                    for cont, suffix in (("short-actions", ".tap"),
                                         ("long-actions", ".hold")):
                        c = a.find(cont)
                        if c is None:
                            continue
                        for ref in c.findall("action-id"):
                            la = lib[ref.text]
                            lt = la.get("type")
                            if lt == "map-to-vjoy":
                                set_label(ref.text, f"{mon}{suffix}")
                            elif lt == "change-mode":
                                set_label(ref.text, "None")
                            elif lt == "macro":
                                if macro_has_keys(la):
                                    set_label(ref.text, f"{mon}{suffix} {FREELOOK_QUOTE}")
                                else:
                                    set_label(ref.text, f"{mon}{suffix} {LIGHTAMP_NOTE}")
                            else:
                                raise ValueError(f"unhandled tempo leaf type {lt}")
                else:
                    raise ValueError(f"unhandled root child type {kt}")

            # ---- root labels + fresh descriptions (non-basic only) ----
            if itype == "axis" and has_mouse:
                a = lib[kids[kid_types.index("map-to-mouse")]]
                set_label(rid, "Axis to Mouse Axis (3rd Person Freelook)")
                desc_additions.append((rid, 1, MOUSE_DESC[get_prop(a, "direction")]))
            elif itype == "axis" and dev == R_DEV and iid in (4, 5) and is_scm:
                set_label(rid, MINISTICK_SHORT)
                desc_additions.append((rid, 1, MINISTICK_DESC))
            elif itype == "axis" and dev == R_DEV and iid == 6:
                set_label(rid, BRAKE_SHORT)
                desc_additions.append((rid, 1, BRAKE_DESC))
            elif itype == "axis":
                set_label(rid, "Response Curve (For Inversion)")
                desc_additions.append((rid, 1, AXIS_DESC))
            elif is_scm and (dev, iid) in SPECIAL_ROOTS:
                short, desc = SPECIAL_ROOTS[(dev, iid)]
                set_label(rid, short)
                desc_additions.append((rid, 0, desc))

    # ---------- report ----------
    print(f"label edits: {len(label_edits)}")
    print(f"description removals: {len(desc_removals)}")
    print(f"description additions: {len(desc_additions)}")
    for line in report:
        print(line)
    if not apply:
        print("\nDRY RUN -- re-run with --apply to write.")
        return

    # ---------- text-level application (balanced block scanner) ----------
    text = raw
    EOL = "\r\n" if "\r\n" in raw else "\n"

    def block_span(aid):
        start = text.index(f'<action id="{aid}"')
        end = text.index("</action>", start) + len("</action>")
        return start, end

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 1. remove description blocks (incl. any leading whitespace run)
    for did in sorted(desc_removals, key=lambda d: block_span(d)[0], reverse=True):
        s, e = block_span(did)
        ws = s
        while ws > 0 and text[ws - 1] in " \t\r\n":
            ws -= 1
        text = text[:ws] + text[e:]

    # 2. strip refs to removed descriptions
    for did in desc_removals:
        pat = re.compile(r"[ \t]*<action-id>" + re.escape(did) + r"</action-id>\r?\n?")
        text, n = pat.subn("", text)
        assert n == 1, f"expected exactly one ref to removed description {did}, got {n}"

    # 3. label edits
    label_pat = r"(<name>action-label</name>\s*<value>)[^<]*(</value>)"
    for aid, new in label_edits.items():
        s, e = block_span(aid)
        block = text[s:e]
        block, n = re.subn(label_pat,
                           lambda m: m.group(1) + esc(new) + m.group(2),
                           block, count=1)
        assert n == 1, f"label edit failed for {aid}"
        text = text[:s] + block + text[e:]

    # 4. new description blocks + refs
    def desc_block(aid, dtext):
        lines = [
            f'        <action id="{aid}" type="description">',
            '            <property type="string">',
            '                <name>description</name>',
            f'                <value>{esc(dtext)}</value>',
            '            </property>',
            '            <property type="string">',
            '                <name>action-label</name>',
            '                <value>Description</value>',
            '            </property>',
            '            <property type="activation-mode">',
            '                <name>activation-mode</name>',
            '                <value>disallowed</value>',
            '            </property>',
            '        </action>',
            '',
        ]
        return EOL.join(lines)

    for rid, idx, dtext in desc_additions:
        new_id = str(uuid.uuid4())
        s, e = block_span(rid)
        ls = text.rfind("\n", 0, s) + 1
        prefix = text[ls:s]
        if prefix.strip() == "":
            text = text[:ls] + desc_block(new_id, dtext) + text[ls:]
        else:
            # root block glued to the previous </action> on one line
            text = text[:s] + EOL + desc_block(new_id, dtext) + "        " + text[s:]
        s, e = block_span(rid)
        block = text[s:e]
        refs = list(re.finditer(r"[ \t]*<action-id>[0-9a-f-]+</action-id>", block))
        assert refs, f"no refs in root {rid}"
        new_ref = f"                <action-id>{new_id}</action-id>{EOL}"
        if idx < len(refs):
            anchor = refs[idx]
            block = block[:anchor.start()] + new_ref + block[anchor.start():]
        else:
            ins = refs[-1].end()
            block = block[:ins] + EOL + new_ref.rstrip("\r\n") + block[ins:]
        text = text[:s] + block + text[e:]

    # 5. sanity: no dangling references to removed actions
    for did in desc_removals:
        assert did not in text, f"dangling reference to removed action {did}"

    # 6. semantic verification: wiring must be byte-identical to the original
    def wiring(xml_text):
        rt = ET.fromstring(xml_text.lstrip("﻿"))
        lb = {a.get("id"): a for a in rt.find("library")}
        out = []
        def sig(aid, path):
            a = lb[aid]
            t = a.get("type")
            if t == "description":
                return
            if t == "map-to-vjoy":
                out.append((path, t, get_prop(a, "vjoy-device-id"), get_prop(a, "vjoy-input-id")))
            elif t == "map-to-mouse":
                out.append((path, t, get_prop(a, "direction")))
            elif t == "change-mode":
                out.append((path, t, get_prop(a, "change-type"),
                            tuple(sorted(p.findtext("value") or "" for tm in a.findall("target-mode") for p in tm.findall("property")))))
            elif t == "macro":
                out.append((path, t, tuple((ma.get("type"),
                            tuple(sorted((pr.findtext("name"), pr.findtext("value")) for pr in ma.findall("property"))))
                            for ma in a.findall("macro-action"))))
            else:
                out.append((path, t))
            for cont in ("actions", "short-actions", "long-actions"):
                c = a.find(cont)
                if c is not None:
                    for r in c.findall("action-id"):
                        sig(r.text, path + (cont,))
        for inp in rt.find("inputs"):
            key = (inp.findtext("device-id"), inp.findtext("input-type"),
                   inp.findtext("input-id"), inp.findtext("mode"))
            for ci, cfg in enumerate(inp.findall("action-configuration")):
                sig(cfg.findtext("root-action"), key + (ci,))
        return sorted(map(repr, out))

    assert wiring(raw) == wiring(text), "SEMANTIC WIRING CHANGED -- aborting"

    PROFILE.write_text(text, encoding="utf-8", newline="")
    print(f"\nWROTE {PROFILE}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
