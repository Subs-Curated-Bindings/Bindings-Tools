#!/usr/bin/env python3
"""MOZA MTQ + MHG moniker pass -- migrate the JG profile to the settled
physical-moniker convention (SOL-R 2026-06-05, NXT/GF 2026-06-11,
VMAX 2026-06-12).

Monikers use the chart's T-/R- cluster names (MTQ throttle = T-*, vjoy 1;
MHG grip = R-*, vjoy 2). Axes use the JG HID names (T-X-Axis .. T-Dial,
R-X-Axis .. R-Dial) per the SOL-R precedent; the chart-side mapping in
extract-physical-control-map.py resolves e.g. T-Slider -> T-2.

Ground-truthed against layout_ENH_MTQ_MHG_480_LIVE_exported.xml (chart
direction text -> SC actions -> jsN slots -> physical ids), NOT the old
matcher bridges (the NXT R-A4 lesson):
  - MHG hats enumerate base+0=up,+1=right,+2=down,+3=left,+4=press-in
    uniformly: R-TGT 7-11, R-DATA 12-16, R-DEF 17-21 (the old bridge put
    the chart's R-POV.press-in.device "Switch to Analog" note on phys 21;
    physically 21 is R-DEF.press-in -- shield reset / laser type / focus
    all heads). R-POV 25-28 is up,right,down,left (no press emit -- its
    press is the hardware analog-mode toggle; the analog mode is MHG axes
    4/5, routed to mouse free-look). R-CTL is 22=right, 23=left,
    24=press-in.
  - MTQ 5-ways enumerate press-in,right,left,down,up: T-WPN 52-56
    (52 = Flight Ready / Precision Aiming = the chart's press-in text;
    56 = the [DT] Reset-3rd-Person double-tap = the chart's up text),
    T-COM 57-61 (57 = gimbal toggles = press-in).
  - T-MODE is the FIVE-detent dial phys 17-21: pos 1=NAV, 3=SCM,
    5=Mining/Salvage carry the tempo+change-mode routes; the chart's
    bind.T-MODE.2 / bind.T-MODE.4 ("| Unbound") are detents 2/4 =
    phys 18/20. phys 36 is the SCM detent's Nav-Mode route (T-MODE.scm).
  - Modifier layers: MHG = phys+30 (sequential); MTQ = sequential 61..119
    across the enumeration order (the 37-40 id gap collapses; phys 36 and
    65 have no Modifier remap). Monikers stay the physical identity
    regardless of slot.
  - The Modifier button is T-B1 (MTQ phys 65, chart label.T-B1 =
    "MODIFIER"). Oddity kept as-is and described: in Nav Mode the
    Modifier change-mode also sits on phys 28 (T-SW2.down).
  - Unidentified ids keep their generic labels (flagged in the report):
    MTQ 11-13, 31-35, 41-49 (42 fires the afterburner slot, Modifier+49
    fires Eject); MHG 29, 49, 57-59 (57/58 OR-feed the Sub-Target
    reset/back slots).

What it does in one idempotent pass:
  1. Moniker on every bottom-tier emitting action across all modes; tempo
     leaves carry the full `<moniker>.tap/.hold`; the T-WPN.up double-tap
     leaves carry `.tap` / `.double-tap`.
  2. Authors load-bearing quoted labels: T-B1 Modifier change-modes, the
     Nav-Mode T-SW2.down Modifier, 2 mouse-camera axes (MHG 4/5), the
     F4+camera Reset-3rd-Person keyboard macro.
  3. Change-modes inside tempo holds -> the `None` sentinel.
  4. Removes all 102 em-dash chart-bridge description actions + refs.
  5. Adds short-root + fuller descriptions on non-basic controls: 11 plain
     axes, 2 mouse axes, 2 full-throttle afterburner thresholds, the T-A4
     lights/light-amp tempo, 3 mode-dial detents, the T-WPN.up double-tap,
     T-B1, and the Nav-Mode latched Modifier.

Balanced block scanner at text level; preserves BOM + CRLF (newline="").
"""
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

PROFILE = Path(__file__).resolve().parent.parent / (
    "[Enhanced] MOZA MTQ + MHG/"
    "Joystick Gremlin Profile [ENH][MTQ+MHG][4.8.0][LIVE][R14].xml"
)

T_DEV = "b3167000-d436-11f0-8001-444553540000"  # MOZA MTQ throttle -> vjoy 1
R_DEV = "00ed3200-d437-11f0-8002-444553540000"  # MOZA MHG grip     -> vjoy 2

AXIS_NAMES = {1: "X-Axis", 2: "Y-Axis", 3: "Z-Axis", 4: "X-Rotation",
              5: "Y-Rotation", 6: "Z-Rotation", 7: "Slider", 8: "Dial"}

URDLP = ("up", "right", "down", "left", "press-in")

def hat(name, base, order=URDLP):
    return {base + i: f"{name}.{d}" for i, d in enumerate(order)}

T_MONIKERS = {
    1: "T-A1", 2: "T-A2", 3: "T-A3", 4: "T-A4",
    5: "T-NAV-1", 6: "T-HDG-4", 7: "T-SPD-2", 8: "T-ALT-5",
    9: "T-FD-3", 10: "T-AP-6",
    14: "T-E3.down", 15: "T-E3.up", 16: "T-E3.press-in",
    17: "T-MODE.nav", 18: "T-MODE.2", 19: "T-MODE.scm", 20: "T-MODE.4",
    21: "T-MODE.mining",
    22: "T-E2.press-in", 23: "T-E2.down", 24: "T-E2.up",
    25: "T-SW1.up", 26: "T-SW1.down", 27: "T-SW2.up", 28: "T-SW2.down",
    29: "T-SW3.up", 30: "T-SW3.down",
    36: "T-MODE.scm",
    50: "T-BRK.right", 51: "T-BRK.left",
    62: "T-M1.press-in", 63: "T-E1.up", 64: "T-E1.down", 65: "T-B1",
}
T_MONIKERS.update(hat("T-WPN", 52, ("press-in", "right", "left", "down", "up")))
T_MONIKERS.update(hat("T-COM", 57, ("press-in", "right", "left", "down", "up")))

R_MONIKERS = {
    1: "MAIN-TRIG.stage-1", 2: "R-LNCH", 3: "R-PINKY", 4: "R-AUX",
    5: "R-REV", 6: "MAIN-TRIG.stage-2",
    22: "R-CTL.right", 23: "R-CTL.left", 24: "R-CTL.press-in",
    50: "R-BB-1", 51: "R-BB-3", 52: "R-BB-4", 53: "R-BB-5",
    54: "R-BB-6", 55: "R-BB-7", 56: "R-BB-8",
}
R_MONIKERS.update(hat("R-TGT", 7))
R_MONIKERS.update(hat("R-DATA", 12))
R_MONIKERS.update(hat("R-DEF", 17))
R_MONIKERS.update(hat("R-POV", 25, ("up", "right", "down", "left")))

BUTTON_MONIKERS = {T_DEV: T_MONIKERS, R_DEV: R_MONIKERS}

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
AB_SHORT = "Full Throttle - Boost (Afterburner)"
AB_DESC = ("Pushing this throttle lever past 90% of its travel presses and "
           "holds Boost (afterburner). Easing back below 90% releases it.")
MODIFIER_DESC = ("Hold the Modifier button (T-B1) to switch on the Modifier "
                 "layer, a temporary shift that gives most buttons a second "
                 "function while held. Release to return. Nothing is sent to "
                 "the game; it only changes Joystick Gremlin's layer.")
NAVMOD_DESC = ("In NAV mode only, flipping Config Down (T-SW2) holds the "
               "Modifier layer on for as long as the switch stays down - a "
               "latched Modifier. It sends nothing to the game by itself; "
               "T-B1 keeps working as the held Modifier too.")
MODE_LABELS = {  # change-mode action labels, keyed by (device, input-id)
    (T_DEV, 65): 'T-B1 "Modifier | Modifier" Hold-only Modifier mode (chord layer). Reverts on release.',
    (T_DEV, 28): 'T-SW2.down "Modifier | Modifier" NAV only: latched Modifier while the switch is down.',
}
RESET3P_QUOTE = '"Reset 3rd Person Camera | Camera" F4 + camera chord, 0.5s hold.'
LIGHTAMP_NOTE = "Clean 100ms tap on the light-amp slot. Activation-mode must stay release (not both)."

# (device, input-id, mode) -> (short root label, fuller description)
SPECIAL_ROOTS = {
    (T_DEV, 4, "SCM Mode"): ("Tempo (Tap/Hold) Lights / Light Amp",
                             "Tap toggles the ship lights. Hold about half a "
                             "second to toggle Light Amplification (night "
                             "vision); it runs through a macro because Star "
                             "Citizen only accepts a quick tap on that bind."),
    (T_DEV, 17, "SCM Mode"): ("Mode Dial Pos 1 - NAV Mode",
                              "Position 1 of the five-detent mode dial. "
                              "Resting the dial here holds the button down; "
                              "after about half a second it sets NAV master "
                              "mode and Joystick Gremlin's NAV layer follows "
                              "along. Snapping past the detent does nothing."),
    (T_DEV, 19, "SCM Mode"): ("Mode Dial Pos 3 - SCM Mode",
                              "Position 3 of the five-detent mode dial. "
                              "Resting the dial here holds the button down; "
                              "after about half a second it sets SCM master "
                              "mode and returns Joystick Gremlin to the SCM "
                              "layer. Snapping past the detent does nothing."),
    (T_DEV, 21, "SCM Mode"): ("Mode Dial Pos 5 - Mining/Salvage",
                              "Position 5 of the five-detent mode dial. "
                              "Resting the dial here holds the button down; "
                              "after about half a second it switches to "
                              "mining/salvage operator mode and Joystick "
                              "Gremlin's Auxiliary layer follows along."),
    (T_DEV, 56, "SCM Mode"): ("Double-Tap - Camera / Reset 3rd Person",
                              "Press cycles the camera view (1st/3rd person, "
                              "docking view). A quick double-tap runs a macro "
                              "that holds F4 plus the camera button for half "
                              "a second to reset the 3rd-person camera, since "
                              "Star Citizen has no direct reset bind."),
    (T_DEV, 65, "SCM Mode"): ("Modifier", MODIFIER_DESC),
    (T_DEV, 28, "Nav Mode"): ("Modifier (NAV layer)", NAVMOD_DESC),
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
    unidentified = []

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

    def label_leaves(tempo_action, mon, containers):
        for cont, suffix in containers:
            c = tempo_action.find(cont)
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
                        set_label(ref.text, f"{mon}{suffix} {RESET3P_QUOTE}")
                    else:
                        set_label(ref.text, f"{mon}{suffix} {LIGHTAMP_NOTE}")
                else:
                    raise ValueError(f"unhandled tempo/double-tap leaf {lt}")

    for inp in root.find("inputs"):
        dev = inp.findtext("device-id")
        itype = inp.findtext("input-type")
        iid = int(inp.findtext("input-id"))
        mode = inp.findtext("mode")
        side_mons = BUTTON_MONIKERS[dev]
        side = "T-" if dev == T_DEV else "R-"

        axis_mon = side + AXIS_NAMES[iid] if itype == "axis" else None

        for cfg in inp.findall("action-configuration"):
            rid = cfg.findtext("root-action")
            beh = cfg.findtext("behavior")
            ra = lib[rid]
            acts = ra.find("actions")
            kids = [r.text for r in acts.findall("action-id")] if acts is not None else []
            kid_types = [lib[k].get("type") for k in kids]
            has_mouse = "map-to-mouse" in kid_types

            if itype == "axis" and beh == "button":
                # full-throttle afterburner threshold: emits carry the
                # axis moniker + .full; root gets short + fuller description
                set_label(rid, AB_SHORT)
                desc_additions.append((rid, 0, AB_DESC))
                for k, kt in zip(kids, kid_types):
                    if kt == "description":
                        desc_removals.add(k)
                        continue
                    assert kt == "map-to-vjoy", f"unexpected threshold child {kt}"
                    set_label(k, f"{axis_mon}.full")
                continue

            mon = axis_mon if itype == "axis" else side_mons.get(iid)
            if itype == "button" and mon is None and kids:
                unidentified.append((side, iid, mode))

            for k, kt in zip(kids, kid_types):
                a = lib[k]
                if kt == "description":
                    desc_removals.add(k)
                    continue
                if mon is None:
                    continue  # unidentified ids keep their labels
                if kt == "map-to-vjoy":
                    set_label(k, mon)
                elif kt == "response-curve":
                    pass  # keep existing curve labels
                elif kt == "map-to-mouse":
                    set_label(k, MOUSE_LABELS[get_prop(a, "direction")])
                elif kt == "change-mode":
                    # standalone Modifier switch: moniker + authored quote
                    set_label(k, MODE_LABELS[(dev, iid)])
                elif kt == "tempo":
                    set_label(k, mon)
                    label_leaves(a, mon, (("short-actions", ".tap"),
                                          ("long-actions", ".hold")))
                elif kt == "double-tap":
                    set_label(k, mon)
                    label_leaves(a, mon, (("single-actions", ".tap"),
                                          ("double-actions", ".double-tap")))
                else:
                    raise ValueError(f"unhandled root child type {kt}")

            # ---- root labels + fresh descriptions (non-basic only) ----
            if itype == "axis" and has_mouse:
                a = lib[kids[kid_types.index("map-to-mouse")]]
                set_label(rid, "Axis to Mouse Axis (3rd Person Freelook)")
                desc_additions.append((rid, 1, MOUSE_DESC[get_prop(a, "direction")]))
            elif itype == "axis":
                set_label(rid, "Response Curve (For Inversion)")
                desc_additions.append((rid, 1, AXIS_DESC))
            elif (dev, iid, mode) in SPECIAL_ROOTS:
                short, desc = SPECIAL_ROOTS[(dev, iid, mode)]
                set_label(rid, short)
                desc_additions.append((rid, 0, desc))

    # ---------- report ----------
    print(f"label edits: {len(label_edits)}")
    print(f"description removals: {len(desc_removals)}")
    print(f"description additions: {len(desc_additions)}")
    if unidentified:
        print(f"unidentified inputs (labels kept): "
              f"{sorted(set((s, i) for s, i, m in unidentified))}")
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
            for cont in ("actions", "short-actions", "long-actions",
                         "single-actions", "double-actions"):
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
