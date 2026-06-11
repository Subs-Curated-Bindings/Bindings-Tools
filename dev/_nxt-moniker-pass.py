#!/usr/bin/env python3
"""NXT moniker pass — migrate the Gladiator NXT JG profile to the settled
physical-moniker convention (SOL-R 2, 2026-06-05).

What it does (all in one idempotent pass):
  1. Puts a physical moniker on every bottom-tier emitting action's
     action-label (map-to-vjoy / tempo wrappers / tempo leaves / macros),
     across all modes. Tempo leaves carry the full `<moniker>.tap/.hold`.
  2. Strips redundant quoted friendly-labels (anything that fires a
     layout-resolvable vjoy). Keeps the load-bearing quotes: the L-D1 pinky
     change-mode, the two map-to-mouse camera emits, and the two
     keyboard-chord macros (Dock/Undock, Reset Freelook).
  3. Sets parallel-emit change-modes (inside tempo holds) to the `None`
     sentinel — the companion vjoy drives the identity.
  4. Removes every old chart-bridge description action (bare etched names +
     em-dash bodies) and the L-btn-8 desc-only action-configuration.
  5. Adds the short-root + fuller-description pair on every non-basic
     control: 12 axes, 5 tempo routes (SCM only — one route gives the
     short), and the pinky Modifier change-mode.

The L 125-128 inputs are R13 placeholders and are excluded (labels stay
'Map to vJoy'), matching SOL-R button 29.

Text-level edits preserve the BOM + LF line endings (newline="").
"""
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

PROFILE = Path(__file__).resolve().parent.parent / (
    "[Enhanced] Dual VKB Gladiator NXT/"
    "Joystick Gremlin Profile [ENH][NXT][4.8.1][LIVE][R14].xml"
)

L_DEV = "7d12d5c0-43ea-11f0-800a-444553540000"
R_DEV = "ec8bbeb0-4009-11f0-8002-444553540000"

AXIS_NAMES = {1: "X-Axis", 2: "Y-Axis", 3: "Z-Axis",
              4: "X-Rotation", 5: "Y-Rotation", 6: "Z-Rotation"}

BUTTON_MONIKERS_L = {
    1: "MAIN-TRIG-L.stage-1", 2: "MAIN-TRIG-L.stage-2",
    3: "L-A2", 4: "L-B1", 5: "L-D1",
    6: "L-A3.up", 7: "L-A3.right", 8: "L-A3.down", 9: "L-A3.left", 10: "L-A3.press-in",
    11: "L-A4.up", 12: "L-A4.right", 13: "L-A4.down", 14: "L-A4.left", 15: "L-A4.press-in",
    16: "L-C1.up", 17: "L-C1.right", 18: "L-C1.down", 19: "L-C1.left", 20: "L-C1.press-in",
    21: "RAPID-TRIG-L.up", 22: "RAPID-TRIG-L.down",
    23: "L-EN1.up", 24: "L-EN1.down",
    25: "L-SW1.up", 26: "L-SW1.down",
    27: "L-F1", 28: "L-F2", 29: "L-F3",
}
BUTTON_MONIKERS_R = {
    1: "MAIN-TRIG-R.stage-1", 2: "MAIN-TRIG-R.stage-2",
    3: "R-A2", 4: "R-B1", 5: "R-D1",
    6: "R-A3.up", 7: "R-A3.right", 8: "R-A3.down", 9: "R-A3.left", 10: "R-A3.press-in",
    # Same enumeration as every other NXT hat: base+0=up, +1=right, +2=down, +3=left.
    # (The old 4.8.0 bridges had R-A4 up/down swapped -- a matcher artifact, not hardware.)
    11: "R-A4.up", 12: "R-A4.right", 13: "R-A4.down", 14: "R-A4.left", 15: "R-A4.press-in",
    16: "R-C1.up", 17: "R-C1.right", 18: "R-C1.down", 19: "R-C1.left", 20: "R-C1.press-in",
    21: "RAPID-TRIG-R.up", 22: "RAPID-TRIG-R.down",
    23: "R-EN1.up", 24: "R-EN1.down",
    25: "R-SW1.up", 26: "R-SW1.down",
    27: "R-F1", 28: "R-F2", 29: "R-F3",
}
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

# (device, input-id) -> (short root label, fuller description) for the SCM
# tempo routes. One route gives the short — Aux/Nav routes stay bare.
TEMPO_ROOTS = {
    (L_DEV, 3): ("Tempo (Tap/Hold) Master Mode",
                 "Tap cycles your operator mode. Hold about half a second to "
                 "jump between master modes: from SCM it sets NAV; from NAV "
                 "or Auxiliary it drops back to SCM. Joystick Gremlin's "
                 "active layer follows along."),
    (R_DEV, 3): ("Tempo (Tap/Hold) Quick Repair / Aux Mode",
                 "Tap fires the MFD quick-action (repair all). Hold about "
                 "half a second to enter Auxiliary mode for mining and "
                 "salvage; once in Auxiliary, the hold cycles your master "
                 "mode instead. Joystick Gremlin's active layer follows "
                 "along."),
    (L_DEV, 8): ("Tempo (Tap/Hold) Landing / Docking",
                 "Tap toggles your landing gear (or auto-lands / requests "
                 "docking when available). Hold about half a second to send "
                 "a quick Right Alt+N chord -- Star Citizen's dock/undock "
                 "toggle, which can't be bound to a stick button directly."),
    (L_DEV, 15): ("Tempo (Tap/Hold) Freelook / Reset Freelook",
                  "Tap toggles freelook. Hold about half a second to "
                  "recenter the camera: a macro holds F4 plus the freelook "
                  "button for half a second, since Star Citizen won't let "
                  "you bind the recenter directly."),
    (L_DEV, 21): ("Tempo (Tap/Hold) Scan Ping / Light Amp",
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
        if dev == L_DEV:
            if iid in EXCLUDED_BUTTONS_L:
                return None
            return BUTTON_MONIKERS_L[iid]
        return BUTTON_MONIKERS_R[iid]
    raise ValueError(f"unexpected input type {itype}")


def get_label(a):
    for pr in a.findall("property"):
        if pr.findtext("name") == "action-label":
            return pr.findtext("value") or ""
    return ""


def main(apply=False):
    raw = PROFILE.read_text(encoding="utf-8", newline="")
    root = ET.fromstring(raw)
    lib = {a.get("id"): a for a in root.find("library")}

    label_edits = {}      # action-id -> new label
    desc_removals = set() # description action-ids to drop (block + refs)
    root_removals = set() # root action-ids to drop (the desc-only cfg)
    cfg_removals = []     # root-action ids whose <action-configuration> to drop
    desc_additions = []   # (root_id, index, text) — index into surviving refs
    report = []

    def set_label(aid, new):
        old = get_label(lib[aid])
        if old != new:
            label_edits[aid] = new
            report.append(f"  label [{lib[aid].get('type')}] {old!r} -> {new!r}")

    def macro_has_keys(a):
        return any(ma.get("type") == "key" for ma in a.iter("macro-action"))

    def keep_quote_tail(label):
        """Existing '"Label | Cat" note' portion of a label, sans any prefix."""
        m = re.search(r'"[^"]*".*$', label, re.S)
        return m.group(0) if m else label

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

            # the L btn 8 desc-only cfg: root whose only child is a description
            if kid_types == ["description"]:
                cfg_removals.append(rid)
                root_removals.add(rid)
                desc_removals.add(kids[0])
                report.append(f"L button 8 SCM: removing desc-only action-configuration ({rid})")
                continue

            has_curve = "response-curve" in kid_types
            has_mouse = "map-to-mouse" in kid_types
            has_tempo = "tempo" in kid_types
            surviving = []  # non-description children, in order

            for k, kt in zip(kids, kid_types):
                a = lib[k]
                if kt == "description":
                    desc_removals.add(k)
                    continue
                surviving.append(k)
                if mon is None:
                    continue  # placeholder inputs keep their labels
                if kt == "map-to-vjoy":
                    set_label(k, mon)
                elif kt == "response-curve":
                    pass  # keep existing curve labels
                elif kt == "map-to-mouse":
                    pass  # load-bearing quote, no moniker (SOL-R precedent)
                elif kt == "change-mode":
                    # standalone pinky change-mode: moniker + kept quote
                    set_label(k, f"{mon} {keep_quote_tail(get_label(a))}")
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
                                    tail = keep_quote_tail(get_label(la))
                                    set_label(ref.text, f"{mon}{suffix} {tail}")
                                else:
                                    set_label(ref.text, f"{mon}{suffix}")

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
    print(f"cfg removals: {len(cfg_removals)}")
    for line in report:
        print(line)
    if not apply:
        print("\nDRY RUN — re-run with --apply to write.")
        return

    # ---------- text-level application ----------
    text = raw

    # 1. remove the desc-only action-configuration block (inputs section)
    for rid in cfg_removals:
        pat = re.compile(
            r"\n            <action-configuration>\s*"
            r"<root-action>" + re.escape(rid) + r"</root-action>.*?"
            r"</action-configuration>", re.S)
        text, n = pat.subn("", text)
        assert n == 1, f"cfg removal failed for {rid}"

    # 2. library edits, block by block
    lib_pat = re.compile(
        r'(        <action id="([0-9a-f-]+)" type="([a-z-]+)">.*?\n        </action>\n)',
        re.S)

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    add_by_root = {}
    for rid, idx, dtext in desc_additions:
        add_by_root[rid] = (idx, dtext, str(uuid.uuid4()))

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

    out = []
    lib_start = text.index("<library>")
    lib_end = text.index("</library>")
    head, lib_text, tail = text[:lib_start], text[lib_start:lib_end], text[lib_end:]

    pos = 0
    pieces = []
    for m in lib_pat.finditer(lib_text):
        pieces.append(lib_text[pos:m.start()])
        block, aid, typ = m.group(1), m.group(2), m.group(3)
        pos = m.end()
        if aid in desc_removals or aid in root_removals:
            continue  # drop block
        # strip refs to removed descriptions
        for did in desc_removals:
            block = re.sub(
                r"\n\s*<action-id>" + re.escape(did) + r"</action-id>", "", block)
        # label edit
        if aid in label_edits:
            block, n = re.subn(
                r"(<name>action-label</name>\s*\n\s*<value>)[^<]*(</value>)",
                lambda mm: mm.group(1) + esc(label_edits[aid]) + mm.group(2),
                block)
            assert n == 1, f"label edit failed for {aid}"
        # description-ref insertion + new block before the root
        if aid in add_by_root:
            idx, dtext, new_id = add_by_root[aid]
            pieces.append(desc_block(new_id, dtext))
            refs = re.findall(r"<action-id>[0-9a-f-]+</action-id>", block)
            new_ref = f"<action-id>{new_id}</action-id>"
            anchor_idx = min(idx, len(refs))
            if anchor_idx == len(refs):
                # append after last ref
                block = block.replace(refs[-1], refs[-1] + "\n                " + new_ref, 1)
            else:
                block = block.replace(refs[anchor_idx], new_ref + "\n                " + refs[anchor_idx], 1)
        pieces.append(block)
    pieces.append(lib_text[pos:])
    text = head + "".join(pieces) + tail

    # also strip refs to removed descriptions anywhere outside library (none expected)
    for did in desc_removals | root_removals:
        assert f">{did}<" not in text, f"dangling reference to removed action {did}"

    PROFILE.write_text(text, encoding="utf-8", newline="")
    print(f"\nWROTE {PROFILE}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
