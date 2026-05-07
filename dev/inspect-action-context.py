"""
Inspect a JG R14 profile and dump per-action context to help with action-label
authoring or debugging.

For each compound action (tempo, macro, response-curve, change-mode,
map-to-mouse), reports:
  - which physical input drives the root that contains it
  - what other actions it's paired with in the same root
  - type-specific details (curve points, change-type/target, macro sub-actions,
    map-to-mouse direction, etc.)

Helpful when writing action-labels in bulk -- gives you the "what does this do
and where does it live" view without having to click through JG's UI.

Usage:
  python inspect-action-context.py "<path to JG profile xml>"
       [--type tempo|macro|response-curve|change-mode|map-to-mouse]
       [--id-prefix abc12345]
"""
import argparse
import sys
import xml.etree.ElementTree as ET


def get_prop(a, name):
    for prop in a.findall('property'):
        n = prop.find('name')
        if n is not None and n.text == name:
            v = prop.find('value')
            return v.text if v is not None else None
    return None


def get_label(a):
    return get_prop(a, 'action-label') or ''


def inspect(profile_path, filter_type=None, filter_prefix=None):
    tree = ET.parse(profile_path)
    root = tree.getroot()

    actions = root.findall('./library/action')
    action_by_id = {a.attrib['id']: a for a in actions}
    action_type = {aid: a.attrib['type'] for aid, a in action_by_id.items()}

    # action_id -> list of root_ids that include it
    parent_roots = {}
    for a in actions:
        if a.attrib['type'] != 'root':
            continue
        rid = a.attrib['id']
        children_el = a.find('actions')
        if children_el is None:
            continue
        for c in children_el:
            if c.text:
                parent_roots.setdefault(c.text, []).append(rid)

    # root_id -> physical inputs that drive it
    input_drivers = {}
    device_name = {}
    for d in root.findall('./devices/device'):
        did = d.find('device-id').text if d.find('device-id') is not None else '?'
        dname = d.find('device-name').text if d.find('device-name') is not None else '?'
        device_name[did] = dname

    for inp in root.findall('./inputs/input'):
        did = inp.find('device-id').text
        mode = inp.find('mode').text
        itype = inp.find('input-type').text
        iid = inp.find('input-id').text
        for ac in inp.findall('action-configuration'):
            ra = ac.find('root-action')
            if ra is not None and ra.text:
                input_drivers.setdefault(ra.text, []).append((did, mode, itype, iid))

    def trace_to_input(action_id, depth=0):
        if depth > 6:
            return None
        if action_id in input_drivers:
            return input_drivers[action_id]
        for p in parent_roots.get(action_id, []):
            r = trace_to_input(p, depth + 1)
            if r:
                return r
        return None

    LABEL_TYPES = {'tempo', 'macro', 'response-curve', 'change-mode', 'map-to-mouse'}
    for a in actions:
        t = a.attrib['type']
        if t not in LABEL_TYPES:
            continue
        if filter_type and t != filter_type:
            continue
        aid = a.attrib['id']
        if filter_prefix and not aid.startswith(filter_prefix):
            continue

        drivers = trace_to_input(aid)
        if drivers:
            ds = []
            for did, mode, itype, iid in drivers:
                short_dev = device_name.get(did, did[:8])
                ds.append(f'{short_dev} {itype}{iid} ({mode})')
            driver_str = ' | '.join(ds)
        else:
            driver_str = '-'

        detail = ''
        if t == 'change-mode':
            ct = get_prop(a, 'change-type')
            tm_el = a.find('target-mode')
            tm_name = ''
            if tm_el is not None:
                for prop in tm_el.findall('property'):
                    n = prop.find('name')
                    if n is not None and n.text == 'name':
                        v = prop.find('value')
                        tm_name = v.text if v is not None else ''
            detail = f'change-type={ct}, target={tm_name}'
        elif t == 'macro':
            subs = []
            for s in a.findall('macro-action'):
                stype = s.attrib.get('type', '?')
                if stype == 'vjoy':
                    vid = get_prop(s, 'vjoy-id')
                    btn = get_prop(s, 'input-id')
                    val = get_prop(s, 'value')
                    subs.append(f'vjoy{vid}.btn{btn}={val}')
                elif stype == 'pause':
                    subs.append(f'pause {get_prop(s, "duration")}s')
                elif stype == 'key':
                    subs.append(f'key sc={get_prop(s, "scan-code")} pressed={get_prop(s, "is-pressed")}')
            detail = ' / '.join(subs)
        elif t == 'map-to-mouse':
            detail = (f'direction={get_prop(a, "direction")}, '
                      f'min={get_prop(a, "min-speed")}, max={get_prop(a, "max-speed")}')
        elif t == 'response-curve':
            cp_el = a.find('control-points')
            cps = []
            if cp_el is not None:
                for prop in cp_el.findall('property'):
                    v = prop.find('value')
                    if v is not None and v.text:
                        cps.append(v.text)
            detail = f'curve-type={get_prop(a, "curve-type")}, points=[{", ".join(cps)}]'
        elif t == 'tempo':
            detail = (f'threshold={get_prop(a, "threshold")}, '
                      f'activate-on={get_prop(a, "activate-on")}')

        # Paired siblings in this action's root
        paired_str = ''
        for r in parent_roots.get(aid, []):
            siblings = []
            children_el = action_by_id[r].find('actions')
            if children_el is not None:
                for c in children_el:
                    if c.text and c.text != aid:
                        siblings.append(f'{action_type.get(c.text, "?")}({c.text[:8]})')
            if siblings:
                paired_str = '+'.join(siblings)

        print(f'\n{aid[:8]} ({t})')
        print(f'  driver: {driver_str}')
        if detail:
            print(f'  detail: {detail}')
        if paired_str:
            print(f'  paired: {paired_str}')
        cur = get_label(a)
        if cur:
            print(f'  label : {cur}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('profile', help='Path to the JG R14 profile XML')
    p.add_argument('--type', choices=['tempo', 'macro', 'response-curve', 'change-mode', 'map-to-mouse'],
                   help='Filter to one action type')
    p.add_argument('--id-prefix', help='Filter to actions whose ID starts with this prefix')
    args = p.parse_args()
    inspect(args.profile, args.type, args.id_prefix)


if __name__ == '__main__':
    main()
