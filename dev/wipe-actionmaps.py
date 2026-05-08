"""
Delete Star Citizen's live actionmaps.xml so the next launch produces SC's
engine-default state -- the same as a brand-new user's first launch. Used
when testing a shipped layout from the end-user perspective: wipe, launch SC,
load the layout via Customization -> Control Profiles, verify binds.

Backs up the file first as actionmaps.xml.bak-yyyyMMdd-HHmmss alongside the
original, so the previous binds can be restored by renaming.

Refuses to run if StarCitizen.exe is detected -- SC holds the file open and
will overwrite any change on save anyway.

Sub's install uses the GAME/ symlink layout (LIVE/PTU/EPTU all symlink to
GAME/), so any --channel resolves to the same physical file. End-user
installs have a real per-channel directory; --channel matters there.

Usage:
  python wipe-actionmaps.py                         # defaults to LIVE
  python wipe-actionmaps.py --channel PTU
  python wipe-actionmaps.py --channel PTU --no-backup
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys


DEFAULT_INSTALL_ROOT = r'C:\Program Files\Roberts Space Industries\StarCitizen'


def sc_is_running():
    try:
        out = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq StarCitizen.exe', '/NH'],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    return 'StarCitizen.exe' in out


def wipe_actionmaps(install_root, channel, backup):
    actionmaps = os.path.join(
        install_root, channel, 'user', 'client', '0',
        'Profiles', 'default', 'actionmaps.xml',
    )

    if sc_is_running():
        sys.exit('StarCitizen.exe is running -- close it before wiping actionmaps.xml.')

    if not os.path.exists(actionmaps):
        print(f'Already absent: {actionmaps}')
        print('SC will write a fresh engine-default file on next launch.')
        return

    size = os.path.getsize(actionmaps)

    if backup:
        ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_path = actionmaps + f'.bak-{ts}'
        shutil.copy2(actionmaps, backup_path)
        print(f'Backed up -> {backup_path}')

    os.remove(actionmaps)
    print(f'Deleted {actionmaps} ({size} bytes)')
    print('Next SC launch will produce a fresh engine-default actionmaps.xml.')


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        '--channel', default='LIVE',
        choices=['LIVE', 'PTU', 'EPTU', 'HOTFIX', 'TECH-PREVIEW', 'GAME'],
        help='SC channel folder (default: LIVE). On Sub\'s install all channels symlink to GAME.',
    )
    p.add_argument(
        '--install-root', default=DEFAULT_INSTALL_ROOT,
        help='SC install root that contains the channel folders.',
    )
    p.add_argument(
        '--no-backup', dest='backup', action='store_false',
        help='Skip the timestamped backup. Default is to back up.',
    )
    args = p.parse_args()
    wipe_actionmaps(args.install_root, args.channel, args.backup)


if __name__ == '__main__':
    main()
