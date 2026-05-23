"""Add axis-as-button blocks to the Virpil VMAX+Aero JG R14 profile, wiring
the Aeromax-R mini-stick (axes 4+5, SCM Mode) to fire targeting vJoy
button slots, ordered to match Sub's other-hat convention: press->N,
up->N+1, right->N+2, down->N+3, left->N+4 (mini-stick has no press
input so we start at btn 37 for UP).

  axis 5 in [-1.0, -0.50]  ->  vJoy 2 btn 37  -- mini UP    (axis 5 polarity inverted from convention)
  axis 4 in [ 0.50,  1.0]  ->  vJoy 2 btn 38  -- mini RIGHT
  axis 5 in [ 0.50,  1.0]  ->  vJoy 2 btn 39  -- mini DOWN
  axis 4 in [-1.0, -0.50]  ->  vJoy 2 btn 40  -- mini LEFT

The SC layout currently binds these vJoy slots to:
  btn 37 = target cycle hostile/all backward
  btn 38 = target under reticle / cycle attacker fwd
  btn 39 = target cycle hostile/all forward
  btn 40 = target cycle hostile/all reset (closest)
  -- if the in-game mapping doesn't feel right, update the layout XML
     bindings, not these JG-side outputs.

Two inputs (axis 4 SCM, axis 5 SCM) get TWO new <action-configuration>
button blocks each. Additive: existing axis behavior is untouched. New
map-to-vjoy primitives are appended to <library> BEFORE the new root
actions (JG R14 requires backward refs).
"""
import sys, re, uuid

sys.stdout.reconfigure(encoding='utf-8')

PROF = '[Enhanced] Virpil VMAX Throttle + Aeromax-R/Joystick Gremlin Profile [ENH][VMAX+AERO][4.8.0][LIVE][R14].xml'
AERO = '40440b60-c93b-11f0-8002-444553540000'

with open(PROF, 'rb') as f:
    raw = f.read()
bom = raw[:3] if raw[:3] == b'\xef\xbb\xbf' else b''
text = raw[len(bom):].decode('utf-8')
sep = '\r\n' if '\r\n' in text else '\n'

# (axis_id, lower, upper, vjoy_btn, label_root)
# Mapping rotated to match Sub's other-hat convention: UP/RIGHT/DOWN/LEFT
# fire vJoy btn 37/38/39/40 in that order.
gestures = [
    (5, '-1.0', '-0.5', 37, 'Mini-stick Y past -50% (UP): hold vjoy 2 btn 37'),
    (4, '0.5',  '1.0',  38, 'Mini-stick X past +50% (RIGHT): hold vjoy 2 btn 38'),
    (5, '0.5',  '1.0',  39, 'Mini-stick Y past +50% (DOWN): hold vjoy 2 btn 39'),
    (4, '-1.0', '-0.5', 40, 'Mini-stick X past -50% (LEFT): hold vjoy 2 btn 40'),
]
plans = []
for axis_id, lo, hi, vbtn, label in gestures:
    plans.append({
        'axis_id': axis_id, 'lo': lo, 'hi': hi, 'vbtn': vbtn, 'label': label,
        'mtv_id': str(uuid.uuid4()), 'root_id': str(uuid.uuid4()),
    })

def make_mtv(mtv_id, vbtn):
    return (
        f'        <action id="{mtv_id}" type="map-to-vjoy">\n'
        f'            <property type="int">\n'
        f'                <name>vjoy-device-id</name>\n'
        f'                <value>2</value>\n'
        f'            </property>\n'
        f'            <property type="int">\n'
        f'                <name>vjoy-input-id</name>\n'
        f'                <value>{vbtn}</value>\n'
        f'            </property>\n'
        f'            <property type="input_type">\n'
        f'                <name>vjoy-input-type</name>\n'
        f'                <value>button</value>\n'
        f'            </property>\n'
        f'            <property type="bool">\n'
        f'                <name>button-inverted</name>\n'
        f'                <value>False</value>\n'
        f'            </property>\n'
        f'            <property type="string">\n'
        f'                <name>action-label</name>\n'
        f'                <value>Map to vJoy 2 btn {vbtn}</value>\n'
        f'            </property>\n'
        f'            <property type="activation-mode">\n'
        f'                <name>activation-mode</name>\n'
        f'                <value>both</value>\n'
        f'            </property>\n'
        f'        </action>'
    )

def make_root(root_id, mtv_id, label):
    return (
        f'        <action id="{root_id}" type="root">\n'
        f'            <actions>\n'
        f'                <action-id>{mtv_id}</action-id>\n'
        f'            </actions>\n'
        f'            <property type="string">\n'
        f'                <name>action-label</name>\n'
        f'                <value>{label}</value>\n'
        f'            </property>\n'
        f'            <property type="activation-mode">\n'
        f'                <name>activation-mode</name>\n'
        f'                <value>disallowed</value>\n'
        f'            </property>\n'
        f'        </action>'
    )

def make_action_cfg(root_id, lo, hi):
    return (
        f'            <action-configuration>\n'
        f'                <root-action>{root_id}</root-action>\n'
        f'                <behavior>button</behavior>\n'
        f'                <virtual-button>\n'
        f'                    <lower-limit>{lo}</lower-limit>\n'
        f'                    <upper-limit>{hi}</upper-limit>\n'
        f'                    <axis-button-direction>anywhere</axis-button-direction>\n'
        f'                </virtual-button>\n'
        f'            </action-configuration>'
    )

# Library order: primitives first, then roots (backward refs only).
lib_pieces = (
    [make_mtv(p['mtv_id'], p['vbtn']) for p in plans] +
    [make_root(p['root_id'], p['mtv_id'], p['label']) for p in plans]
)
new_lib_chunk = '\n'.join(lib_pieces).replace('\n', sep)

# Insert before </library>
lib_close = '    </library>'
if (lib_close + sep) not in text:
    print('Could not find "    </library>" in profile', file=sys.stderr)
    sys.exit(1)
text = text.replace(lib_close + sep, new_lib_chunk + sep + lib_close + sep, 1)
print(f'Library: appended {len(plans)} map-to-vjoy primitives + {len(plans)} root actions')

# Group plans by (axis_id, mode) -- both axes go in SCM Mode
by_axis = {}
for p in plans:
    by_axis.setdefault(p['axis_id'], []).append(p)

# For each axis input, find the existing <input> element and splice ALL new
# action-configurations in at once.
for axis_id, axis_plans in by_axis.items():
    # Match: <input>...AERO...axis...SCM Mode...input-id=axis_id...EXISTING axis action-cfg...</input>
    # Capture three groups: (input + existing axis cfg) / (whitespace before </input>) / (</input>)
    pat = re.compile(
        r'(<input>\s*'
        r'<device-id>' + re.escape(AERO) + r'</device-id>\s*'
        r'<input-type>axis</input-type>\s*'
        r'<mode>SCM Mode</mode>\s*'
        r'<input-id>' + str(axis_id) + r'</input-id>\s*'
        r'<action-configuration>\s*'
        r'<root-action>[0-9a-f-]+</root-action>\s*'
        r'<behavior>axis</behavior>\s*'
        r'</action-configuration>)(\s*)(</input>)',
        re.DOTALL
    )
    matches = list(pat.finditer(text))
    if len(matches) != 1:
        print(f'FAIL: Aero axis {axis_id} SCM Mode input did not uniquely match ({len(matches)} matches)', file=sys.stderr)
        sys.exit(2)
    m = matches[0]
    # Build all new action-configurations for this axis (joined by sep)
    new_cfgs = sep.join(
        make_action_cfg(p['root_id'], p['lo'], p['hi']).replace('\n', sep)
        for p in axis_plans
    )
    replacement = m.group(1) + sep + new_cfgs + m.group(2) + m.group(3)
    text = text[:m.start()] + replacement + text[m.end():]
    plans_str = ', '.join(f'[{p["lo"]},{p["hi"]}]->btn{p["vbtn"]}' for p in axis_plans)
    print(f'  Aero axis {axis_id} SCM: spliced {len(axis_plans)} button cfgs ({plans_str})')

with open(PROF, 'wb') as f:
    if bom:
        f.write(bom)
    f.write(text.encode('utf-8'))

print(f'Wrote profile: {PROF}')
