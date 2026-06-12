#!/usr/bin/env python3
"""
Clone the NXT's Dock/Undock tempo onto the Gunfighter's L-A3.down (button 13).

The NXT puts a tap/hold tempo on L-A3.down: tap = the existing landing-gear
vjoy emit (vjoy1.13), hold = a Right Alt+N keyboard macro (SC's dock/undock
toggle, which can't be bound to a stick button). The GF shares the exact same
SCG grip + moniker, and its L-A3.down is currently a plain map-to-vjoy → vjoy1.13
(the same landing/docking emit), so the clone is 1:1: wrap that vjoy in a tempo
as the tap and add the RAlt+N macro as the hold.

Idempotent: bails if the macro is already present. Preserves LF (newline="").
Run tools/fix-library-order.py + tools/audit-jg-profile.py afterwards.
"""
import re, uuid, sys

PROFILE = "[Enhanced] Dual VKB Gunfighter Binds/Joystick Gremlin Profile [ENH][GF][4.8.1][LIVE][R14].xml"

ROOT_ID = "7986a859-4186-440e-a93f-aad924a28652"   # button 13 SCM root
VJOY_ID = "2f929000-6c4c-4782-b76e-7245ff5bd8fa"   # its map-to-vjoy vjoy1.13

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
        <value>Tap toggles your landing gear (or auto-lands / requests docking when available). Hold about half a second to send a quick Right Alt+N chord -- Star Citizen's dock/undock toggle, which can't be bound to a stick button directly.</value>
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
        <value>L-A3.down</value>
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
        <value>L-A3.down.hold "Dock/Undock | Flight Control" Quick Right Alt+N chord -- SC docking toggle</value>
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
    with open(PROFILE, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    if "Dock/Undock" in text:
        print("Docking macro already present — nothing to do.")
        return

    # 1) Relabel the existing vjoy emit: L-A3.down -> L-A3.down.tap (scoped).
    vs, ve = action_span(text, VJOY_ID)
    vblock = text[vs:ve].replace(
        "<value>L-A3.down</value>", "<value>L-A3.down.tap</value>"
    )
    text = text[:vs] + vblock + text[ve:]

    # 2) Rewire the root: single vjoy child -> [description, tempo]; relabel.
    rs, re_ = action_span(text, ROOT_ID)
    rblock = text[rs:re_]
    rblock = rblock.replace(
        f"<actions>\n                <action-id>{VJOY_ID}</action-id>\n            </actions>",
        f"<actions>\n                <action-id>{DESC_ID}</action-id>\n"
        f"                <action-id>{TEMPO_ID}</action-id>\n            </actions>",
    )
    rblock = rblock.replace(
        "<value>Root</value>", "<value>Tempo (Tap/Hold) Landing / Docking</value>"
    )
    if "<value>Tempo (Tap/Hold) Landing / Docking</value>" not in rblock:
        sys.exit("root rewire failed — actions block didn't match expected shape")
    text = text[:rs] + rblock + text[re_:]

    # 3) Insert the new library actions right after the vjoy block, in
    #    dependency order so no forward ref is created: the tempo references the
    #    macro + the (already-earlier) vjoy, and the button-13 root references
    #    the description + tempo, both of which now precede it. (The GF profile's
    #    `</library>` is unindented, which trips fix-library-order's bound
    #    matcher, so we order correctly up front rather than rely on it.)
    vs2, ve2 = action_span(text, VJOY_ID)
    insert = "\n" + DESC_BLOCK + "\n" + MACRO_BLOCK + "\n" + TEMPO_BLOCK
    text = text[:ve2] + insert + text[ve2:]

    with open(PROFILE, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"Added Dock/Undock tempo to GF L-A3.down.")
    print(f"  description={DESC_ID}\n  tempo={TEMPO_ID}\n  macro={MACRO_ID}")


if __name__ == "__main__":
    main()
