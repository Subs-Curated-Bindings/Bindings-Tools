#!/usr/bin/env python3
"""GF moniker pass — migrate the Dual VKB Gunfighter JG profile to the settled
physical-moniker convention (SOL-R 2026-06-05, NXT 2026-06-11).

The Gunfighter grips are the same SCG family as the NXT's, so the monikers
reuse the NXT grip names (L-A2, L-B1, L-D1, L-A3.up, RAPID-TRIG-L.up,
MAIN-TRIG-R.stage-2, ...). The GF enumerates differently from the NXT:
A4 hat = buttons 6-10, A3 = 11-15, A1-ministick-in-button-mode = 16-20
(unbound; the bound path is the POV hat -> vjoy hat), C1 = 21-25, rapid
trigger = 26-27. No base buttons. L buttons 125-128 are R13 placeholders
(master-mode/mining slots fired by the tempo holds) and stay excluded.

What it does in one idempotent pass:
  1. Moniker on every bottom-tier emitting action across all modes; tempo
     leaves carry the full `<moniker>.tap/.hold`.
  2. Authors the load-bearing quoted labels (GF never had the quoted-label
     pass): 3x L-D1 pinky change-modes, 2 mouse-camera emits, the Reset
     Freelook keyboard macro + its Modifier-layer map-to-keyboard twin.
  3. Parallel-emit change-modes (inside tempo holds) -> the `None` sentinel.
  4. Removes all 70 em-dash chart-bridge description actions + their refs.
  5. Adds short-root + fuller descriptions on non-basic controls: 10 axes
     (8 inversion curves + 2 mouse-camera), 5 SCM tempo routes, the pinky.

Text-level edits use a balanced block scanner (the GF library has two blocks
glued to the previous `</action>` on one line, so line-anchored regex is
unsafe). Preserves the BOM + LF line endings (newline="").
"""
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

PROFILE = Path(__file__).resolve().parent.parent / (
    "[Enhanced] Dual VKB Gunfighter Binds/"
    "Joystick Gremlin Profile [ENH][GF][4.8.0][LIVE][R14].xml"
)

L_DEV = "0dcdeb30-d727-11ef-8013-444553540000"  # VKBSim Space Gunfighter L -> vjoy 1
R_DEV = "0dcd7600-d727-11ef-800a-444553540000"  # VKBSim Space Gunfighter   -> vjoy 2

AXIS_NAMES = {1: "X-Axis", 2: "Y-Axis", 3: "Z-Axis",
              4: "X-Rotation", 5: "Y-Rotation"}

# Every GF hat enumerates base+0=up, +1=right, +2=down, +3=left, +4=press-in
# (verified uniform across A4/A3/C1 on both grips; A1-as-buttons assumed same).
def hat_block(name, base):
    return {base: f"{name}.up", base + 1: f"{name}.right",
            base + 2: f"{name}.down", base + 3: f"{name}.left",
            base + 4: f"{name}.press-in"}

def button_monikers(side):
    m = {1: f"MAIN-TRIG-{side}.stage-1", 2: f"MAIN-TRIG-{side}.stage-2",
         3: f"{side}-A2", 4: f"{side}-B1", 5: f"{side}-D1",
         26: f"RAPID-TRIG-{side}.up", 27: f"RAPID-TRIG-{side}.down"}
    m.update(hat_block(f"{side}-A4", 6))
    m.update(hat_block(f"{side}-A3", 11))
    m.update(hat_block(f"{side}-A1", 16))  # ministick in button mode (unbound)
    m.update(hat_block(f"{side}-C1", 21))
    return m

BUTTON_MONIKERS = {L_DEV: button_monikers("L"), R_DEV: button_monikers("R")}
EXCLUDED_BUTTONS_L = {125, 126, 127, 128}  # R13 1:1 placeholders

AXIS_DESC = ("A flat 1:1 response curve sits on this axis only so you can "
             "reverse its direction with Joystick Gremlin's Invert Curve "
             "button if your hardware reads it backwards. No other effect.")
MOUSE_DESC = {
    4: ("Routed to mouse Y so you can free-look up and down in 3rd-person "
        "flight. The flat center curve suppresses idle stick drift so the "
        "camera holds still."),
    5: ("Routed to mouse X so you can free-look left and right in 3rd-person "
        "flight. The flat center curve suppresses idle stick drift so the "
        "camera holds still."),
}
PINKY_DESC = ("Hold the pinky button (D1) to switch on the Modifier layer, a "
              "temporary shift that gives most buttons a second function "
              "while held. Release to return. Nothing is sent to the game; "
              "it only changes Joystick Gremlin's layer.")

# Authored quoted labels (load-bearing -- these emits can't resolve via the
# layout XML -> Binding Database).
PINKY_LABELS = {
    "Temporary": 'L-D1 "Modifier | Modifier" Hold-only Modifier mode (chord layer). Reverts on release.',
    "Previous": 'L-D1 "Modifier | Modifier" Pop mode stack -- return to the prior active mode.',
}
MOUSE_LABELS = {  # keyed by map-to-mouse `direction` property
    "90": '"Camera Tilt (Mouse Y) | Camera" Routed to mouse Y so you can free-look up/down while flying in 3rd person.',
    "0": '"Camera Pan (Mouse X) | Camera" Routed to mouse X so you can free-look left/right while flying in 3rd person.',
}
FREELOOK_MACRO_QUOTE = '"Reset Freelook | Camera" Holds F4 + the freelook button 0.5s to recenter.'
FREELOOK_KEYBOARD_QUOTE = '"Reset Freelook | Camera" Holds F4 + the freelook button to recenter.'

# (device, input-id) -> (short root label, fuller description) for the SCM
# tempo routes. One route gives the short -- Nav/Aux/Modifier routes stay bare.
TEMPO_ROOTS = {
    (L_DEV, 3): ("Tempo (Tap/Hold) Master Mode",
                 "Tap cycles your operator mode. Hold about half a second to "
                 "jump between master modes: from SCM it sets NAV; from NAV "
                 "or Auxiliary it drops back to SCM. Joystick Gremlin's "
                 "active layer follows along."),
    (R_DEV, 3): ("Tempo (Tap/Hold) Bomb Impact / Aux Mode",
                 "Tap toggles your bomb impact point (or the horn in a "
                 "ground vehicle). Hold about half a second to enter "
                 "Auxiliary mode for mining and salvage; once in Auxiliary, "
                 "the hold drops back to SCM. Joystick Gremlin's active "
                 "layer follows along."),
    (L_DEV, 10): ("Tempo (Tap/Hold) Freelook / Reset Freelook",
                  "Tap toggles freelook. Hold about half a second to "
                  "recenter the camera: a macro holds F4 plus the freelook "
                  "button for half a second, since Star Citizen won't let "
                  "you bind the recenter directly."),
    (L_DEV, 11): ("Tempo (Tap/Hold) Flight Ready / Light Amp",
                  "Tap readies the ship for flight (the same button is the "
                  "lights toggle, and a double-tap toggles port locks). Hold "
                  "about half a second to toggle Light Amplification (night "
                  "vision); it runs through a macro because Star Citizen "
                  "only accepts a quick tap on that bind."),
    (L_DEV, 26): ("Tempo (Tap/Hold) Scan Ping / Light Amp",
                  "Tap fires a radar ping. Hold about half a second to "
                  "toggle Light Amplification (night vision); it runs "
                  "through a macro because Star Citizen only accepts a "
                  "quick tap on that bind."),
}


def moniker_for(dev, itype, iid):
    iid = int(iid)
    side = "L" if dev == L_DEV else "R"
    if itype == "axis":
        return f"{side}-{AXIS_NAMES[iid]}"
    if itype == "hat":
        return f"{side}-A1"
    if itype == "button":
        if dev == L_DEV and iid in EXCLUDED_BUTTONS_L:
            return None
        return BUTTON_MONIKERS[dev][iid]
    raise ValueError(f"unexpected input type {itype}")


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
        if old != new:
            label_edits[aid] = new
            report.append(f"  [{a.get('type')}] {old!r} -> {new!r}")

    def macro_has_keys(a):
        return any(ma.get("type") == "key" for ma in a.iter("macro-action"))

    for inp in root.find("inputs"):
        dev = inp.findtext("device-id")
        itype = inp.findtext("input-type")
        iid = int(inp.findtext("input-id"))
        mode = inp.findtext("mode")
        mon = moniker_for(dev, itype, iid)
        is_scm = mode == "SCM Mode"

        for cfg in inp.findall("action-configuration"):
            rid = cfg.findtext("root-action")
            ra = lib[rid]
            kids = [r.text for r in ra.find("actions").findall("action-id")]
            kid_types = [lib[k].get("type") for k in kids]
            has_curve = "response-curve" in kid_types
            has_mouse = "map-to-mouse" in kid_types
            has_tempo = "tempo" in kid_types

            for k, kt in zip(kids, kid_types):
                a = lib[k]
                if kt == "description":
                    desc_removals.add(k)
                    continue
                if mon is None:
                    continue  # placeholder inputs keep their labels
                if kt == "map-to-vjoy":
                    set_label(k, mon)
                elif kt == "response-curve":
                    pass  # keep existing curve labels
                elif kt == "map-to-mouse":
                    set_label(k, MOUSE_LABELS[get_prop(a, "direction")])
                elif kt == "change-mode":
                    # standalone pinky change-mode: moniker + authored quote
                    set_label(k, PINKY_LABELS[get_prop(a, "change-type")])
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
                                    set_label(ref.text, f"{mon}{suffix} {FREELOOK_MACRO_QUOTE}")
                                else:
                                    set_label(ref.text, f"{mon}{suffix}")
                            elif lt == "map-to-keyboard":
                                set_label(ref.text, f"{mon}{suffix} {FREELOOK_KEYBOARD_QUOTE}")
                            else:
                                raise ValueError(f"unhandled tempo leaf type {lt}")
                else:
                    raise ValueError(f"unhandled root child type {kt}")

            # ---- root labels + fresh descriptions (non-basic only) ----
            if itype == "axis" and has_curve and not has_mouse:
                set_label(rid, "Response Curve (For Inversion)")
                desc_additions.append((rid, 1, AXIS_DESC))
            elif itype == "axis" and has_mouse:
                set_label(rid, "Axis to Mouse Axis (3rd Person Freelook)")
                desc_additions.append((rid, 1, MOUSE_DESC[iid]))
            elif has_tempo and is_scm and (dev, iid) in TEMPO_ROOTS:
                short, desc = TEMPO_ROOTS[(dev, iid)]
                set_label(rid, short)
                desc_additions.append((rid, 0, desc))
            elif itype == "button" and iid == 5 and dev == L_DEV and is_scm:
                set_label(rid, "Modifier")
                desc_additions.append((rid, 0, PINKY_DESC))

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

    def block_span(aid):
        """(start, end) of the `<action id="aid" ...>...</action>` block."""
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
        return f"""        <action id="{aid}" type="description">
            <property type="string">
                <name>description</name>
                <value>{esc(dtext)}</value>
            </property>
            <property type="string">
                <name>action-label</name>
                <value>Description</value>
            </property>
            <property type="activation-mode">
                <name>activation-mode</name>
                <value>disallowed</value>
            </property>
        </action>
"""

    for rid, idx, dtext in desc_additions:
        new_id = str(uuid.uuid4())
        s, e = block_span(rid)
        # insert the new block before the root block, at line start
        ls = text.rfind("\n", 0, s) + 1
        prefix = text[ls:s]
        assert prefix.strip() == "", f"root block {rid} not at line start"
        text = text[:ls] + desc_block(new_id, dtext) + text[ls:]
        # insert the ref inside the root's <actions> at position idx
        s, e = block_span(rid)
        block = text[s:e]
        refs = list(re.finditer(r"[ \t]*<action-id>[0-9a-f-]+</action-id>", block))
        assert refs, f"no refs in root {rid}"
        new_ref = f"                <action-id>{new_id}</action-id>\n"
        anchor = refs[min(idx, len(refs) - 1)] if idx < len(refs) else None
        if anchor is None:
            ins = refs[-1].end()
            block = block[:ins] + "\n" + new_ref.rstrip("\n") + block[ins:]
        else:
            block = block[:anchor.start()] + new_ref + block[anchor.start():]
        text = text[:s] + block + text[e:]

    # 5. sanity: no dangling references to removed actions
    for did in desc_removals:
        assert did not in text, f"dangling reference to removed action {did}"

    PROFILE.write_text(text, encoding="utf-8", newline="")
    print(f"\nWROTE {PROFILE}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
