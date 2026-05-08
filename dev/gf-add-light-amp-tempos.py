"""
One-shot: wrap the existing map-to-vjoy on Gunfighter L btn 26 and L btn 11
in a tempo with a light-amplification-toggle macro long-action.

Pattern mirrors the NXT rapid-trigger setup (see references/sc-toggle-tap-pattern.md):
  - threshold 0.5s, activate-on=release
  - short-action: existing map-to-vjoy (tap pass-through)
  - long-action: 100ms tap macro on vJoy 2 button 46 (activation-mode=release)

After running, also bind v_light_amplification_toggle to js2_button46 in the
layout XML (separate edit).

Backs up the JG profile to <profile>.bak-yyyyMMdd-HHmmss.

Usage:
  python gf-add-light-amp-tempos.py
"""
import datetime
import os
import re
import shutil
import sys
import uuid


PROFILE = (
    r'..\[Enhanced] Dual VKB Gunfighter Binds'
    r'\Joystick Gremlin Profile [ENH][GF][4.8.0][PTU][R14].xml'
)

BUTTONS = [
    {
        'name': 'btn26',
        'root_id': '9588a1af-7d5b-46f6-afae-0739e5f1054e',
        'existing_mtv_id': '0921cd3b-0e19-4158-b45c-f230f1a9888f',
        'tempo_label': 'Tap: ping radar. Hold 0.5s: light amp toggle (via macro -- SC needs tap-shape).',
    },
    {
        'name': 'btn11',
        'root_id': '4b671697-d9d7-4bfa-b934-fa9f25257c82',
        'existing_mtv_id': 'f4cf8305-b9f9-452d-9bcd-b02a08dd88e6',
        'tempo_label': 'Tap: flightready / portlocks dbl / lights. Hold 0.5s: light amp toggle.',
    },
]

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

    for btn in BUTTONS:
        btn['macro_id'] = str(uuid.uuid4())
        btn['tempo_id'] = str(uuid.uuid4())

    positions = []
    for btn in BUTTONS:
        m = re.search(rf'<action id="{re.escape(btn["root_id"])}" type="root">', data)
        if not m:
            sys.exit(f'Root not found: {btn["root_id"]}')
        positions.append((m.start(), btn))

    positions.sort(key=lambda x: x[0], reverse=True)
    for offset, btn in positions:
        macro_xml = make_macro_xml(btn['macro_id'], MACRO_LABEL)
        tempo_xml = make_tempo_xml(
            btn['tempo_id'], btn['existing_mtv_id'], btn['macro_id'], btn['tempo_label']
        )
        insert = macro_xml + '\r\n        ' + tempo_xml + '\r\n        '
        data = data[:offset] + insert + data[offset:]

    for btn in BUTTONS:
        old_block = (
            f'<action id="{btn["root_id"]}" type="root">\r\n'
            f'            <actions>\r\n'
            f'                <action-id>{btn["existing_mtv_id"]}</action-id>\r\n'
            f'            </actions>'
        )
        new_block = (
            f'<action id="{btn["root_id"]}" type="root">\r\n'
            f'            <actions>\r\n'
            f'                <action-id>{btn["tempo_id"]}</action-id>\r\n'
            f'            </actions>'
        )
        if old_block not in data:
            sys.exit(f'Could not find root <actions> block for {btn["name"]}')
        data = data.replace(old_block, new_block, 1)

    out = data.encode('utf-8')
    open(profile, 'wb').write(out)
    print(f'orig: {orig_size}, new: {len(out)}, delta: {len(out)-orig_size:+d}')
    print()
    for btn in BUTTONS:
        print(f'  {btn["name"]}: tempo={btn["tempo_id"]}  macro={btn["macro_id"]}')


if __name__ == '__main__':
    main()
