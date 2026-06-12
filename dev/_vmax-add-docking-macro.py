#!/usr/bin/env python3
"""
Clone the NXT/GF Dock/Undock tempo onto the VMAX+AERO's T-H2.down (THR btn 12).

The NXT/GF put a tap/hold tempo on their docking control: tap = the existing
vjoy emit, hold = a Right Alt+N keyboard macro (SC's dock/undock toggle, which
can't be bound to a stick button directly). VMAX T-H2.down is currently a plain
map-to-vjoy → vjoy1.12 (Invoke Docking / Toggle Docking / [DT] Lights via the
layout), so the clone is 1:1: wrap that vjoy in a tempo as the tap and add the
RAlt+N macro as the hold, carrying the quoted "Dock/Undock | Flight Control"
label so it charts as Dock/Undock alongside the existing rows.

Only the SCM config is touched; the Modifier config (vjoy1.52 = Thruster Power
Toggle) is left alone. Idempotent (bails if the macro is already present).
Preserves the UTF-8 BOM + LF (newline=""). Run fix-library-order.py +
audit-jg-profile.py afterwards.
"""
import sys, uuid

PROFILE = ("[Enhanced] Virpil VMAX Throttle + Aeromax-R/"
           "Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.0][LIVE][R14].xml")

ROOT_ID = "f581a15c-17fb-4fbd-bdce-eb54bbd75c23"   # T-H2.down SCM root
VJOY_ID = "03169f16-1e2e-4ad1-a887-70399b8bfb92"   # its map-to-vjoy vjoy1.12

DESC_ID = str(uuid.uuid4())
TEMPO_ID = str(uuid.uuid4())
MACRO_ID = str(uuid.uuid4())

I = " " * 8  # an action's base indent in <library>


def block(s: str) -> str:
    """Re-indent a dedented action template to the library's 8-space base."""
    return "\n".join((I + ln if ln.strip() else "") for ln in s.strip("\n").split("\n"))


DESC_BLOCK = block(f'''
<action id="{DESC_ID}" type="description">
    <property type="string">
        <name>description</name>
        <value>Tap requests / toggles docking (the same as a normal press). Hold about half a second to send a quick Right Alt+N chord -- Star Citizen's dock/undock toggle, which can't be bound to a stick button directly.</value>
    </property>
    <property type="string">
        <name>action-label</name>
        <value>Description</value>
    </property>
    <property type="activation-mode">
        <name>activation-mode</name>
        <value>disallowed</value>
    </property>
</action>''')

TEMPO_BLOCK = block(f'''
<action id="{TEMPO_ID}" type="tempo">
    <short-actions>
        <action-id>{VJOY_ID}</action-id>
    </short-actions>
    <long-actions>
        <action-id>{MACRO_ID}</action-id>
    </long-actions>
    <property type="float">
        <name>threshold</name>
        <value>0.5</value>
    </property>
    <property type="string">
        <name>activate-on</name>
        <value>release</value>
    </property>
    <property type="string">
        <name>action-label</name>
        <value>T-H2.down</value>
    </property>
    <property type="activation-mode">
        <name>activation-mode</name>
        <value>disallowed</value>
    </property>
</action>''')

MACRO_BLOCK = block(f'''
<action id="{MACRO_ID}" type="macro">
    <property type="bool">
        <name>is-exclusive</name>
        <value>False</value>
    </property>
    <property type="string">
        <name>repeat-mode</name>
        <value>Single</value>
    </property>
    <property type="int">
        <name>repeat-count</name>
        <value>1</value>
    </property>
    <property type="float">
        <name>repeat-delay</name>
        <value>0.1</value>
    </property>
    <macro-action type="key">
        <property type="int">
            <name>scan-code</name>
            <value>56</value>
        </property>
        <property type="bool">
            <name>is-extended</name>
            <value>True</value>
        </property>
        <property type="bool">
            <name>is-pressed</name>
            <value>True</value>
        </property>
    </macro-action>
    <macro-action type="key">
        <property type="int">
            <name>scan-code</name>
            <value>49</value>
        </property>
        <property type="bool">
            <name>is-extended</name>
            <value>False</value>
        </property>
        <property type="bool">
            <name>is-pressed</name>
            <value>True</value>
        </property>
    </macro-action>
    <macro-action type="pause">
        <property type="float">
            <name>duration</name>
            <value>0.05</value>
        </property>
    </macro-action>
    <macro-action type="key">
        <property type="int">
            <name>scan-code</name>
            <value>49</value>
        </property>
        <property type="bool">
            <name>is-extended</name>
            <value>False</value>
        </property>
        <property type="bool">
            <name>is-pressed</name>
            <value>False</value>
        </property>
    </macro-action>
    <macro-action type="key">
        <property type="int">
            <name>scan-code</name>
            <value>56</value>
        </property>
        <property type="bool">
            <name>is-extended</name>
            <value>True</value>
        </property>
        <property type="bool">
            <name>is-pressed</name>
            <value>False</value>
        </property>
    </macro-action>
    <property type="string">
        <name>action-label</name>
        <value>T-H2.down.hold "Dock/Undock | Flight Control" Quick Right Alt+N chord -- SC docking toggle</value>
    </property>
    <property type="activation-mode">
        <name>activation-mode</name>
        <value>press</value>
    </property>
</action>''')


def action_span(text, action_id):
    start = text.find(f'<action id="{action_id}"')
    if start == -1:
        sys.exit(f"action {action_id} not found")
    end = text.index("</action>", start) + len("</action>")
    return start, end


def main():
    with open(PROFILE, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()

    if "Dock/Undock" in text:
        print("Docking macro already present -- nothing to do.")
        return

    # 1) Relabel the existing SCM vjoy emit: T-H2.down -> T-H2.down.tap (scoped
    #    to this action so the Modifier config's T-H2.down stays untouched).
    vs, ve = action_span(text, VJOY_ID)
    vblock = text[vs:ve].replace(
        "<value>T-H2.down</value>", "<value>T-H2.down.tap</value>"
    )
    text = text[:vs] + vblock + text[ve:]

    # 2) Rewire the SCM root: single vjoy child -> [description, tempo]; relabel.
    rs, re_ = action_span(text, ROOT_ID)
    rblock = text[rs:re_]
    rblock = rblock.replace(
        f"<actions>\n                <action-id>{VJOY_ID}</action-id>\n            </actions>",
        f"<actions>\n                <action-id>{DESC_ID}</action-id>\n"
        f"                <action-id>{TEMPO_ID}</action-id>\n            </actions>",
    )
    rblock = rblock.replace(
        "<value>Root</value>", "<value>Tempo (Tap/Hold) Docking</value>"
    )
    if "<value>Tempo (Tap/Hold) Docking</value>" not in rblock:
        sys.exit("root rewire failed -- actions block didn't match expected shape")
    text = text[:rs] + rblock + text[re_:]

    # 3) Insert the new library actions right after the vjoy block, in
    #    dependency order (vjoy already precedes; tempo refs macro + vjoy; the
    #    root refs description + tempo, both now earlier).
    vs2, ve2 = action_span(text, VJOY_ID)
    insert = "\n" + DESC_BLOCK + "\n" + MACRO_BLOCK + "\n" + TEMPO_BLOCK
    text = text[:ve2] + insert + text[ve2:]

    with open(PROFILE, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)
    print("Added Dock/Undock tempo to VMAX T-H2.down.")
    print(f"  description={DESC_ID}\n  tempo={TEMPO_ID}\n  macro={MACRO_ID}")


if __name__ == "__main__":
    main()
