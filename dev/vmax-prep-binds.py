"""
One-shot for the VMAX 4.8.0 LIVE prep:
  1. Remove the two ghost <device> entries (placeholder GUIDs left over
     from earlier distribution prep -- zero <input> elements reference
     them, so removal is safe).
  2. Wrap the existing map-to-vjoy on VMAX throttle btn 11 (SCM Mode)
     in a tempo with a 100ms macro tap on vJoy 2 button 46 as the
     long-action -- mirrors the NXT/GF light-amp-toggle pattern.

Backs up the JG profile to <profile>.bak-yyyyMMdd-HHmmss.

Usage:
  python vmax-prep-binds.py
"""
import datetime
import os
import re
import shutil
import sys
import uuid


PROFILE = (
    r'..\[Enhanced] Virpil VMAX Throttle + Aeromax-R'
    r'\Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.0][LIVE][R14].xml'
)

GHOST_GUIDS = [
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
]

# Throttle btn 11 SCM Mode root + its child map-to-vjoy
BTN11_ROOT_ID = '0b24b750-12e2-4372-ab0c-00008d6c2193'
BTN11_MTV_ID  = '067a27ec-9461-404d-9a0b-71077eebbca9'
BTN11_TEMPO_LABEL = 'Tap: shield raise L / salvage focus L. Hold 0.5s: light amp toggle (macro tap).'

MACRO_LABEL = 'Clean 100ms tap on light-amp vJoy button. Activation-mode must stay "release" (not "both").'


def make_macro_xml(macro_id, label):
    return (
        f'<action id="{macro_id}" type="macro">\r\n'
        f'            <property type="bool">\r\n'
        f'                <name>is-exclusive</name>\r\n'
        f'                <value>False</value>\r\n'
        f'            </property>\r\n'
        f'            <property type="string">\r\n'
        f'                <name>repeat-mode</name>\r\n'
        f'                <value>Single</value>\r\n'
        f'            </property>\r\n'
        f'            <property type="int">\r\n'
        f'                <name>repeat-count</name>\r\n'
        f'                <value>1</value>\r\n'
        f'            </property>\r\n'
        f'            <property type="float">\r\n'
        f'                <name>repeat-delay</name>\r\n'
        f'                <value>0.1</value>\r\n'
        f'            </property>\r\n'
        f'            <macro-action type="vjoy">\r\n'
        f'                <property type="int">\r\n'
        f'                    <name>vjoy-id</name>\r\n'
        f'                    <value>2</value>\r\n'
        f'                </property>\r\n'
        f'                <property type="input_type">\r\n'
        f'                    <name>input-type</name>\r\n'
        f'                    <value>button</value>\r\n'
        f'                </property>\r\n'
        f'                <property type="int">\r\n'
        f'                    <name>input-id</name>\r\n'
        f'                    <value>46</value>\r\n'
        f'                </property>\r\n'
        f'                <property type="bool">\r\n'
        f'                    <name>value</name>\r\n'
        f'                    <value>True</value>\r\n'
        f'                </property>\r\n'
        f'            </macro-action>\r\n'
        f'            <macro-action type="pause">\r\n'
        f'                <property type="float">\r\n'
        f'                    <name>duration</name>\r\n'
        f'                    <value>0.1</value>\r\n'
        f'                </property>\r\n'
        f'            </macro-action>\r\n'
        f'            <macro-action type="vjoy">\r\n'
        f'                <property type="int">\r\n'
        f'                    <name>vjoy-id</name>\r\n'
        f'                    <value>2</value>\r\n'
        f'                </property>\r\n'
        f'                <property type="input_type">\r\n'
        f'                    <name>input-type</name>\r\n'
        f'                    <value>button</value>\r\n'
        f'                </property>\r\n'
        f'                <property type="int">\r\n'
        f'                    <name>input-id</name>\r\n'
        f'                    <value>46</value>\r\n'
        f'                </property>\r\n'
        f'                <property type="bool">\r\n'
        f'                    <name>value</name>\r\n'
        f'                    <value>False</value>\r\n'
        f'                </property>\r\n'
        f'            </macro-action>\r\n'
        f'            <property type="string">\r\n'
        f'                <name>action-label</name>\r\n'
        f'                <value>{label}</value>\r\n'
        f'            </property>\r\n'
        f'            <property type="activation-mode">\r\n'
        f'                <name>activation-mode</name>\r\n'
        f'                <value>release</value>\r\n'
        f'            </property>\r\n'
        f'        </action>'
    )


def make_tempo_xml(tempo_id, short_id, long_id, label):
    return (
        f'<action id="{tempo_id}" type="tempo">\r\n'
        f'            <short-actions>\r\n'
        f'                <action-id>{short_id}</action-id>\r\n'
        f'            </short-actions>\r\n'
        f'            <long-actions>\r\n'
        f'                <action-id>{long_id}</action-id>\r\n'
        f'            </long-actions>\r\n'
        f'            <property type="float">\r\n'
        f'                <name>threshold</name>\r\n'
        f'                <value>0.5</value>\r\n'
        f'            </property>\r\n'
        f'            <property type="string">\r\n'
        f'                <name>activate-on</name>\r\n'
        f'                <value>release</value>\r\n'
        f'            </property>\r\n'
        f'            <property type="string">\r\n'
        f'                <name>action-label</name>\r\n'
        f'                <value>{label}</value>\r\n'
        f'            </property>\r\n'
        f'            <property type="activation-mode">\r\n'
        f'                <name>activation-mode</name>\r\n'
        f'                <value>disallowed</value>\r\n'
        f'            </property>\r\n'
        f'        </action>'
    )


def main():
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    profile = os.path.normpath(os.path.join(tools_dir, PROFILE))
    if not os.path.exists(profile):
        sys.exit(f'Profile not found: {profile}')

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = f'{profile}.bak-{ts}'
    shutil.copy2(profile, backup)
    print(f'Backed up -> {backup}')

    data = open(profile, 'rb').read().decode('utf-8')
    orig_size = len(data.encode('utf-8'))

    # === Phase 1: remove ghost devices ===
    for guid in GHOST_GUIDS:
        pat = re.compile(
            rf'\r?\n\s*<device>\s*<device-id>{re.escape(guid)}</device-id>.*?</device>',
            re.DOTALL,
        )
        m = pat.search(data)
        if not m:
            print(f'  ghost {guid}: anchor not found, skipping')
            continue
        data = data[:m.start()] + data[m.end():]
        print(f'  removed ghost device {guid}')

    # === Phase 2: insert macro + tempo before btn 11 root, update root reference ===
    macro_id = str(uuid.uuid4())
    tempo_id = str(uuid.uuid4())

    # Find root start position
    m = re.search(rf'<action id="{re.escape(BTN11_ROOT_ID)}" type="root">', data)
    if not m:
        sys.exit(f'btn 11 root not found: {BTN11_ROOT_ID}')

    macro_xml = make_macro_xml(macro_id, MACRO_LABEL)
    tempo_xml = make_tempo_xml(tempo_id, BTN11_MTV_ID, macro_id, BTN11_TEMPO_LABEL)
    insert = macro_xml + '\r\n        ' + tempo_xml + '\r\n        '
    data = data[:m.start()] + insert + data[m.start():]

    # Update root <actions><action-id> to point at new tempo
    old_block = (
        f'<action id="{BTN11_ROOT_ID}" type="root">\r\n'
        f'            <actions>\r\n'
        f'                <action-id>{BTN11_MTV_ID}</action-id>\r\n'
        f'            </actions>'
    )
    new_block = (
        f'<action id="{BTN11_ROOT_ID}" type="root">\r\n'
        f'            <actions>\r\n'
        f'                <action-id>{tempo_id}</action-id>\r\n'
        f'            </actions>'
    )
    if old_block not in data:
        sys.exit('btn 11 root <actions> block did not match expected pattern')
    data = data.replace(old_block, new_block, 1)

    out = data.encode('utf-8')
    open(profile, 'wb').write(out)
    print(f'\norig: {orig_size}, new: {len(out)}, delta: {len(out)-orig_size:+d}')
    print(f'tempo: {tempo_id}')
    print(f'macro: {macro_id}')


if __name__ == '__main__':
    main()
