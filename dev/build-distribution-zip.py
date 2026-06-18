"""
Build a distribution zip for a stick repo (or legacy stick folder).

Walks the stick folder and zips everything except:
  - the .Assets/ subfolder (contributor-only)
  - Thumbs.db
  - *.af~lock~ (Affinity lock files)
  - rendered chart exports (.pdf/.png/.svg) + the .af source inside
    Binding Charts/ -- as of 2026-05-30 the website chart generator renders
    charts on demand, so the binds zip no longer ships chart files.

Toolkit bundling (Option A) -- pass --bundle-toolkit-dir + --stick-key to
inject the unified, stick-aware Bindings Toolkit (from the Bindings-Tools
repo) into the zip's Tools/ folder, stamped with $BundledStick so the
shipped copy knows which stick it is. When bundling, any pre-existing
Tools/Bindings Toolkit* / Tools/Fix MFD Binds* files in the repo are left
out of the zip (the injected unified toolkit replaces them).

The zip lands in <stick-folder>/.Assets/<zip-name> (or --out-dir/<zip-name>).
An existing zip with the same name is overwritten.

Usage:
  python build-distribution-zip.py
      --stick-folder "<path to stick repo>"
      --zip-name "[4.8.1][LIVE][ENH] MOZA MTQ + MHG Binds.zip"
      --bundle-toolkit-dir "<path to Bindings-Tools/toolkit>"
      --stick-key MOZA
"""
import argparse
import os
import sys
import zipfile


# .git / .github / .vscode are repo machinery, never user deliverables. Excluding
# .git matters now that each stick is its own repo (the old monorepo folders had none).
# assets/ holds the README header logo (logo-color/white.png) referenced by README.md
# (itself excluded) -- GitHub-repo branding from the org split, not user download content.
EXCLUDE_DIRS = {'.Assets', '.git', '.github', '.vscode', 'assets'}
# README.md is the per-stick GitHub repo landing page (org-split artifact), and
# .gitignore is a repo artifact -- neither is user-facing download content (the
# user's readme is the README - <stick>.url shortcut). Exclude both.
EXCLUDE_FILES = {'Thumbs.db', '.gitignore', 'README.md'}
EXCLUDE_SUFFIXES = ('.af~lock~',)

# Chart sources + rendered exports no longer ship (the website generator renders
# charts on demand; the .af is a contributor/generator source, not a user
# deliverable). Scoped to Binding Charts/ so unrelated files elsewhere are untouched.
CHART_DIR_NAME = 'Binding Charts'
CHART_EXPORT_SUFFIXES = ('.pdf', '.png', '.svg', '.af')

# When bundling the unified toolkit, these stale per-stick toolkit files in the
# repo's Tools/ are left out of the zip (the injected unified toolkit replaces them).
TOOLKIT_OLD_PREFIXES = ('bindings toolkit', 'fix mfd binds')

# Valid stick keys (must match the $Registry in Bindings-Tools/toolkit).
STICK_KEYS = ('NXT', 'SOL-R', 'Gunfighter', 'VMAX', 'MOZA')

BUNDLED_MARKER = b"$BundledStick = ''"


def stamp_toolkit(ps1_path, stick_key):
    """Read the unified toolkit .ps1 and stamp $BundledStick with the stick key,
    preserving the file's exact bytes/line-endings/encoding."""
    with open(ps1_path, 'rb') as f:
        raw = f.read()
    count = raw.count(BUNDLED_MARKER)
    if count != 1:
        sys.exit(f"Expected exactly one \"$BundledStick = ''\" line in {ps1_path}, found {count}.")
    return raw.replace(BUNDLED_MARKER, b"$BundledStick = '%s'" % stick_key.encode('ascii'))


def build_zip(stick_dir, zip_name, out_dir=None, toolkit_dir=None, stick_key=None):
    if not os.path.isdir(stick_dir):
        sys.exit(f'Stick folder not found: {stick_dir}')

    bundling = bool(toolkit_dir)
    if bundling:
        if stick_key not in STICK_KEYS:
            sys.exit(f'--stick-key must be one of {STICK_KEYS} when bundling; got {stick_key!r}.')
        ps1_src = os.path.join(toolkit_dir, 'Bindings Toolkit.ps1')
        bat_src = os.path.join(toolkit_dir, 'Bindings Toolkit.bat')
        for p in (ps1_src, bat_src):
            if not os.path.isfile(p):
                sys.exit(f'Toolkit file not found: {p}')

    dest_dir = out_dir if out_dir else os.path.join(stick_dir, '.Assets')
    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, zip_name)

    if os.path.exists(zip_path):
        os.remove(zip_path)
        print(f'Removed old zip: {zip_path}')

    entries = []
    total_bytes = 0

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dirpath, dirnames, filenames in os.walk(stick_dir):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            in_tools = os.path.basename(dirpath).lower() == 'tools'
            for fn in filenames:
                if fn in EXCLUDE_FILES:
                    continue
                if any(fn.endswith(suf) for suf in EXCLUDE_SUFFIXES):
                    continue
                # Skip chart sources + exports under Binding Charts/ -- website-rendered
                if (CHART_DIR_NAME in dirpath.split(os.sep)
                        and fn.lower().endswith(CHART_EXPORT_SUFFIXES)):
                    continue
                # When bundling, leave the repo's stale per-stick toolkit out of the zip
                if (bundling and in_tools
                        and any(fn.lower().startswith(pre) for pre in TOOLKIT_OLD_PREFIXES)):
                    continue
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, stick_dir).replace('\\', '/')
                zf.write(src, rel)
                sz = os.path.getsize(src)
                entries.append((rel, sz))
                total_bytes += sz

        # Inject the stamped unified toolkit into Tools/
        if bundling:
            stamped = stamp_toolkit(ps1_src, stick_key)
            zf.writestr('Tools/Bindings Toolkit.ps1', stamped)
            entries.append(('Tools/Bindings Toolkit.ps1', len(stamped)))
            total_bytes += len(stamped)
            zf.write(bat_src, 'Tools/Bindings Toolkit.bat')
            bsz = os.path.getsize(bat_src)
            entries.append(('Tools/Bindings Toolkit.bat', bsz))
            total_bytes += bsz

    entries.sort()

    print(f'\nWrote: {zip_path}')
    if bundling:
        print(f"Bundled unified toolkit, $BundledStick = '{stick_key}'")
    print(f'Entries: {len(entries)}, source total: {total_bytes/1024/1024:.2f} MiB')
    print(f'Zip size: {os.path.getsize(zip_path)/1024/1024:.2f} MiB')
    print('\nContents:')
    for rel, sz in entries:
        print(f'  {sz:>10,}  {rel}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--stick-folder', required=True, help='Path to the stick repo / folder')
    p.add_argument('--zip-name', required=True, help='Output zip filename (full name incl. .zip)')
    p.add_argument('--out-dir', help='Write the zip here instead of <stick-folder>/.Assets/ (for test builds)')
    p.add_argument('--bundle-toolkit-dir', help='Path to Bindings-Tools/toolkit to inject the unified toolkit')
    p.add_argument('--stick-key', help=f'Stick key to stamp into the bundled toolkit; one of {STICK_KEYS}')
    args = p.parse_args()
    build_zip(args.stick_folder, args.zip_name, args.out_dir, args.bundle_toolkit_dir, args.stick_key)


if __name__ == '__main__':
    main()
