"""
Build a distribution zip for a stick folder.

Walks the stick folder and zips everything except:
  - the .Assets/ subfolder (contributor-only)
  - Thumbs.db
  - *.af~lock~ (Affinity lock files)
  - rendered chart exports (.pdf/.png/.svg) inside Binding Charts/ -- as of
    2026-05-30 the website chart generator renders charts on demand, so the
    binds zip no longer ships pre-rendered exports. The .af template stays
    (it's the generator's geometry/anchor source, not an export).

The zip lands in <stick-folder>/.Assets/<zip-name>.zip. If a zip with the
same name already exists, it is overwritten.

Usage:
  python build-distribution-zip.py
      --stick-folder "<path to stick folder>"
      --zip-name "[4.8.0][LIVE][ENH] TM SOL-R 2 Binds.zip"
"""
import argparse
import os
import sys
import zipfile


EXCLUDE_DIRS = {'.Assets'}
EXCLUDE_FILES = {'Thumbs.db'}
EXCLUDE_SUFFIXES = ('.af~lock~',)

# Chart sources + rendered exports no longer ship (the website generator renders
# charts on demand; the .af is a contributor/generator source, not a user
# deliverable). Scoped to Binding Charts/ so unrelated files elsewhere are untouched.
CHART_DIR_NAME = 'Binding Charts'
CHART_EXPORT_SUFFIXES = ('.pdf', '.png', '.svg', '.af')


def build_zip(stick_dir, zip_name):
    if not os.path.isdir(stick_dir):
        sys.exit(f'Stick folder not found: {stick_dir}')

    assets_dir = os.path.join(stick_dir, '.Assets')
    os.makedirs(assets_dir, exist_ok=True)
    zip_path = os.path.join(assets_dir, zip_name)

    if os.path.exists(zip_path):
        os.remove(zip_path)
        print(f'Removed old zip: {zip_path}')

    entries = []
    total_bytes = 0

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dirpath, dirnames, filenames in os.walk(stick_dir):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn in EXCLUDE_FILES:
                    continue
                if any(fn.endswith(suf) for suf in EXCLUDE_SUFFIXES):
                    continue
                # Skip chart sources + exports under Binding Charts/ (.af/.svg/.png/.pdf) — website-rendered
                if (CHART_DIR_NAME in dirpath.split(os.sep)
                        and fn.lower().endswith(CHART_EXPORT_SUFFIXES)):
                    continue
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, stick_dir).replace('\\', '/')
                zf.write(src, rel)
                sz = os.path.getsize(src)
                entries.append((rel, sz))
                total_bytes += sz

    entries.sort()

    print(f'\nWrote: {zip_path}')
    print(f'Entries: {len(entries)}, source total: {total_bytes/1024/1024:.2f} MiB')
    print(f'Zip size: {os.path.getsize(zip_path)/1024/1024:.2f} MiB')
    print('\nContents:')
    for rel, sz in entries:
        print(f'  {sz:>10,}  {rel}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--stick-folder', required=True, help='Path to the stick folder')
    p.add_argument('--zip-name', required=True, help='Output zip filename (will land under .Assets/)')
    args = p.parse_args()
    build_zip(args.stick_folder, args.zip_name)


if __name__ == '__main__':
    main()
