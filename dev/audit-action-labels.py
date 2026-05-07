"""
Audit JG R14 profile action-labels per the project style guide.

Lists every compound action (tempo, macro, response-curve, change-mode,
map-to-mouse) and reports whether its action-label is the JG default
("Tempo", "Macro", etc.) or a custom natural-language description.

Project style: every compound action should have a custom label, ~80 chars
target, max 100. See references/jg-action-labels.md.

Usage:
  python audit-action-labels.py "<path to JG profile xml>"
"""
import sys
import xml.etree.ElementTree as ET


LABEL_TYPES = {'tempo', 'macro', 'response-curve', 'change-mode', 'map-to-mouse'}
DEFAULT_LABELS = {
    'tempo': 'Tempo',
    'macro': 'Macro',
    'response-curve': 'Response Curve',
    'change-mode': 'Change Mode',
    'map-to-mouse': 'Map to Mouse',
}


def get_label(a):
    for prop in a.findall('property'):
        n = prop.find('name')
        if n is not None and n.text == 'action-label':
            v = prop.find('value')
            return (v.text if v is not None and v.text else '')
    return ''


def audit(profile_path):
    tree = ET.parse(profile_path)
    root = tree.getroot()

    rows = []
    for a in root.findall('./library/action'):
        t = a.attrib['type']
        if t not in LABEL_TYPES:
            continue
        label = get_label(a)
        rows.append((a.attrib['id'], t, label, len(label)))

    # Group
    from collections import defaultdict
    by_type = defaultdict(list)
    for r in rows:
        by_type[r[1]].append(r)

    print(f'Profile: {profile_path}\n')
    print('=== Summary ===')
    for t in sorted(by_type):
        total = len(by_type[t])
        generic = sum(1 for r in by_type[t] if r[2].strip() == DEFAULT_LABELS[t])
        custom = total - generic
        print(f'  {t:18s}: {total} total, {custom} custom, {generic} generic')

    # Generic ones (need labels)
    print('\n=== Generic-labeled (need updating) ===')
    any_generic = False
    for t in sorted(by_type):
        gs = [r for r in by_type[t] if r[2].strip() == DEFAULT_LABELS[t]]
        if gs:
            any_generic = True
            print(f'\n  {t}: {len(gs)} actions still labeled "{DEFAULT_LABELS[t]}"')
            for r in gs:
                print(f'    {r[0][:8]}')
    if not any_generic:
        print('  (none)')

    # Custom ones (length check)
    print('\n=== Custom-labeled ===')
    for t in sorted(by_type):
        cs = [r for r in by_type[t] if r[2].strip() != DEFAULT_LABELS[t]]
        if cs:
            print(f'\n  {t}: {len(cs)} actions')
            for r in cs:
                marker = ''
                if r[3] > 100:
                    marker = ' (LONG -- over 100 chars)'
                elif r[3] > 80:
                    marker = ' (over 80 chars)'
                print(f'    {r[0][:8]} ({r[3]:3d}){marker}: {r[2][:90]}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: audit-action-labels.py <profile.xml>')
    audit(sys.argv[1])
