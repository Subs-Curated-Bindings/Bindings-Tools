"""
Set the <startup-mode> value in a JG R14 profile's <settings> block.

The startup-mode controls which mode JG R14 activates when the profile
loads. "Use Heuristic" lets JG decide automatically (typically remembers
last-active mode). A literal mode name forces deterministic behavior.

The mode name must match one of the modes declared in the profile's
<modes> section, or the literal string "Use Heuristic".

Usage:
  python set-startup-mode.py "<profile.xml>" "SCM Mode"
  python set-startup-mode.py "<profile.xml>" "Use Heuristic"

Preserves UTF-8 BOM.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET


def set_mode(profile_path, mode_name):
    # Verify the target mode exists in the profile (or is "Use Heuristic")
    tree = ET.parse(profile_path)
    root = tree.getroot()
    declared_modes = {m.text for m in root.findall('./modes/mode') if m.text}
    if mode_name != 'Use Heuristic' and mode_name not in declared_modes:
        print(f'Mode "{mode_name}" is not declared in <modes>.', file=sys.stderr)
        print(f'Declared modes: {sorted(declared_modes)}', file=sys.stderr)
        print('  (or use "Use Heuristic" for JG\'s default behavior)', file=sys.stderr)
        return 1

    # Read preserving BOM
    with open(profile_path, 'rb') as f:
        raw = f.read()
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    text = raw.decode('utf-8-sig')

    pat = re.compile(r'(<startup-mode>)([^<]*)(</startup-mode>)')
    m = pat.search(text)
    if not m:
        print('No <startup-mode> element found in profile.', file=sys.stderr)
        return 1

    old_value = m.group(2)
    if old_value == mode_name:
        print(f'startup-mode already set to "{mode_name}" -- nothing to do.')
        return 0

    text = pat.sub(r'\1' + mode_name + r'\3', text, count=1)

    out = text.encode('utf-8')
    if has_bom and not out.startswith(b'\xef\xbb\xbf'):
        out = b'\xef\xbb\xbf' + out
    with open(profile_path, 'wb') as f:
        f.write(out)

    ET.parse(profile_path)
    print(f'startup-mode: "{old_value}" -> "{mode_name}". XML parses OK.')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('profile', help='Path to the JG R14 profile XML')
    p.add_argument('mode', help='Mode name to set as startup (or "Use Heuristic")')
    args = p.parse_args()
    sys.exit(set_mode(args.profile, args.mode))


if __name__ == '__main__':
    main()
