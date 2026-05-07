"""
Apply action-labels to compound actions in a JG R14 profile from a JSON
mapping of action-id -> label string.

JSON format (action ID can be a full UUID or a unique short prefix):
{
  "5ba40b88": "Throttle Y inverted at the JG layer here -- skips SC's in-game invert toggle.",
  "d8f1994d": "R-stick X axis curve at JG layer. Any inversion happens here, not in SC's invert menu.",
  ...
}

Per references/jg-action-labels.md: aim for ~80 chars, hard ceiling 100,
never push past 150. Script warns on >100 and refuses >150.

Preserves UTF-8 BOM (JG saves the profile with one).

Usage:
  python apply-action-labels.py "<profile.xml>" "<labels.json>"        # apply
  python apply-action-labels.py "<profile.xml>" "<labels.json>" --dry-run
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET


def apply(profile_path, labels_path, dry_run=False):
    with open(labels_path, 'r', encoding='utf-8') as f:
        labels = json.load(f)

    # Length sanity
    too_long = []
    long_warn = []
    for k, v in labels.items():
        if len(v) > 150:
            too_long.append((k, len(v)))
        elif len(v) > 100:
            long_warn.append((k, len(v)))

    if too_long:
        print('Refusing to apply: some labels exceed 150 chars (JG truncation):', file=sys.stderr)
        for k, n in too_long:
            print(f'  {k}: {n} chars', file=sys.stderr)
        return 1

    if long_warn:
        print('Warning: labels over 100 chars may be uncomfortable to read in JG\'s UI:')
        for k, n in long_warn:
            print(f'  {k}: {n} chars')

    # Read preserving BOM
    with open(profile_path, 'rb') as f:
        raw = f.read()
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    text = raw.decode('utf-8-sig')

    # For each label, locate the action block and rewrite the action-label value
    changed = 0
    not_found = []
    no_label_prop = []
    for action_id, new_label in labels.items():
        # Match block start (full ID or unique prefix)
        block_start_pat = re.compile(
            r'<action id="(' + re.escape(action_id) + r'[^"]*)" type="[^"]+">'
        )
        matches = list(block_start_pat.finditer(text))
        if len(matches) == 0:
            not_found.append(action_id)
            continue
        if len(matches) > 1:
            print(f'  WARNING: prefix {action_id} is not unique ({len(matches)} matches); skipping')
            continue
        m = matches[0]

        # Find matching </action> at library indent (8 spaces)
        end_match = re.search(r'\n        </action>\n', text[m.start():])
        if not end_match:
            print(f'  WARNING: end-of-block not found for {action_id}')
            continue

        block_start = m.start()
        block_end = block_start + end_match.end()
        block = text[block_start:block_end]

        label_pat = re.compile(
            r'(<property type="string">\s*<name>action-label</name>\s*<value>)([^<]*)(</value>\s*</property>)',
            re.DOTALL,
        )
        new_block, n = label_pat.subn(
            lambda mm: mm.group(1) + new_label + mm.group(3), block, count=1
        )
        if n == 0:
            no_label_prop.append(action_id)
            continue

        if not dry_run:
            text = text[:block_start] + new_block + text[block_end:]
        changed += 1
        marker = '[dry-run] ' if dry_run else ''
        print(f'  {marker}{action_id[:8]} ({len(new_label):3d}): {new_label[:70]}{"..." if len(new_label) > 70 else ""}')

    if not_found:
        print(f'\nNot found: {len(not_found)} action(s)')
        for k in not_found:
            print(f'  {k}')

    if no_label_prop:
        print(f'\nNo action-label property in: {len(no_label_prop)} action(s)')
        for k in no_label_prop:
            print(f'  {k}')

    if dry_run:
        print(f'\n(dry-run) Would have updated {changed}/{len(labels)} labels.')
        return 0

    # Write back
    out = text.encode('utf-8')
    if has_bom and not out.startswith(b'\xef\xbb\xbf'):
        out = b'\xef\xbb\xbf' + out
    with open(profile_path, 'wb') as f:
        f.write(out)

    ET.parse(profile_path)
    print(f'\nApplied {changed}/{len(labels)} labels. XML parses OK.')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('profile', help='Path to the JG R14 profile XML')
    p.add_argument('labels', help='Path to JSON file: {"action-id": "label", ...}')
    p.add_argument('--dry-run', action='store_true', help='Report what would change without modifying the file')
    args = p.parse_args()
    sys.exit(apply(args.profile, args.labels, args.dry_run))


if __name__ == '__main__':
    main()
