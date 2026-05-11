"""
Load a stick's layout XML into Star Citizen's live actionmaps.xml, bypassing
the SC profile-import path (which has the vehicle_mfd wipe bug).

Workflow:
  1. Copies the layout XML into <CHANNEL>\\user\\client\\0\\controls\\mappings\\
  2. Backs up the current actionmaps.xml with a timestamp suffix
  3. Builds a new actionmaps.xml by lifting the layout's body content
     (deviceoptions, options, modifiers, all <actionmap> blocks) into the
     ActionProfiles wrapper that actionmaps.xml uses.

Encoding: preserves no-BOM + CRLF (what SC writes natively).

Star Citizen MUST BE FULLY CLOSED before running. SC overwrites actionmaps.xml
on its own when running, so any edit-while-running gets silently lost. This
script does not enforce the check -- close SC manually first.

Usage:
  python load-layout-to-actionmaps.py --layout "<path to layout XML>"
                                      --channel PTU
                                     [--install-root "C:\\Program Files\\..."]
"""
import argparse
import datetime
import os
import re
import shutil
import sys


def load_layout_to_actionmaps(layout_src, install_root, channel):
    sc_base = os.path.join(install_root, channel, 'user', 'client', '0')
    layout_dst = os.path.join(sc_base, 'controls', 'mappings', os.path.basename(layout_src))
    actionmaps = os.path.join(sc_base, 'Profiles', 'default', 'actionmaps.xml')

    if not os.path.exists(layout_src):
        sys.exit(f'Layout source not found: {layout_src}')
    if not os.path.exists(actionmaps):
        sys.exit(f'actionmaps.xml not found: {actionmaps}\nLaunch SC once to let it generate the file.')

    # 1. Copy layout to mappings folder
    shutil.copy2(layout_src, layout_dst)
    print(f'Copied layout -> {layout_dst}')

    # 2. Read layout and strip outer <ActionMaps> + CustomisationUIHeader
    with open(layout_src, 'rb') as f:
        layout = f.read()
    lines = layout.split(b'\r\n')

    header_start = next((i for i, ln in enumerate(lines) if b'<CustomisationUIHeader' in ln), None)
    header_end = next((i for i, ln in enumerate(lines) if b'</CustomisationUIHeader>' in ln), None)
    if header_start is None or header_end is None:
        sys.exit('Layout XML missing CustomisationUIHeader block')

    body = lines[1:header_start] + lines[header_end + 1:-2]
    if body and body[-1].strip() == b'</ActionMaps>':
        body = body[:-1]

    # Re-indent +1 space (deeper nesting under ActionProfiles wrapper)
    reindented = [b' ' + ln if ln else ln for ln in body]
    new_lines = [
        b'<ActionMaps>',
        b' <ActionProfiles version="1" optionsVersion="2" rebindVersion="2" profileName="default">',
    ] + reindented + [
        b' </ActionProfiles>',
        b'</ActionMaps>',
        b'',
    ]
    new_content = b'\r\n'.join(new_lines)

    # 3. Backup current actionmaps
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = actionmaps + f'.bak-{ts}'
    shutil.copy2(actionmaps, backup)
    print(f'Backed up actionmaps.xml -> {backup}')

    # 4. Write new actionmaps
    with open(actionmaps, 'wb') as f:
        f.write(new_content)
    print(f'Wrote new actionmaps.xml ({len(new_content)} bytes)')

    # 5. Sanity counts
    text = new_content.decode('utf-8')
    js_rebind = '<rebind input="js'
    print(f'  actionmaps: {len(re.findall(r"<actionmap ", text))}')
    print(f'  joystick rebinds: {text.count(js_rebind)}')
    print(f'  invert lines: {len(re.findall(r"invert=", text))}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--layout', required=True, help='Path to the stick layout XML in the repo')
    p.add_argument('--channel', required=True, choices=['LIVE', 'PTU', 'EPTU', 'HOTFIX', 'TECH-PREVIEW'])
    p.add_argument('--install-root', default=r'C:\Program Files\Roberts Space Industries\StarCitizen',
                   help='SC install root that contains the channel folders')
    args = p.parse_args()
    load_layout_to_actionmaps(args.layout, args.install_root, args.channel)


if __name__ == '__main__':
    main()
