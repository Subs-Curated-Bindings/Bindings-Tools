"""Rotate the 8 target-cycle SC actions in the Virpil layout XML to align
with the chart's mini-stick direction-to-action mapping.

Before (current layout):                After (chart-aligned):
  back            -> js2_button37         back            -> js2_button40  (LEFT gesture)
  under_reticle   -> js2_button38         under_reticle   -> js2_button37  (UP gesture)
  attacker_fwd    -> js2_button38         attacker_fwd    -> js2_button37  (UP gesture)
  fwd             -> js2_button39         fwd             -> js2_button38  (RIGHT gesture)
  reset (closest) -> js2_button40         reset (closest) -> js2_button39  (DOWN gesture)
"""
import sys, re

sys.stdout.reconfigure(encoding='utf-8')

LAYOUT = '[Enhanced] Virpil VMAX Throttle + Aeromax-R/layout_ENH_VMAX_AERO_480_LIVE_exported.xml'

# Per-action target rebind. Each action's <rebind input="..."/> gets the new slot.
remap = {
    # UP (btn 37)
    'v_target_under_reticle':         'js2_button37',
    'v_target_cycle_attacker_fwd':    'js2_button37',
    # RIGHT (btn 38)
    'v_target_cycle_hostile_fwd':     'js2_button38',
    'v_target_cycle_all_fwd':         'js2_button38',
    # DOWN (btn 39)
    'v_target_cycle_hostile_reset':   'js2_button39',
    'v_target_cycle_all_reset':       'js2_button39',
    # LEFT (btn 40)
    'v_target_cycle_hostile_back':    'js2_button40',
    'v_target_cycle_all_back':        'js2_button40',
}

with open(LAYOUT, 'rb') as f:
    raw = f.read()
bom = raw[:3] if raw[:3] == b'\xef\xbb\xbf' else b''
text = raw[len(bom):].decode('utf-8')

changes = []
for action_name, new_slot in remap.items():
    # Match: <action name="ACTION_NAME">[ws]<rebind input="...." [extra attrs]/>[ws]</action>
    # The rebind may carry additional attrs like multiTap="2", so we only
    # rewrite the `input="..."` value and preserve everything that follows.
    pat = re.compile(
        r'(<action\s+name="' + re.escape(action_name) + r'"\s*>\s*<rebind\s+input=")'
        r'([^"]*)'                    # captured: current input value
        r'("[^/>]*?/?>)',             # closing quote + any trailing attrs + element close
        re.DOTALL
    )
    matches = list(pat.finditer(text))
    if len(matches) == 0:
        if not re.search(r'<action\s+name="' + re.escape(action_name) + r'"', text):
            print(f'  SKIP: action "{action_name}" not in layout', file=sys.stderr)
            continue
        print(f'  FAIL: action "{action_name}" exists but rebind shape did not match', file=sys.stderr)
        sys.exit(2)
    if len(matches) != 1:
        print(f'  FAIL: action "{action_name}" matched {len(matches)} times (expected 1)', file=sys.stderr)
        sys.exit(2)
    m = matches[0]
    cur = m.group(2)
    changes.append((action_name, cur, new_slot))
    text = text[:m.start()] + m.group(1) + new_slot + m.group(3) + text[m.end():]

with open(LAYOUT, 'wb') as f:
    if bom:
        f.write(bom)
    f.write(text.encode('utf-8'))

print(f'Updated {LAYOUT}:')
for action_name, old, new in changes:
    marker = '  ' if old == new else ' *'
    print(f'  {marker} {action_name:40} {old} -> {new}')
