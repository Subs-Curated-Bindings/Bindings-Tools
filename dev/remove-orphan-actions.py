"""
Remove orphan library actions from a JG R14 profile.

An "orphan" is an action defined under <library>/<action> that is never
referenced from any root, container action (tempo/double-tap/etc.), or
input. JG R14's UI tends to leave dead entries behind when the user edits
an action -- the new version gets a fresh ID and the old one stays in
the file unreferenced.

Orphans don't break anything, but they bloat the file and clutter audits.
Safe to remove: by definition nothing in the profile uses them.

Usage:
  python remove-orphan-actions.py "<profile.xml>"        # apply
  python remove-orphan-actions.py "<profile.xml>" --dry-run  # list only

Preserves UTF-8 BOM and line endings as JG saves them.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET


def find_orphans(profile_path):
    tree = ET.parse(profile_path)
    root = tree.getroot()
    actions = root.findall('./library/action')
    all_ids = set(a.attrib['id'] for a in actions)
    refs = set()
    input_root_refs = set()
    for el in root.iter():
        if el.tag == 'action-id' and el.text:
            refs.add(el.text)
        elif el.tag == 'root-action' and el.text:
            input_root_refs.add(el.text)
            refs.add(el.text)
    orphans = (all_ids - refs) - input_root_refs
    action_type = {a.attrib['id']: a.attrib['type'] for a in actions}
    return [(aid, action_type[aid]) for aid in sorted(orphans)]


def remove(profile_path, dry_run=False):
    orphans = find_orphans(profile_path)
    if not orphans:
        print('No orphans found.')
        return 0

    print(f'Found {len(orphans)} orphan(s):')
    for aid, t in orphans:
        print(f'  {aid[:8]} ({t})')

    if dry_run:
        print('\n(dry-run -- no changes written)')
        return 0

    # Read preserving BOM
    with open(profile_path, 'rb') as f:
        raw = f.read()
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    text = raw.decode('utf-8-sig')

    removed = 0
    for aid, _ in orphans:
        # Match the entire <action id="<aid>" type="..."> ... </action> block
        # plus the trailing newline. Library actions are at 8-space indent.
        pat = re.compile(
            r'        <action id="' + re.escape(aid) + r'" type="[^"]+">.*?\n        </action>\n',
            re.DOTALL,
        )
        new_text, n = pat.subn('', text, count=1)
        if n == 1:
            text = new_text
            removed += 1
        else:
            print(f'  WARNING: pattern did not match {aid[:8]}', file=sys.stderr)

    out = text.encode('utf-8')
    if has_bom and not out.startswith(b'\xef\xbb\xbf'):
        out = b'\xef\xbb\xbf' + out
    with open(profile_path, 'wb') as f:
        f.write(out)

    # Verify XML parses
    ET.parse(profile_path)
    print(f'\nRemoved {removed}/{len(orphans)} orphan(s). XML parses OK.')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('profile', help='Path to the JG R14 profile XML')
    p.add_argument('--dry-run', action='store_true', help='List orphans but do not modify the file')
    args = p.parse_args()
    sys.exit(remove(args.profile, args.dry_run))


if __name__ == '__main__':
    main()
